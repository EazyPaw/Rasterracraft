"""Reusable entity AI primitives.

The game keeps entity physics in :mod:`resources.server.entity`, while this
module owns the Minecraft-style goal/selector layer.  Concrete mobs only
need to expose attributes such as ``move_speed`` and ``interact_range`` and
implement their damage method.
"""

import math
import random
from dataclasses import dataclass
from enum import Enum


class GoalFlag(Enum):
    MOVE = "move"
    LOOK = "look"
    JUMP = "jump"
    TARGET = "target"


class Goal:
    """One interruptible unit of entity behaviour."""

    flags: frozenset[GoalFlag] = frozenset()
    tick_every_tick = True
    interruptible = True

    def __init__(self, ai: "EntityAI"):
        self.ai = ai

    @property
    def entity(self):
        return self.ai.entity

    def can_use(self) -> bool:
        return False

    def can_continue(self) -> bool:
        return self.can_use()

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def tick(self) -> None:
        pass


@dataclass
class _WrappedGoal:
    priority: int
    order: int
    goal: Goal
    running: bool = False


class GoalSelector:
    """Select goals by priority while enforcing controller flag conflicts."""

    def __init__(self):
        self._goals: list[_WrappedGoal] = []
        self._next_order = 0

    def add(self, priority: int, goal: Goal) -> Goal:
        self._goals.append(_WrappedGoal(int(priority), self._next_order, goal))
        self._next_order += 1
        self._goals.sort(key=lambda wrapped: (wrapped.priority, wrapped.order))
        return goal

    def _stop(self, wrapped: _WrappedGoal) -> None:
        if wrapped.running:
            wrapped.running = False
            wrapped.goal.stop()

    def tick(self, recalculate: bool) -> None:
        for wrapped in self._goals:
            if wrapped.running and not wrapped.goal.can_continue():
                self._stop(wrapped)

        if recalculate:
            for candidate in self._goals:
                if candidate.running or not candidate.goal.can_use():
                    continue
                conflicts = [
                    running for running in self._goals
                    if running.running
                    and running.goal.flags.intersection(candidate.goal.flags)
                ]
                if conflicts and not all(
                    candidate.priority < running.priority and running.goal.interruptible
                    for running in conflicts
                ):
                    continue
                for running in conflicts:
                    self._stop(running)
                candidate.running = True
                candidate.goal.start()

        for wrapped in self._goals:
            if wrapped.running and (recalculate or wrapped.goal.tick_every_tick):
                wrapped.goal.tick()


class MoveControl:
    """Horizontal controller driven by the entity's movement attributes."""

    def __init__(self, ai: "EntityAI"):
        self.ai = ai
        self.wanted_x: float | None = None
        self.speed_modifier = 1.0

    @property
    def entity(self):
        return self.ai.entity

    def move_to(self, x: float, speed_modifier: float = 1.0) -> None:
        self.wanted_x = float(x)
        self.speed_modifier = max(0.0, float(speed_modifier))

    def stop(self) -> None:
        self.wanted_x = None

    def tick(self) -> None:
        wanted_x = self.wanted_x
        self.wanted_x = None
        if wanted_x is None:
            return

        entity = self.entity
        delta = wanted_x - (entity.x + entity.width * 0.5)
        if abs(delta) <= 0.08:
            return

        direction = 1 if delta > 0 else -1
        entity.facing = 1 if direction > 0 else 0
        if not self.ai.can_move(direction):
            self.ai.on_blocked(direction)
            return
        entity.motion.x += entity.get_move_acceleration() * self.speed_modifier * direction

        # Request a jump only when the horizontal path is genuinely blocked
        # and the common movement layer cannot step onto that obstacle.  Low
        # slabs/snow/custom shapes are crossed directly via max_step_height.
        probe_dx = direction * max(abs(entity.motion.x), 0.16)
        _, blocked = entity._sweep_x(probe_dx)
        if entity.on_ground and blocked and not entity.can_step_up(probe_dx):
            self.ai.jump_control.jump()


