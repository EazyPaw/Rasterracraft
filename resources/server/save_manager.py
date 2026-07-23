import os
import re
import shutil
import time
import uuid
import zlib
from pathlib import Path
from typing import Any

import msgpack
import numpy as np

from resources.server.blocks import AIR, get_block_by_id
from resources.server.location import Location


FORMAT_VERSION = 1
REGION_SIZE = 256
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAVES_ROOT = PROJECT_ROOT / "saves"
LEGACY_SAVES_ROOT = PROJECT_ROOT / "data" / "saves"
_LEGACY_MIGRATED = False


def ensure_saves_root() -> Path:
    SAVES_ROOT.mkdir(parents=True, exist_ok=True)
    _migrate_legacy_saves()
    return SAVES_ROOT


def _migrate_legacy_saves() -> None:
    global _LEGACY_MIGRATED
    if _LEGACY_MIGRATED or LEGACY_SAVES_ROOT == SAVES_ROOT or not LEGACY_SAVES_ROOT.exists():
        _LEGACY_MIGRATED = True
        return
    for child in LEGACY_SAVES_ROOT.iterdir():
        if not child.is_dir():
            continue
        target = SAVES_ROOT / child.name
        if target.exists():
            continue
        try:
            shutil.copytree(child, target)
        except OSError:
            pass
    _LEGACY_MIGRATED = True


def _safe_save_id(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"[^a-z0-9_.-]+", "", value)
    return value[:48].strip("._-") or "world"


def _now() -> float:
    return time.time()


def level_path(save_id: str) -> Path:
    return ensure_saves_root() / save_id / "level.msgpack"


def save_path(save_id: str) -> Path:
    return ensure_saves_root() / save_id


def _region_index(rx: int) -> int:
    return int(rx) // REGION_SIZE


def region_path(save_id: str, world_id: str, region_index: int) -> Path:
    return save_path(save_id) / "worlds" / world_id / "regions" / f"r.{region_index}.region"


def entity_region_path(save_id: str, world_id: str, region_index: int) -> Path:
    """Path for one 256-chunk-wide entity region.

    ``entitys`` intentionally follows the save-layout name requested by the
    project, while keeping entity data separate from block region files.
    """
    return (
        save_path(save_id)
        / "worlds"
        / world_id
        / "entitys"
        / f"r.{region_index}.entity"
    )


def chunk_path(save_id: str, world_id: str, rx: int) -> Path:
    """Legacy one-file-per-chunk path kept only for reading old test saves."""
    return save_path(save_id) / "worlds" / world_id / "chunks" / f"{rx}.chunk"


def icon_path(save_id: str) -> Path:
    return save_path(save_id) / "icon.png"


