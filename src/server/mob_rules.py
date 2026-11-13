"""Minecraft 1.8.9 light rules, shared by monster AI and natural spawning."""
import math
import random


def skylight_subtracted(world):
    # WorldProvider.calculateCelestialAngle / World.calculateSkylightSubtracted.
    angle = (float(world.world_time) / 24000.0 - 0.25) % 1.0
    original = angle
    angle = 1.0 - (math.cos(angle * math.pi) + 1.0) / 2.0
    angle = original + (angle - original) / 3.0
    light = max(0.0, min(1.0, math.cos(angle * math.tau) * 2.0 + 0.5))
    weather = getattr(world, "weather", "clear")
    weather = getattr(weather, "value", weather)
    if weather in {"rain", "thunder"}:
        light *= 1.0 - 5.0 / 16.0
    if weather == "thunder":
        light *= 1.0 - 5.0 / 16.0
    return int((1.0 - light) * 11.0)


def local_light(world, x, y):
    return max(0, world.get_sky_light(x, y) - skylight_subtracted(world),
               world.get_block_light(x, y))


def brightness(entity):
    level = local_light(entity.world, math.floor(entity.x + entity.width / 2),
                        math.floor(entity.y + entity.height * 0.85))
    # WorldProvider.generateLightBrightnessTable (ambientLight=0).
    darkness = 1.0 - level / 15.0
    return (1.0 - darkness) / (darkness * 3.0 + 1.0)


def peaceful(world):
    difficulty = getattr(world, "difficulty", getattr(world.server, "difficulty", "normal"))
    difficulty = getattr(difficulty, "name_id", getattr(difficulty, "value", difficulty))
    return difficulty in (0, "peaceful", "PEACEFUL")


def tick_sunlight_burning(entity):
    world = entity.world
    if getattr(world, "id_name", None) != "overworld" or not getattr(world.attribute, "HAS_SKY", True):
        return
    if skylight_subtracted(world) >= 4:
        return
    x, y = math.floor(entity.x + entity.width / 2), math.floor(entity.y + entity.height * 0.85)
    light = brightness(entity)
    weather = getattr(world, "weather", "clear")
    if getattr(weather, "value", weather) != "clear":
        return
    if light > 0.5 and world.get_sky_light(x, y) == 15 and random.random() * 30 < (light - 0.4) * 2:
        entity.set_seconds_on_fire(8)