class LookControl:
    def __init__(self, ai: "EntityAI"):
        self.ai = ai
        self.wanted: tuple[float, float] | None = None

    @property
    def entity(self):
        return self.ai.entity

    def look_at(self, x: float, y: float) -> None:
        self.wanted = (float(x), float(y))

    def tick(self) -> None:
        wanted = self.wanted
        self.wanted = None
        if wanted is None:
            if hasattr(self.entity, "look_angle"):
                self.entity.look_angle *= 0.8
            return

        entity = self.entity
        center_x = entity.x + entity.width * 0.5
        head_y = entity.y + entity.height * 0.86
        dx = wanted[0] - center_x
        dy = wanted[1] - head_y
        if abs(dx) > 0.05:
            entity.facing = 1 if dx > 0 else 0
        if hasattr(entity, "look_angle"):
            entity.look_angle = max(
                -45.0,
                min(60.0, math.degrees(math.atan2(dy, max(abs(dx), 0.01)))),
            )


class JumpControl:
    def __init__(self, ai: "EntityAI"):
        self.ai = ai
        self.wanted = False

    @property
    def entity(self):
        return self.ai.entity

    def jump(self) -> None:
        self.wanted = True

    def tick(self) -> None:
        if not self.wanted:
            return
        self.wanted = False
        if self.entity.in_fluid:
            self.entity.motion.y = max(self.entity.motion.y, 0.12)
        else:
            self.entity.jump()


class EntityAI:
    """Base AI with target/action selectors and shared movement controls."""

    recalculate_interval = 2

    def __init__(self, entity):
        self.entity = entity
        self.move_control = MoveControl(self)
        self.look_control = LookControl(self)
        self.jump_control = JumpControl(self)
        self.target_selector = GoalSelector()
        self.goal_selector = GoalSelector()
        self._tick_count = 0
        self.register_goals()

    def register_goals(self) -> None:
        """Subclasses register target and action goals here."""

    def can_move(self, direction: int) -> bool:
        """Return whether the controller may accelerate in ``direction``."""
        return True

    def on_blocked(self, direction: int) -> None:
        """Controller callback used by goals that need to choose a new path."""

    def on_hurt(self, source) -> None:
        """Optional damage notification for panic/retaliation behaviours."""

    def tick(self) -> None:
        if getattr(self.entity, "no_ai", False):
            self.move_control.stop()
            self.look_control.wanted = None
            self.jump_control.wanted = False
            return

        self._tick_count += 1
        recalculate = (
            self._tick_count + (self.entity.uuid.int & 1)
        ) % self.recalculate_interval == 0
        self.target_selector.tick(recalculate)
        self.goal_selector.tick(recalculate)
        self.move_control.tick()
        self.look_control.tick()
        self.jump_control.tick()


class NearestPlayerTargetGoal(Goal):
    flags = frozenset({GoalFlag.TARGET})

    def __init__(self, ai: "HostileMobAI"):
        super().__init__(ai)
        self.candidate = None
        self.scan_cooldown = 0

    def _nearest(self):
        players = getattr(getattr(self.entity.world, "server", None), "players", ())
        candidates = [player for player in players if self.ai.can_target(player)]
        if not candidates:
            return None
        return min(candidates, key=lambda player: self.ai.distance_squared_to(player))

    def can_use(self) -> bool:
        self.candidate = self._nearest()
        return self.candidate is not None

    def can_continue(self) -> bool:
        return self.ai.can_target(self.ai.get_target(), extra_range=8.0)

    def start(self) -> None:
        self.ai.set_target(self.candidate)
        self.scan_cooldown = 10

    def stop(self) -> None:
        self.ai.set_target(None)
        self.candidate = None

    def tick(self) -> None:
        self.scan_cooldown -= 1
        if self.scan_cooldown > 0:
            return
        self.scan_cooldown = 10
        nearest = self._nearest()
        current = self.ai.get_target()
        if nearest is not None and (
            current is None
            or self.ai.distance_squared_to(nearest) + 1.0
            < self.ai.distance_squared_to(current)
        ):
            self.ai.set_target(nearest)