def _read_msgpack(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("rb") as fh:
        raw = fh.read()
    try:
        raw = zlib.decompress(raw)
    except zlib.error:
        pass
    return msgpack.unpackb(raw, raw=False)


def _write_msgpack(path: Path, data: dict[str, Any], *, compress: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    packed = msgpack.packb(data, use_bin_type=True)
    if compress:
        packed = zlib.compress(packed, level=3)
    tmp_path = path.with_name(path.name + ".tmp")
    with tmp_path.open("wb") as fh:
        fh.write(packed)
    os.replace(tmp_path, path)


def load_level(save_id: str) -> dict[str, Any] | None:
    return _read_msgpack(level_path(save_id))


def save_level(save_id: str, data: dict[str, Any]) -> None:
    data["format_version"] = FORMAT_VERSION
    data["last_played"] = _now()
    _write_msgpack(level_path(save_id), data, compress=False)


def create_save(display_name: str = "New World", *, version: str = "", game_mode: str = "survival") -> dict[str, Any]:
    ensure_saves_root()
    base_id = _safe_save_id(display_name)
    save_id = f"{base_id}_{int(_now())}_{uuid.uuid4().hex[:6]}"
    data = {
        "format_version": FORMAT_VERSION,
        "id": save_id,
        "display_name": display_name.strip() or "New World",
        "created_at": _now(),
        "last_played": _now(),
        "version": version,
        "game_mode": game_mode,
        "worlds": {},
        "player": {"x": 0.0, "y": 100.0},
    }
    save_level(save_id, data)
    return data


def ensure_level(
    save_id: str,
    *,
    display_name: str = "New World",
    version: str = "",
    game_mode: str = "survival",
) -> dict[str, Any]:
    data = load_level(save_id)
    if data is not None:
        data.setdefault("id", save_id)
        data.setdefault("display_name", display_name)
        data.setdefault("created_at", _now())
        data.setdefault("last_played", _now())
        data.setdefault("version", version)
        data.setdefault("game_mode", game_mode)
        data.setdefault("worlds", {})
        data.setdefault("player", {"x": 0.0, "y": 100.0})
        return data

    data = {
        "format_version": FORMAT_VERSION,
        "id": save_id,
        "display_name": display_name,
        "created_at": _now(),
        "last_played": _now(),
        "version": version,
        "game_mode": game_mode,
        "worlds": {},
        "player": {"x": 0.0, "y": 100.0},
    }
    save_level(save_id, data)
    return data


def list_saves() -> list[dict[str, Any]]:
    root = ensure_saves_root()
    saves: list[dict[str, Any]] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        try:
            data = load_level(child.name)
        except Exception:
            data = None
        if data is None:
            data = {
                "id": child.name,
                "display_name": child.name,
                "created_at": child.stat().st_mtime,
                "last_played": child.stat().st_mtime,
                "version": "",
                "game_mode": "unknown",
                "worlds": {},
                "player": {"x": 0.0, "y": 100.0},
            }
        data.setdefault("id", child.name)
        data["path"] = str(child)
        saves.append(data)
    saves.sort(key=lambda item: float(item.get("last_played", 0)), reverse=True)
    return saves


def delete_save(save_id: str) -> None:
    path = save_path(save_id)
    if path.exists():
        shutil.rmtree(path)


def _read_region(save_id: str, world_id: str, region_index: int) -> dict[str, Any]:
    path = region_path(save_id, world_id, region_index)
    data = _read_msgpack(path)
    if data is None:
        return {
            "format_version": FORMAT_VERSION,
            "region_size": REGION_SIZE,
            "region_index": region_index,
            "chunks": {},
        }
    data.setdefault("format_version", FORMAT_VERSION)
    data.setdefault("region_size", REGION_SIZE)
    data.setdefault("region_index", region_index)
    data.setdefault("chunks", {})
    return data


def _write_region(save_id: str, world_id: str, region_index: int, data: dict[str, Any]) -> None:
    data["format_version"] = FORMAT_VERSION
    data["region_size"] = REGION_SIZE
    data["region_index"] = region_index
    _write_msgpack(region_path(save_id, world_id, region_index), data, compress=True)


def _read_entity_region(
    save_id: str, world_id: str, region_index: int
) -> dict[str, Any]:
    data = _read_msgpack(entity_region_path(save_id, world_id, region_index))
    if data is None:
        return {
            "format_version": FORMAT_VERSION,
            "region_size": REGION_SIZE,
            "region_index": region_index,
            "chunks": {},
        }
    data.setdefault("format_version", FORMAT_VERSION)
    data.setdefault("region_size", REGION_SIZE)
    data.setdefault("region_index", region_index)
    data.setdefault("chunks", {})
    return data


def _write_entity_region(
    save_id: str, world_id: str, region_index: int, data: dict[str, Any]
) -> None:
    data["format_version"] = FORMAT_VERSION
    data["region_size"] = REGION_SIZE
    data["region_index"] = region_index
    _write_msgpack(
        entity_region_path(save_id, world_id, region_index), data, compress=True
    )


def load_entity_chunk(save_id: str | None, world_id: str, rx: int) -> list[dict]:
    """Load entity records belonging to exactly one block chunk."""
    if not save_id:
        return []
    region = _read_entity_region(str(save_id), world_id, _region_index(rx))
    records = region.get("chunks", {}).get(str(int(rx)), ())
    if not isinstance(records, (list, tuple)):
        raise ValueError(f"Invalid entity chunk data for {world_id}:{rx}")
    return [dict(record) for record in records if isinstance(record, dict)]


def save_entity_chunks(
    save_id: str, world_id: str, records_by_chunk: dict[int, list[dict]]
) -> None:
    """Replace entity snapshots for the supplied chunks.

    Explicitly writing an empty list clears entities removed since the previous
    save, which is essential when an item is picked up or moves to a new chunk.
    """
    grouped: dict[int, dict[int, list[dict]]] = {}
    for raw_rx, raw_records in records_by_chunk.items():
        rx = int(raw_rx)
        records: list[dict] = []
        seen_uuids: set[str] = set()
        for raw_record in raw_records or ():
            if not isinstance(raw_record, dict):
                continue
            record = dict(raw_record)
            entity_uuid = str(record.get("uuid", ""))
            if entity_uuid and entity_uuid in seen_uuids:
                continue
            if entity_uuid:
                seen_uuids.add(entity_uuid)
            records.append(record)
        grouped.setdefault(_region_index(rx), {})[rx] = records

    for region_index, chunk_records in grouped.items():
        region = _read_entity_region(save_id, world_id, region_index)
        chunk_map = region.setdefault("chunks", {})
        for rx, records in chunk_records.items():
            chunk_map[str(rx)] = records
        _write_entity_region(save_id, world_id, region_index, region)


def chunk_exists(save_id: str | None, world_id: str, rx: int) -> bool:
    if not save_id:
        return False
    region = _read_region(str(save_id), world_id, _region_index(rx))
    return str(int(rx)) in region.get("chunks", {}) or chunk_path(str(save_id), world_id, rx).exists()


def _block_payload(block) -> str | dict[str, Any]:
    nbt = block.parse_nbt()
    if nbt:
        return {"id": block.block_id, "nbt": nbt}
    return block.block_id


def _payload_key(payload: str | dict[str, Any]) -> bytes:
    return msgpack.packb(payload, use_bin_type=True)


def _flatten_blocks(chunk) -> tuple[list[Any], list[int]]:
    palette: list[Any] = []
    palette_index: dict[bytes, int] = {}
    indices: list[int] = []
    region = chunk.region_array
    for x in range(region.shape[0]):
        for y in range(region.shape[1]):
            for z in range(region.shape[2]):
                payload = _block_payload(region[x, y, z])
                key = _payload_key(payload)
                idx = palette_index.get(key)
                if idx is None:
                    idx = len(palette)
                    palette_index[key] = idx
                    palette.append(payload)
                indices.append(idx)
    return palette, indices


def _flatten_biomes(chunk) -> tuple[list[str], list[int]]:
    palette: list[str] = []
    palette_index: dict[str, int] = {}
    indices: list[int] = []
    biomes = chunk.biome_array
    for x in range(biomes.shape[0]):
        for y in range(biomes.shape[1]):
            biome_id = str(biomes[x, y])
            idx = palette_index.get(biome_id)
            if idx is None:
                idx = len(palette)
                palette_index[biome_id] = idx
                palette.append(biome_id)
            indices.append(idx)
    return palette, indices


def chunk_to_data(chunk) -> dict[str, Any]:
    block_palette, block_indices = _flatten_blocks(chunk)
    biome_palette, biome_indices = _flatten_biomes(chunk)
    return {
        "format_version": FORMAT_VERSION,
        "x": int(chunk.x),
        "height": int(chunk.region_array.shape[1]),
        "depth": int(chunk.region_array.shape[2]),
        "block_palette": block_palette,
        "block_indices": block_indices,
        "biome_palette": biome_palette,
        "biome_indices": biome_indices,
    }


def save_chunks(save_id: str, world_id: str, chunks) -> None:
    grouped: dict[int, list] = {}
    for chunk in chunks:
        if chunk is None:
            continue
        grouped.setdefault(_region_index(int(chunk.x)), []).append(chunk)

    for region_index, region_chunks in grouped.items():
        region = _read_region(save_id, world_id, region_index)
        chunk_map = region.setdefault("chunks", {})
        for chunk in region_chunks:
            chunk_map[str(int(chunk.x))] = chunk_to_data(chunk)
        _write_region(save_id, world_id, region_index, region)


def save_chunk(save_id: str, world_id: str, chunk) -> None:
    save_chunks(save_id, world_id, [chunk])


def _make_block(payload: str | dict[str, Any], world, x: int, y: int, z: int):
    if isinstance(payload, str):
        block_id = payload
        nbt = None
    else:
        block_id = payload.get("id", "air")
        nbt = payload.get("nbt")
    block = get_block_by_id(block_id)
    if nbt:
        block.write_nbt(nbt)
    block.location = Location(world, x, y, z)
    return block


def load_chunk(save_id: str, world_id: str, rx: int, world):
    region = _read_region(save_id, world_id, _region_index(rx))
    data = region.get("chunks", {}).get(str(int(rx)))
    if data is None:
        data = _read_msgpack(chunk_path(save_id, world_id, rx))
    if data is None:
        return None

    from resources.server.world_class import Chunk

    height = int(data.get("height", world.attribute.MAX_BUILD_HEIGHT))
    depth = int(data.get("depth", 2))
    region = np.full((16, height, depth), AIR(), dtype=object)
    block_palette = data.get("block_palette", ["air"])
    block_indices = data.get("block_indices", [])
    expected_blocks = 16 * height * depth
    if len(block_indices) != expected_blocks:
        raise ValueError(f"Invalid chunk block data length for {world_id}:{rx}")

    i = 0
    for x in range(16):
        world_x = rx * 16 + x
        for y in range(height):
            for z in range(depth):
                region[x, y, z] = _make_block(block_palette[block_indices[i]], world, world_x, y, z)
                i += 1

    biome_palette = data.get("biome_palette", ["void"])
    biome_indices = data.get("biome_indices", [])
    biome_array = np.full((16, height), "void", dtype="<U32")
    expected_biomes = 16 * height
    if len(biome_indices) == expected_biomes:
        i = 0
        for x in range(16):
            for y in range(height):
                biome_array[x, y] = biome_palette[biome_indices[i]]
                i += 1
    else:
        for x in range(16):
            world_x = rx * 16 + x
            for y in range(height):
                biome_array[x, y] = world.generator.get_original_biome(world_x, y)

    return Chunk(rx, region, biome_array)
