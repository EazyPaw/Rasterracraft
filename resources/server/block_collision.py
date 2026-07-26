# Commented and arranged by ChatGPT

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Iterable, Sequence


@dataclass(frozen=True)
class CollisionBox:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def __post_init__(self):
        values = (self.min_x, self.min_y, self.max_x, self.max_y)
        if not all(isinstance(value, Real) for value in values):
            raise TypeError("collision bounds must be numbers")
        if self.max_x <= self.min_x or self.max_y <= self.min_y:
            raise ValueError("collision bounds must have positive size")

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    def translated(self, x: float, y: float) -> "CollisionBox":
        return type(self)(
            self.min_x + x, self.min_y + y, self.max_x + x, self.max_y + y
        )

    def overlaps(
        self,
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
        epsilon: float = 1.0e-9,
    ) -> bool:
        return (
            self.max_x > min_x + epsilon
            and self.min_x < max_x - epsilon
            and self.max_y > min_y + epsilon
            and self.min_y < max_y - epsilon
        )


@dataclass(frozen=True)
class BlockCollisionBox:
    boxes: tuple[CollisionBox, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "boxes", tuple(self.boxes))
        if not all(isinstance(box, CollisionBox) for box in self.boxes):
            raise TypeError("boxes must contain CollisionBox instances")

    def __iter__(self):
        return iter(self.boxes)

    @property
    def collision_boxes(self) -> tuple[CollisionBox, ...]:
        return self.boxes

    def __len__(self):
        return len(self.boxes)

    def __bool__(self):
        return bool(self.boxes)

    @property
    def is_empty(self) -> bool:
        return not self.boxes

    @property
    def max_height(self) -> float:
        return max((box.max_y for box in self.boxes), default=0.0)

    @property
    def min_x(self) -> float:
        return min((box.min_x for box in self.boxes), default=0.0)

    @property
    def min_y(self) -> float:
        return min((box.min_y for box in self.boxes), default=0.0)

    @property
    def max_x(self) -> float:
        return max((box.max_x for box in self.boxes), default=0.0)

    @property
    def max_y(self) -> float:
        return max((box.max_y for box in self.boxes), default=0.0)

    @classmethod
    def from_box(cls, min_x=0.0, min_y=0.0, max_x=1.0, max_y=1.0):
        return cls(
            (CollisionBox(float(min_x), float(min_y), float(max_x), float(max_y)),)
        )

    @classmethod
    def full_block(cls) -> "BlockCollisionBox":
        return FULL_BLOCK

    @classmethod
    def empty(cls) -> "BlockCollisionBox":
        return EMPTY

    @classmethod
    def from_grid(
        cls, grid: Sequence[Sequence[int] | str], *, cell_size=16, origin_y=0.0
    ) -> "BlockCollisionBox":
        return grid_collision(grid, cell_size=cell_size, origin_y=origin_y)


CollisionShape = BlockCollisionBox
AABB = CollisionBox
box = CollisionBox


EMPTY = BlockCollisionBox(())
FULL_BLOCK = BlockCollisionBox.from_box()
HALF_BOTTOM = BlockCollisionBox.from_box(0, 0, 1, 0.5)
HALF_TOP = BlockCollisionBox.from_box(0, 0.5, 1, 1)
QUARTER_BLOCK = BlockCollisionBox.from_box(0, 0, 1, 0.25)
FENCE_POST = BlockCollisionBox.from_box(0.375, 0, 0.625, 1.5)
POST = FENCE_POST

FULL = FULL_BLOCK
HALF = HALF_BOTTOM
BOTTOM_SLAB = HALF_BOTTOM
TOP_SLAB = HALF_TOP
EMPTY_COLLISION = EMPTY
FENCE_COLLISION = FENCE_POST


def grid_collision(
    grid: Sequence[Sequence[int] | str], *, cell_size: int = 16, origin_y: float = 0.0
) -> BlockCollisionBox:
    if not isinstance(cell_size, int) or cell_size <= 0:
        raise ValueError("cell_size must be a positive integer")
    if isinstance(grid, str):
        lines = [line.strip() for line in grid.splitlines() if line.strip()]
        if len(lines) == 1 and len(lines[0]) == cell_size * cell_size:
            lines = [
                lines[0][i : i + cell_size] for i in range(0, len(lines[0]), cell_size)
            ]
        grid = lines
    elif (
        isinstance(grid, Sequence)
        and len(grid) == cell_size * cell_size
        and all(not isinstance(value, (Sequence, str)) for value in grid)
    ):
        grid = [grid[i : i + cell_size] for i in range(0, len(grid), cell_size)]
    if not isinstance(grid, Sequence) or len(grid) != cell_size:
        raise ValueError(f"collision grid must have {cell_size} rows")

    boxes: list[CollisionBox] = []
    for row_index, row in enumerate(grid):
        if isinstance(row, str):
            values = list(row)
        else:
            try:
                values = list(row)
            except TypeError as exc:
                raise ValueError("each collision grid row must be a sequence") from exc
        if len(values) != cell_size:
            raise ValueError(f"collision grid rows must have {cell_size} columns")
        run_start = None
        for column, value in enumerate(values + [0]):
            if value not in (0, 1, "0", "1", False, True):
                raise ValueError("collision grid values must be 0 or 1")
            occupied = value in (1, "1", True)
            if occupied and run_start is None:
                run_start = column
            elif not occupied and run_start is not None:
                boxes.append(
                    CollisionBox(
                        run_start / cell_size,
                        origin_y + row_index / cell_size,
                        column / cell_size,
                        origin_y + (row_index + 1) / cell_size,
                    )
                )
                run_start = None
    return BlockCollisionBox(tuple(boxes))


custom_collision = grid_collision


def coerce_collision_shape(value) -> BlockCollisionBox:
    if value is None or value is False:
        return EMPTY
    if isinstance(value, BlockCollisionBox):
        return value
    if isinstance(value, CollisionBox):
        return BlockCollisionBox((value,))
    if isinstance(value, Iterable):
        if (
            isinstance(value, (tuple, list))
            and len(value) == 4
            and all(isinstance(item, Real) for item in value)
        ):
            return BlockCollisionBox((CollisionBox(*value),))
        boxes = []
        for item in value:
            if isinstance(item, CollisionBox):
                boxes.append(item)
            else:
                boxes.append(CollisionBox(*item))
        return BlockCollisionBox(tuple(boxes))
    raise TypeError(f"unsupported collision shape: {type(value)!r}")
