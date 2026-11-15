"""Shared 1.8 dragon movement history and projected multipart hit geometry."""
import math


def wrap_degrees(value):
    return (value + 180.0) % 360.0 - 180.0


def movement_offset(history, offset, yaw, y):
    return history[min(offset, len(history) - 1)] if history else (yaw, y)


class DragonPart:
    """An ephemeral damage proxy; only its parent is tracked or saved."""
    def __init__(self, parent, name, cx, cy, width, height):
        self.parent, self.part_name = parent, name
        self.x, self.y = cx - width / 2, cy - height / 2
        self.width, self.height = width, height

    def __getattr__(self, name):
        return getattr(self.parent, name)

    def apply_damage(self, amount, damage_type=None, source=None, knockback=None, **kwargs):
        return self.parent.apply_part_damage(self.part_name, amount, damage_type,
                                             source=source, knockback=knockback, **kwargs)


def dragon_parts(entity):
    cx, cy = entity.x + entity.width / 2, entity.y + entity.height / 2
    yaw = float(getattr(entity, "dragon_yaw", 90))
    turn = float(getattr(entity, "dragon_turn", 0))
    history = getattr(entity, "dragon_history", ())
    old5 = movement_offset(history, 5, yaw, cy)
    old10 = movement_offset(history, 10, yaw, cy)
    pitch = math.radians((old5[1] - old10[1]) * 10)
    sy, co = math.sin(math.radians(yaw)), math.cos(math.radians(yaw))
    head_yaw = math.radians(yaw - turn * .01)
    parts = [DragonPart(entity, "head", cx + math.sin(head_yaw) * 5.5 * math.cos(pitch),
                        cy + cy - old5[1] - math.sin(pitch) * 5.5, 3, 3),
             DragonPart(entity, "body", cx + sy * .5, cy, 5, 3)]
    for i in range(3):
        old = movement_offset(history, 12 + i * 2, yaw, cy)
        a = math.radians(yaw + wrap_degrees(old[0] - old5[0]))
        distance = (i + 1) * 2
        parts.append(DragonPart(entity, "tail", cx - (sy * 1.5 + math.sin(a) * distance) * math.cos(pitch),
                                cy + old[1] - old5[1] + (distance + 1.5) * math.sin(pitch) + 1.5, 2, 2))
    parts.extend(DragonPart(entity, "wing", cx + side * co * 4.5, cy + 2, 4, 2)
                 for side in (-1, 1))
    return parts


def damage_targets(entity):
    getter = getattr(entity, "get_damage_parts", None)
    return getter() if callable(getter) else (entity,)