class FloatGoal(Goal):
    flags = frozenset({GoalFlag.MOVE, GoalFlag.JUMP})

    def can_use(self) -> bool:
        return self.entity.in_fluid

    def tick(self) -> None:
        self.ai.jump_control.jump()
        target = self.ai.get_target()
        if target is not None:
            self.ai.move_control.move_to(target.x + target.width * 0.5, 0.8)


class MeleeAttackGoal(Goal):
    flags = frozenset({GoalFlag.MOVE, GoalFlag.LOOK})

    def can_use(self) -> bool:
        return self.ai.can_target(self.ai.get_target(), extra_range=8.0)

    def tick(self) -> None:
        target = self.ai.get_target()
        if target is None:
            return
        target_x = target.x + target.width * 0.5
        target_y = target.y + target.height * 0.75
        self.ai.look_control.look_at(target_x, target_y)
        self.ai.move_control.move_to(target_x, 1.0)

        if self.ai.is_in_attack_reach(target):
            self.ai.try_attack(target)

    def stop(self) -> None:
        self.ai.move_control.stop()


class RandomStrollGoal(Goal):
    flags = frozenset({GoalFlag.MOVE})

    def __init__(self, ai: "EntityAI"):
        super().__init__(ai)
        self.wanted_x = 0.0
        self.remaining_ticks = 0

    def can_use(self) -> bool:
        if self.ai.get_target() is not None or random.randrange(120) != 0:
            return False
        direction = random.choice((-1, 1))
        self.wanted_x = self.entity.x + direction * random.uniform(3.0, 7.0)
        self.remaining_ticks = random.randint(40, 90)
        return True

    def can_continue(self) -> bool:
        return self.ai.get_target() is None and self.remaining_ticks > 0

    def tick(self) -> None:
        self.remaining_ticks -= 1
        self.ai.move_control.move_to(self.wanted_x, 0.65)

    def stop(self) -> None:
        self.ai.move_control.stop()


class LookAtPlayerGoal(Goal):
    flags = frozenset({GoalFlag.LOOK})

    def __init__(self, ai: "EntityAI"):
        super().__init__(ai)
        self.target = None
        self.remaining_ticks = 0

    def can_use(self) -> bool:
        if self.ai.get_target() is not None or random.randrange(100) != 0:
            return False
        players = getattr(getattr(self.entity.world, "server", None), "players", ())
        nearby = [player for player in players if self.ai.can_look_at(player)]
        if not nearby:
            return False
        self.target = min(nearby, key=lambda player: self.ai.distance_squared_to(player))
        self.remaining_ticks = random.randint(40, 80)
        return True

    def can_continue(self) -> bool:
        return self.remaining_ticks > 0 and self.ai.can_look_at(self.target)

    def tick(self) -> None:
        self.remaining_ticks -= 1
        self.ai.look_control.look_at(
            self.target.x + self.target.width * 0.5,
            self.target.y + self.target.height * 0.75,
        )

    def stop(self) -> None:
        self.target = None


class RandomLookAroundGoal(Goal):
    flags = frozenset({GoalFlag.LOOK})

    def __init__(self, ai: "EntityAI"):
        super().__init__(ai)
        self.direction = 1
        self.remaining_ticks = 0

    def can_use(self) -> bool:
        if random.randrange(100) != 0:
            return False
        self.direction = random.choice((-1, 1))
        self.remaining_ticks = random.randint(20, 40)
        return True

    def can_continue(self) -> bool:
        return self.remaining_ticks > 0

    def tick(self) -> None:
        self.remaining_ticks -= 1
        self.ai.look_control.look_at(
            self.entity.x + self.entity.width * 0.5 + self.direction * 4.0,
            self.entity.y + self.entity.height * 0.85,
        )


