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

    def __init__(self, ai: "HostileMobAI"):
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

    def __init__(self, ai: "HostileMobAI"):
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

    def __init__(self, ai: "HostileMobAI"):
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
