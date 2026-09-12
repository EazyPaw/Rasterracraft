"""Structure-template capture and placement.

JSON templates are human-readable.  ``.structure`` templates contain the same
data encoded as compressed MessagePack.  Blocks use the same palette/NBT shape
as chunk saves, while ``structure_void`` is a template-only sentinel that
leaves the destination untouched.
"""

from __future__ import annotations

import json
import os
import re
import zlib
from pathlib import Path
from typing import Any

import msgpack

from src.server.blocks import AIR, get_block_by_id, has_block_id
from src.server.entity_registry import create_entity_from_save, is_entity_persistent
from src.server.location import Location


STRUCTURES_ROOT = Path(__file__).resolve().parents[2] / "structures"
FORMAT_VERSION = 1
MAX_TEMPLATE_CELLS = 131072
_NAME_PART = re.compile(r"^[a-z0-9_.-]+$")
_SERIALIZED_MAGIC = b"PYC2DS1\0"
_FORMAT_SUFFIXES = {"json": ".json", "serialized": ".structure"}
_LEGACY_RUNTIME_NBT_FIELDS = {"location", "place_sound"}


def normalize_structure_name(value: str) -> str:
    """Return a traversal-safe, namespaced-friendly relative structure name."""
    raw = str(value).strip().lower().replace("\\", "/")
    for suffix in _FORMAT_SUFFIXES.values():
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)]
            break
    parts = [part for part in raw.split("/") if part]
    if not parts or any(
        part in (".", "..") or not _NAME_PART.fullmatch(part) for part in parts
    ):
        raise ValueError("Structure name may only contain a-z, 0-9, _, -, . and /")
    return "/".join(parts)


def structure_path(name: str, file_format: str = "json") -> Path:
    if file_format not in _FORMAT_SUFFIXES:
        raise ValueError(f"Unknown structure file format: {file_format}")
    normalized = normalize_structure_name(name)
    base = STRUCTURES_ROOT.joinpath(*normalized.split("/"))
    path = base.with_name(base.name + _FORMAT_SUFFIXES[file_format])
    resolved_root = STRUCTURES_ROOT.resolve()
    resolved = path.resolve()
    if resolved_root not in resolved.parents:
        raise ValueError("Structure path escapes the structures directory")
    return path


def _block_payload(block) -> dict[str, Any]:
    payload: dict[str, Any] = {"id": str(block.block_id)}
    nbt = dict(block.parse_nbt() or {})
    for field in _LEGACY_RUNTIME_NBT_FIELDS:
        nbt.pop(field, None)
    if nbt:
        payload["nbt"] = nbt
    return payload


def _palette_index(payload: dict[str, Any], palette, lookup) -> int:
    key = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    index = lookup.get(key)
    if index is None:
        index = len(palette)
        lookup[key] = index
        palette.append(payload)
    return index


