# Commented and arranged by ChatGPT

from __future__ import annotations


ORB_VALUES = (2477, 1237, 617, 307, 149, 73, 37, 17, 7, 3, 1)


def experience_to_next_level(level: int) -> int:
    level = max(0, int(level))
    if level >= 30:
        return 112 + (level - 30) * 9
    if level >= 15:
        return 37 + (level - 15) * 5
    return 7 + level * 2


def total_experience_for_level(level: int) -> int:
    level = max(0, int(level))
    if level >= 32:
        return int(4.5 * level * level - 162.5 * level + 2220)
    if level >= 17:
        return int(2.5 * level * level - 40.5 * level + 360)
    return level * level + 6 * level


def split_experience(amount: int) -> list[int]:
    remaining = max(0, int(amount))
    result: list[int] = []
    while remaining > 0:
        value = next(value for value in ORB_VALUES if remaining >= value)
        result.append(value)
        remaining -= value
    return result


def experience_orb_icon(value: int) -> int:
    value = max(0, int(value))
    for reverse_index, threshold in enumerate(ORB_VALUES):
        if value >= threshold:
            return len(ORB_VALUES) - reverse_index - 1
    return 0