class PanicGoal(Goal):
    """Run away briefly after receiving damage."""

    flags = frozenset({GoalFlag.MOVE})

    def can_use(self) -> bool:
        return self.ai.panic_ticks > 0

    def can_continue(self) -> bool:
        return self.ai.panic_ticks > 0

    def tick(self) -> None:
        self.ai.panic_ticks -= 1
        direction = self.ai.panic_direction
        target_x = self.entity.x + direction * 8.0
        self.ai.move_control.move_to(
            target_x,
            float(getattr(self.entity, "panic_speed_modifier", 1.25)),
        )

    def stop(self) -> None:
        self.ai.move_control.stop()


class TemptGoal(Goal):
    """Follow the nearest player holding a configured food item."""

    flags = frozenset({GoalFlag.MOVE, GoalFlag.LOOK})

    def __init__(self, ai: "PassiveMobAI"):
        super().__init__(ai)
        self.player = None

    def _nearest(self):
        candidates = [
            player for player in self.ai.iter_players()
            if self.ai.is_tempting(player)
        ]
        if not candidates:
            return None
        return min(candidates, key=self.ai.distance_squared_to)

    def can_use(self) -> bool:
        self.player = self._nearest()
        return self.player is not None

    def can_continue(self) -> bool:
        return self.player is not None and self.ai.is_tempting(self.player)

    def tick(self) -> None:
        player = self.player
        if player is None:
            return
        target_x = player.x + player.width * 0.5
        self.ai.look_control.look_at(target_x, player.y + player.height * 0.75)
        if self.ai.distance_squared_to(player) > 1.6 * 1.6:
            self.ai.move_control.move_to(
                target_x,
                float(getattr(self.entity, "tempt_speed_modifier", 1.1)),
            )

    def stop(self) -> None:
        self.player = None
        self.ai.move_control.stop()


class BreedGoal(Goal):
    """Bring two in-love adults together; the entity owns offspring state."""

    flags = frozenset({GoalFlag.MOVE, GoalFlag.LOOK})

    def __init__(self, ai: "PassiveMobAI"):
        super().__init__(ai)
        self.mate = None

    def _nearest_mate(self):
        finder = getattr(self.entity, "find_breeding_mate", None)
        return finder() if callable(finder) else None

    def can_use(self) -> bool:
        if int(getattr(self.entity, "love_ticks", 0)) <= 0:
            return False
        self.mate = self._nearest_mate()
        return self.mate is not None

    def can_continue(self) -> bool:
        return (
            self.mate is not None
            and int(getattr(self.entity, "love_ticks", 0)) > 0
            and int(getattr(self.mate, "love_ticks", 0)) > 0
            and not getattr(self.mate, "removed", False)
        )

    def tick(self) -> None:
        mate = self.mate
        if mate is None:
            return
        mate_x = mate.x + mate.width * 0.5
        self.ai.look_control.look_at(mate_x, mate.y + mate.height * 0.75)
        if self.ai.distance_squared_to(mate) > 1.25 * 1.25:
            self.ai.move_control.move_to(mate_x, 1.0)
            return
        breeder = getattr(self.entity, "try_breed_with", None)
        if callable(breeder):
            breeder(mate)

    def stop(self) -> None:
        self.mate = None
        self.ai.move_control.stop()


class FollowParentGoal(Goal):
    flags = frozenset({GoalFlag.MOVE})

    def __init__(self, ai: "PassiveMobAI"):
        super().__init__(ai)
        self.parent = None

    def can_use(self) -> bool:
        finder = getattr(self.entity, "find_nearest_adult", None)
        if not getattr(self.entity, "is_baby", False) or not callable(finder):
            return False
        self.parent = finder(8.0)
        return self.parent is not None and self.ai.distance_squared_to(self.parent) > 2.0 * 2.0

    def can_continue(self) -> bool:
        distance = self.ai.distance_squared_to(self.parent)
        return self.parent is not None and 1.5 * 1.5 < distance <= 10.0 * 10.0

    def tick(self) -> None:
        self.ai.move_control.move_to(
            self.parent.x + self.parent.width * 0.5,
            float(getattr(self.entity, "follow_parent_speed_modifier", 1.1)),
        )

    def stop(self) -> None:
        self.parent = None
        self.ai.move_control.stop()