def _capture_structure_data(world, name: str) -> dict[str, Any]:
    with world._structure_lock:
        bounds = world.structure_bounds
        void_positions = set(world.structure_void_positions)
    if bounds is None:
        raise ValueError("The structure build area is empty")
    x_min, y_min, x_max, y_max = bounds
    width, height, depth = x_max - x_min + 1, y_max - y_min + 1, 2
    cell_count = width * height * depth
    if cell_count > MAX_TEMPLATE_CELLS:
        raise ValueError(
            f"Structure has {cell_count} cells; maximum is {MAX_TEMPLATE_CELLS}"
        )
    for rx in range(x_min // 16, x_max // 16 + 1):
        if rx not in world.regions:
            world.generate_chunk(rx)

    palette: list[dict[str, Any]] = []
    lookup: dict[str, int] = {}
    indices: list[int] = []
    for x in range(x_min, x_max + 1):
        for y in range(y_min, y_max + 1):
            for z in range(depth):
                if (x, y, z) in void_positions:
                    payload = {"id": "structure_void"}
                else:
                    payload = _block_payload(world.get_block(x, y, z))
                indices.append(_palette_index(payload, palette, lookup))

    entities = []
    with world._entities_lock:
        candidates = tuple(world.entities.values())
    for entity in candidates:
        if (
            entity.entity_id == "player"
            or entity.removed
            or entity.health <= 0
            or not is_entity_persistent(entity)
            or not (x_min <= float(entity.x) < x_max + 1)
            or not (y_min <= float(entity.y) < y_max + 1)
        ):
            continue
        record = entity.to_save_data()
        record.pop("uuid", None)
        record["x"] = float(entity.x) - x_min
        record["y"] = float(entity.y) - y_min
        entities.append(record)

    normalized = normalize_structure_name(name)
    data = {
        "format_version": FORMAT_VERSION,
        "id": normalized,
        "size": [width, height, depth],
        "anchor": [0, 0, 0],
        "palette": palette,
        "blocks": indices,
        "entities": entities,
    }
    return data


def write_structure_data(
    name: str, data: dict[str, Any], file_format: str = "json"
) -> Path:
    """Atomically write one structure representation."""
    path = structure_path(name, file_format)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if file_format == "json":
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    elif file_format == "serialized":
        encoded = msgpack.packb(data, use_bin_type=True)
        payload = _SERIALIZED_MAGIC + zlib.compress(encoded, level=9)
        with temporary.open("wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    else:
        raise ValueError(f"Unknown structure file format: {file_format}")
    temporary.replace(path)
    return path


def capture_structure(
    world, name: str, file_format: str = "json"
) -> tuple[Path, dict[str, Any]]:
    data = _capture_structure_data(world, name)
    path = write_structure_data(data["id"], data, file_format)
    return path, data


def load_structure_data(name: str) -> tuple[Path, dict[str, Any]]:
    lowered = str(name).strip().lower()
    if lowered.endswith(".json"):
        file_format = "json"
        path = structure_path(name, file_format)
    elif lowered.endswith(".structure"):
        file_format = "serialized"
        path = structure_path(name, file_format)
    else:
        serialized_path = structure_path(name, "serialized")
        file_format = "serialized" if serialized_path.is_file() else "json"
        path = (
            serialized_path
            if file_format == "serialized"
            else structure_path(name)
        )
    try:
        if file_format == "json":
            with path.open("r", encoding="utf-8") as stream:
                data = json.load(stream)
        else:
            payload = path.read_bytes()
            if not payload.startswith(_SERIALIZED_MAGIC):
                raise ValueError("Invalid serialized structure header")
            data = msgpack.unpackb(
                zlib.decompress(payload[len(_SERIALIZED_MAGIC) :]), raw=False
            )
    except FileNotFoundError as exc:
        raise ValueError(f"Unknown structure: {normalize_structure_name(name)}") from exc
    except (
        OSError,
        json.JSONDecodeError,
        msgpack.UnpackException,
        zlib.error,
    ) as exc:
        raise ValueError(f"Cannot read structure {name}: {exc}") from exc
    if not isinstance(data, dict) or int(data.get("format_version", 0)) != FORMAT_VERSION:
        raise ValueError("Unsupported structure format")
    size = data.get("size")
    if not isinstance(size, list) or len(size) != 3:
        raise ValueError("Structure size must contain width, height and depth")
    try:
        width, height, depth = (int(value) for value in size)
    except (TypeError, ValueError) as exc:
        raise ValueError("Structure size is invalid") from exc
    if width <= 0 or height <= 0 or depth not in (1, 2):
        raise ValueError("Structure dimensions are invalid")
    if width * height * depth > MAX_TEMPLATE_CELLS:
        raise ValueError("Structure is too large")
    palette, blocks = data.get("palette"), data.get("blocks")
    if not isinstance(palette, list) or not isinstance(blocks, list):
        raise ValueError("Structure palette or block data is missing")
    if len(blocks) != width * height * depth:
        raise ValueError("Structure block data length does not match its size")
    for entry in palette:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise ValueError("Structure palette contains an invalid entry")
        if entry["id"] != "structure_void" and not has_block_id(entry["id"]):
            raise ValueError(f"Unknown block in structure palette: {entry['id']}")
        # Older files may contain runtime fields emitted by Block.__init__.
        # Ignore them in memory so loading/resaving naturally cleans the file.
        nbt = entry.get("nbt")
        if isinstance(nbt, dict):
            for field in _LEGACY_RUNTIME_NBT_FIELDS:
                nbt.pop(field, None)
            if not nbt:
                entry.pop("nbt", None)
    return path, data


def _sync_changed_chunks(world, affected_chunks: set[int]) -> None:
    if not affected_chunks:
        return
    for rx in affected_chunks:
        world.mark_chunk_dirty(rx)
        world.invalidate_chunk_packet(rx)
        if not world.structure_build_mode:
            world.schedule_chunk_and_boundary_fluids(rx)
    changed_light = world.recalculate_light_for_chunks(affected_chunks)
    for rx in affected_chunks:
        chunk = world.regions.get(rx)
        if chunk is None:
            continue
        for player in world.server.players:
            if rx in player.loading_regions:
                world.server.send_client_socket(player, chunk, "Chunk")
    world.send_light_updates(changed_light - affected_chunks)


def apply_structure_mask(
    world,
    kind: str,
    start: tuple[int, int, int],
    end: tuple[int, int, int],
) -> int:
    """Paint template-only air/void semantics and clear real blocks below it."""
    if not world.structure_build_mode:
        raise ValueError("Structure masks can only be edited in Structure Build worlds")
    if kind not in {"air", "structure_void"}:
        raise ValueError("Unknown structure mask")
    x1, y1, z1 = (int(value) for value in start)
    x2, y2, z2 = (int(value) for value in end)
    if z1 != z2 or z1 not in (0, 1):
        raise ValueError("A mask selection must stay on one depth layer")
    x_min, x_max = sorted((x1, x2))
    y_min, y_max = sorted((y1, y2))
    y_min = max(0, y_min)
    y_max = min(world.attribute.MAX_BUILD_HEIGHT - 1, y_max)
    total = (x_max - x_min + 1) * max(0, y_max - y_min + 1)
    if total > MAX_TEMPLATE_CELLS:
        raise ValueError(f"Mask selection has {total} cells; maximum is {MAX_TEMPLATE_CELLS}")
    for rx in range(x_min // 16, x_max // 16 + 1):
        if rx not in world.regions:
            world.generate_chunk(rx)

    affected: set[int] = set()
    void_add: list[tuple[int, int, int]] = []
    void_remove: list[tuple[int, int, int]] = []
    with world._structure_lock:
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                position = (x, y, z1)
                old = world.get_block(x, y, z1)
                unload = getattr(old, "on_unload", None)
                if callable(unload):
                    unload()
                air = AIR()
                air.location = Location(world, x, y, z1)
                world.regions[x // 16].region_array[x % 16, y, z1] = air
                world.structure_content_positions.discard(position)
                if kind == "structure_void":
                    if position not in world.structure_void_positions:
                        void_add.append(position)
                    world.structure_void_positions.add(position)
                    world.structure_air_positions.discard(position)
                else:
                    if position in world.structure_void_positions:
                        void_remove.append(position)
                    world.structure_void_positions.discard(position)
                affected.add(x // 16)

        if kind == "air":
            world.structure_air_positions.update(
                {
                    (x_min, y_min, z1),
                    (x_min, y_max, z1),
                    (x_max, y_min, z1),
                    (x_max, y_max, z1),
                }
            )

        world._refresh_structure_bounds()
    _sync_changed_chunks(world, affected)
    world.send_structure_build_delta(void_add=void_add, void_remove=void_remove)
    return total


def place_structure(world, name: str, origin: tuple[int, int, int]) -> dict[str, int]:
    _path, data = load_structure_data(name)
    origin_x, origin_y, origin_z = (int(value) for value in origin)
    width, height, depth = (int(value) for value in data["size"])
    if origin_y < 0 or origin_y + height > world.attribute.MAX_BUILD_HEIGHT:
        raise ValueError("Structure exceeds the world's build height")
    if origin_z < 0 or origin_z + depth > 2:
        raise ValueError("Structure exceeds the world's depth layers")
    for rx in range(origin_x // 16, (origin_x + width - 1) // 16 + 1):
        if rx not in world.regions:
            world.generate_chunk(rx)

    palette = data["palette"]
    affected: set[int] = set()
    placed = skipped = 0
    index = 0
    for dx in range(width):
        x = origin_x + dx
        for dy in range(height):
            y = origin_y + dy
            for dz in range(depth):
                z = origin_z + dz
                try:
                    entry = palette[int(data["blocks"][index])]
                except (IndexError, TypeError, ValueError) as exc:
                    raise ValueError("Structure contains an invalid palette index") from exc
                index += 1
                if entry["id"] == "structure_void":
                    skipped += 1
                    continue
                block = get_block_by_id(entry["id"])
                nbt = entry.get("nbt")
                if isinstance(nbt, dict):
                    block.write_nbt(nbt)
                old = world.get_block(x, y, z)
                unload = getattr(old, "on_unload", None)
                if callable(unload):
                    unload()
                block.location = Location(world, x, y, z)
                world.regions[x // 16].region_array[x % 16, y, z] = block
                load = getattr(block, "on_load", None)
                if callable(load) and not world.structure_build_mode:
                    load()
                affected.add(x // 16)
                placed += 1

    spawned = 0
    for source in data.get("entities", []):
        if not isinstance(source, dict):
            continue
        record = dict(source)
        record.pop("uuid", None)
        try:
            record["x"] = origin_x + float(source.get("x", 0.0))
            record["y"] = origin_y + float(source.get("y", 0.0))
            record["z"] = origin_z + int(source.get("z", 0))
        except (TypeError, ValueError, OverflowError):
            continue
        entity = create_entity_from_save(record, world)
        if entity is not None and entity.health > 0:
            world.spawn_entity(entity)
            spawned += 1

    _sync_changed_chunks(world, affected)
    if world.structure_build_mode:
        world.note_structure_region_change(
            origin_x, origin_y, origin_z, width, height, depth
        )
    return {"placed": placed, "skipped": skipped, "entities": spawned}


def list_structures() -> list[str]:
    if not STRUCTURES_ROOT.exists():
        return []
    names = {
        path.relative_to(STRUCTURES_ROOT).with_suffix("").as_posix()
        for suffix in _FORMAT_SUFFIXES.values()
        for path in STRUCTURES_ROOT.rglob(f"*{suffix}")
        if path.is_file()
    }
    return sorted(names)