class EatGrassGoal(Goal):
    """Forty-tick sheep grazing action with a synced head animation."""

    flags = frozenset({GoalFlag.MOVE, GoalFlag.LOOK})

    def __init__(self, ai: "PassiveMobAI"):
        super().__init__(ai)
        self.remaining_ticks = 0

    def can_use(self) -> bool:
        checker = getattr(self.entity, "can_eat_grass", None)
        chance = 50 if getattr(self.entity, "is_baby", False) else 1000
        return callable(checker) and random.randrange(chance) == 0 and checker()

    def can_continue(self) -> bool:
        return self.remaining_ticks > 0

    def start(self) -> None:
        self.remaining_ticks = 40
        self.entity.eat_animation_ticks = 40

    def tick(self) -> None:
        self.remaining_ticks -= 1
        self.entity.eat_animation_ticks = self.remaining_ticks
        if self.remaining_ticks == 4:
            eater = getattr(self.entity, "eat_grass", None)
            if callable(eater):
                eater()

    def stop(self) -> None:
        self.entity.eat_animation_ticks = 0


class PassiveMobAI(EntityAI):
    """Shared non-hostile animal behaviour and terrain safety policy."""

    def __init__(self, entity):
        self.panic_ticks = 0
        self.panic_direction = random.choice((-1, 1))
        super().__init__(entity)

    def register_goals(self) -> None:
        self.goal_selector.add(0, FloatGoal(self))
        self.goal_selector.add(1, PanicGoal(self))
        self.goal_selector.add(2, BreedGoal(self))
        self.goal_selector.add(3, TemptGoal(self))
        self.goal_selector.add(4, FollowParentGoal(self))
        self.goal_selector.add(7, RandomStrollGoal(self))
        self.goal_selector.add(8, LookAtPlayerGoal(self))
        self.goal_selector.add(8, RandomLookAroundGoal(self))

    def iter_players(self):
        players = getattr(getattr(self.entity.world, "server", None), "players", ())
        return (
            player for player in players
            if getattr(player, "world", None) is self.entity.world
            and int(getattr(player, "z", 0)) == int(getattr(self.entity, "z", 0))
            and getattr(player, "health", 0) > 0
        )

    def distance_squared_to(self, other) -> float:
        if other is None:
            return math.inf
        dx = (self.entity.x + self.entity.width * 0.5) - (other.x + other.width * 0.5)
        dy = (self.entity.y + self.entity.height * 0.5) - (other.y + other.height * 0.5)
        return dx * dx + dy * dy

    def get_target(self):
        return None

    def can_look_at(self, player) -> bool:
        return player is not None and self.distance_squared_to(player) <= 6.0 * 6.0

    @staticmethod
    def _held_item_id(player) -> str:
        try:
            slot = max(0, min(len(player.inventory) - 1, int(player.selected_slot)))
            stack = player.inventory[slot]
            return "air" if stack.is_empty() else str(stack.material.name_id)
        except (AttributeError, IndexError, TypeError, ValueError):
            return "air"

    def is_tempting(self, player) -> bool:
        if self.distance_squared_to(player) > 10.0 * 10.0:
            return False
        return self._held_item_id(player) in set(getattr(self.entity, "tempt_items", ()))

    def on_hurt(self, source) -> None:
        self.panic_ticks = random.randint(80, 140)
        if source is not None and hasattr(source, "x"):
            source_center = source.x + getattr(source, "width", 0.0) * 0.5
            entity_center = self.entity.x + self.entity.width * 0.5
            self.panic_direction = 1 if entity_center >= source_center else -1
        else:
            self.panic_direction = random.choice((-1, 1))

    def can_move(self, direction: int) -> bool:
        entity = self.entity
        if entity.in_fluid:
            return True
        world = entity.world
        z = int(getattr(entity, "z", 0))
        probe_x = entity.x + entity.width * 0.5 + direction * (entity.width * 0.5 + 0.28)
        body_y = math.floor(entity.y + min(entity.height * 0.35, 0.45))
        try:
            body_block = world.get_block(math.floor(probe_x), body_y, z)
            if getattr(body_block, "is_fluid", False):
                return False
            floor_y = math.floor(entity.y - 0.06)
            for drop in range(0, 4):
                support = world.get_block(math.floor(probe_x), floor_y - drop, z)
                getter = getattr(support, "get_collision_box", None)
                shape = getter() if callable(getter) else getattr(support, "collision_box", None)
                if shape:
                    return True
        except (AttributeError, IndexError, TypeError, ValueError):
            return False
        return False

    def on_blocked(self, direction: int) -> None:
        # A blocked stroll will expire naturally; panic reverses so an animal
        # does not keep pressing into a cliff edge for its whole panic window.
        if self.panic_ticks > 0:
            self.panic_direction = -direction


class ChickenAI(PassiveMobAI):
    pass


class CowAI(PassiveMobAI):
    pass


class PigAI(PassiveMobAI):
    pass


class SheepAI(PassiveMobAI):
    def register_goals(self) -> None:
        super().register_goals()
        self.goal_selector.add(5, EatGrassGoal(self))


class HostileMobAI(EntityAI):
    """Common AI implementation for mobs that actively attack players."""

    def register_goals(self) -> None:
        self.target_selector.add(2, NearestPlayerTargetGoal(self))
        self.goal_selector.add(0, FloatGoal(self))
        self.goal_selector.add(2, MeleeAttackGoal(self))
        self.goal_selector.add(7, RandomStrollGoal(self))
        self.goal_selector.add(8, LookAtPlayerGoal(self))
        self.goal_selector.add(8, RandomLookAroundGoal(self))

    def distance_squared_to(self, other) -> float:
        if other is None:
            return math.inf
        dx = (self.entity.x + self.entity.width * 0.5) - (other.x + other.width * 0.5)
        dy = (self.entity.y + self.entity.height * 0.5) - (other.y + other.height * 0.5)
        return dx * dx + dy * dy

    def can_target(self, player, extra_range: float = 0.0) -> bool:
        if player is None or getattr(player, "world", None) is not self.entity.world:
            return False
        if getattr(player, "health", 0) <= 0 or getattr(player, "removed", False):
            return False
        if int(getattr(self.entity, "z", 0)) != int(getattr(player, "z", 0)):
            return False
        mode = getattr(getattr(player, "gamemode", None), "name_id", "survival")
        if mode in {"creative", "spectator"}:
            return False
        distance = float(getattr(self.entity, "follow_range", 35.0)) + float(extra_range)
        return self.distance_squared_to(player) <= distance * distance

    def can_look_at(self, player) -> bool:
        return (
            player is not None
            and getattr(player, "world", None) is self.entity.world
            and self.distance_squared_to(player) <= 8.0 * 8.0
        )

    def get_target(self):
        target_uuid = getattr(self.entity, "target_uuid", None)
        if target_uuid is None:
            return None
        players = getattr(getattr(self.entity.world, "server", None), "players", ())
        for player in players:
            if str(getattr(player, "uuid", "")) == target_uuid:
                return player
        return None

    def set_target(self, target) -> None:
        self.entity.target_uuid = None if target is None else str(target.uuid)

    def is_in_attack_reach(self, target) -> bool:
        horizontal_gap = max(
            target.x - (self.entity.x + self.entity.width),
            self.entity.x - (target.x + target.width),
            0.0,
        )
        vertical_overlap = min(
            self.entity.y + self.entity.height,
            target.y + target.height,
        ) - max(self.entity.y, target.y)
        reach = max(0.0, float(getattr(self.entity, "interact_range", 1.0)))
        return horizontal_gap <= reach and vertical_overlap > 0.25

    def try_attack(self, target) -> bool:
        attack = getattr(self.entity, "try_attack", None)
        return bool(callable(attack) and attack(target))


class ZombieAI(HostileMobAI):
    """The default hostile goal set used by zombies."""

    def register_goals(self) -> None:
        # Keep this override as the extension point for zombie-specific goals
        # (sunlight avoidance, reinforcement calls, equipment, ...), while
        # retaining the shared hostile target/attack/idle behaviour today.
        super().register_goals()
