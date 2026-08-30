# Commented and arranged by ChatGPT
import math
import time
from abc import ABC
from dataclasses import dataclass
from typing import Iterable

import pygame

from src.server.utils import client_method


def _approach(current: float, target: float, strength: float) -> float:
    """普通数值缓动：每帧向目标值靠近一小段，避免动作突然跳变。"""
    return current + (target - current) * strength


def _shortest_angle_delta(current: float, target: float) -> float:
    """计算两个角度之间最短的旋转差值，避免从 359 度绕远路转到 0 度。"""
    return (target - current + 180.0) % 360.0 - 180.0


def _approach_angle(current: float, target: float, strength: float) -> float:
    """角度专用缓动，内部使用最短旋转路径。"""
    return current + _shortest_angle_delta(current, target) * strength


@dataclass(frozen=True)
class Pose:
    """某个身体部件在当前动画帧中应该达到的姿态。"""

    # anchor 是"关节"在实体坐标中的位置，例如肩膀、髋部、脖子。
    anchor: tuple[float, float]
    # pivot 是这张贴图内部的旋转中心，单位是皮肤像素。
    pivot: tuple[float, float]
    # angle 是围绕 pivot 旋转的角度。
    angle: float = 0.0
    visible: bool = True
    flip_x: bool = False


class BodyPart:
    """带贴图、关节锚点和旋转枢轴的身体部件。"""

    def __init__(
        self,
        name: str,
        texture: pygame.Surface,
        anchor: tuple[float, float],
        pivot: tuple[float, float],
        angle: float = 0.0,
        layer: int = 0,
        show: bool = True,
    ):
        self.name = name
        # original_texture 永远保存未缩放、未旋转的原始皮肤切片。
        self.original_texture = texture.copy()

        # 当前姿态与目标姿态分开保存，tick() 会在二者之间做平滑过渡。
        self.anchor = anchor
        self.target_anchor = anchor
        self.pivot = pivot
        self.target_pivot = pivot
        self.angle = angle
        self.target_angle = angle
        self.layer = layer
        self.show = show
        self.target_show = show
        self.flip_x = False
        self.target_flip_x = False

        self.render_scale = 1.0

        # base_texture 是缩放后的贴图；texture 是在 base_texture 基础上旋转后的贴图。
        self.base_texture = self.original_texture
        self.texture = self.original_texture
        self.size = self.original_texture.get_size()
        # 用这个 key 避免每帧重复缩放/旋转同一张贴图。
        self._last_transform_key = None
        self._render_pivot = pivot

    def set_source_texture(self, texture: pygame.Surface):
        """切换身体部件使用的皮肤切片，主要用于左右朝向时换侧面贴图。"""
        if texture is self.original_texture:
            return
        self.original_texture = texture.copy()
        self._last_transform_key = None

    def set_pose(self, pose: Pose):
        """设置目标姿态；真正显示出来的姿态会在 tick() 里缓动过去。"""
        self.target_anchor = pose.anchor
        self.target_pivot = pose.pivot
        self.target_angle = pose.angle
        self.target_show = pose.visible
        self.target_flip_x = pose.flip_x

    def tick(self, smoothness: float):
        """每帧更新部件姿态，让关节位置和角度平滑接近目标值。"""
        self.anchor = (
            _approach(self.anchor[0], self.target_anchor[0], smoothness),
            _approach(self.anchor[1], self.target_anchor[1], smoothness),
        )
        self.pivot = (
            _approach(self.pivot[0], self.target_pivot[0], smoothness),
            _approach(self.pivot[1], self.target_pivot[1], smoothness),
        )
        self.angle = _approach_angle(self.angle, self.target_angle, smoothness)
        self.show = self.target_show
        self.flip_x = self.target_flip_x

    def rebuild_texture(self, scale: float):
        """按当前渲染缩放和实体大小生成最终贴图。"""
        effective_scale = scale * self.render_scale
        width = max(1, round(self.original_texture.get_width() * effective_scale))
        height = max(1, round(self.original_texture.get_height() * effective_scale))
        key = (
            width,
            height,
            round(self.angle, 2),
            self.flip_x,
            round(self.render_scale, 4),
            round(self.pivot[0], 4),
            round(self.pivot[1], 4),
        )
        if key == self._last_transform_key:
            return

        base = pygame.transform.scale(self.original_texture, (width, height))
        if self.flip_x:
            base = pygame.transform.flip(base, True, False)

        self.base_texture = base
        self.texture = pygame.transform.rotate(base, self.angle)
        self.size = self.texture.get_size()
        # 如果贴图被水平翻转，pivot 的 x 坐标也要镜像，否则关节会错位。
        self._render_pivot = (
            base.get_width() - self.pivot[0] * effective_scale
            if self.flip_x
            else self.pivot[0] * effective_scale,
            self.pivot[1] * effective_scale,
        )
        self._last_transform_key = key

    def draw(
        self,
        render,
        entity_pos: tuple[float, float],
        scale: float,
        tint=(255, 255, 255),
    ):
        """把身体部件画到屏幕上，并保证 pivot 精确贴到 anchor。"""
        if not self.show:
            return

        self.rebuild_texture(scale)

        anchor_world = (entity_pos[0] + self.anchor[0], entity_pos[1] + self.anchor[1])
        anchor_screen = pygame.Vector2(render.trans_world_location(anchor_world))
        pivot = pygame.Vector2(self._render_pivot)

        source_center = pygame.Vector2(
            self.base_texture.get_width() * 0.5,
            self.base_texture.get_height() * 0.5,
        )

        # pygame.transform.rotate 会围绕贴图中心旋转，但我们需要围绕关节 pivot 旋转。
        # 这里先算出"pivot 相对贴图中心"的向量，旋转后再反推出整张贴图的左上角。
        # 注意：Pygame 的屏幕 y 轴向下，所以这里用 -self.angle 来匹配世界坐标的视觉方向。
        pivot_from_center = pivot - source_center
        rotated_pivot_from_center = pivot_from_center.rotate(-self.angle)
        rotated_center = pygame.Vector2(
            self.texture.get_width() * 0.5,
            self.texture.get_height() * 0.5,
        )
        top_left = anchor_screen - rotated_center - rotated_pivot_from_center

        texture = render.get_tinted_surface(self.texture, tint)
        render.blit(texture, (round(top_left.x), round(top_left.y)))


class EntitySkeleton(ABC):
    """实体骨架基类：负责位置插值、缩放缓存、绘制顺序和朝向管理。"""

    LEFT = 0
    RIGHT = 1

    _instances = []

    def __init__(self, client, texture: str, entity):
        self.client = client
        self.texture: pygame.Surface = client.resources_manager.get_texture_img(texture)
        self.entity = entity
        self.body: dict[str, BodyPart] = {}
        self.size = 1.0
        self.last_size = None

        # 朝向
        self.facing = self.RIGHT

        # 本地固定模式：绕过服务器位置插值，不走普通实体相机变换。
        self._pinned = False
        # 模型视觉中心（相对于实体坐标），子类在 __init__ 中覆写
        self._visual_center = (0.5, 0.5)

        # 游戏逻辑是固定 tick 更新，渲染帧率更高；下面这些值用于在两个 tick 之间插值。
        self._prev_x = entity.x
        self._prev_y = entity.y
        self._target_x = entity.x
        self._target_y = entity.y
        self._render_x = entity.x
        self._render_y = entity.y
        self._tick_start = time.perf_counter()
        self._tick_duration = 1.0 / max(getattr(client, "rate", 20), 1)

        EntitySkeleton._instances.append(self)

    @classmethod
    def get_all_instances(cls):
        return cls._instances

    def _parts_in_draw_order(self) -> Iterable[BodyPart]:
        """按 layer 从后到前绘制，保证后侧手脚在身体后面。"""
        return sorted(self.body.values(), key=lambda part: part.layer)

    # ---------- 朝向 ----------

    def _facing_sign(self) -> int:
        """把朝向转换成 -1/1，方便所有动作公式左右镜像。"""
        return 1 if self.facing == self.RIGHT else -1

    def _update_facing(self):
        """根据水平速度更新朝向。子类可覆写以加入额外逻辑（如鼠标指向）。"""
        motion_x = getattr(self.entity.motion, "x", 0.0)
        if abs(motion_x) > 0.02:
            self.facing = self.RIGHT if motion_x > 0 else self.LEFT

    # ---------- 插值 ----------

    def _update_interpolation(self):
        """自适应插值：根据实际 tick 间隔平滑位置，减少高速运动时的错位感。"""
        now = time.perf_counter()

        if self.entity.x != self._target_x or self.entity.y != self._target_y:
            # 用实际时间间隔自适应插值时长，避免固定时长与实际 tick 不一致
            elapsed_since_last = now - self._tick_start
            if elapsed_since_last > 0.001:
                self._tick_duration = elapsed_since_last
            self._tick_duration = min(max(self._tick_duration, 0.016), 0.2)

            # 以前一个目标位置为起点（不用当前渲染位置），保证插值始终完整
            self._prev_x = self._target_x
            self._prev_y = self._target_y
            self._target_x = self.entity.x
            self._target_y = self.entity.y
            self._tick_start = now

        elapsed = now - self._tick_start
        progress = min(max(elapsed / self._tick_duration, 0.0), 1.0)
        smooth_progress = progress * progress * (3.0 - 2.0 * progress)
        self._render_x = (
            self._prev_x + (self._target_x - self._prev_x) * smooth_progress
        )
        self._render_y = (
            self._prev_y + (self._target_y - self._prev_y) * smooth_progress
        )

    def conv_size(self):
        """渲染缩放或实体视觉大小变化时，重建所有部件贴图。"""
        scale = self.client.render.trans_scale * self.size
        for part in self.body.values():
            part.rebuild_texture(scale)
        self.last_size = self.client.render.trans_scale

    def _part_smoothness(self, part: BodyPart) -> float:
        return 0.28

    def update(self):
        """每帧更新骨架位置、缩放缓存和各部件姿态。"""
        self._update_interpolation()
        if self.last_size != self.client.render.trans_scale:
            self.conv_size()
        for part in self.body.values():
            part.tick(self._part_smoothness(part))

    # ---------- 绘制 ----------

    def _draw_part_at_screen(
        self, part: BodyPart, anchor_screen: tuple[float, float], tint=(255, 255, 255)
    ):
        """绕过世界坐标变换，直接在屏幕坐标绘制本地主玩家部件。"""
        if not part.show:
            return
        anchor = pygame.Vector2(anchor_screen)
        pivot = pygame.Vector2(part._render_pivot)
        source_center = pygame.Vector2(
            part.base_texture.get_width() * 0.5,
            part.base_texture.get_height() * 0.5,
        )
        pivot_from_center = pivot - source_center
        rotated_pivot_from_center = pivot_from_center.rotate(-part.angle)
        rotated_center = pygame.Vector2(
            part.texture.get_width() * 0.5,
            part.texture.get_height() * 0.5,
        )
        top_left = anchor - rotated_center - rotated_pivot_from_center
        texture = self.client.render.get_tinted_surface(part.texture, tint)
        self.client.render.blit(texture, (round(top_left.x), round(top_left.y)))

    def draw(self):
        """按层级绘制实体所有可见部件。_pinned 实体不使用服务器位置插值。"""
        scale = self.client.render.trans_scale * self.size
        render = self.client.render
        tint_x = self.entity.x + getattr(self.entity, "width", 1.0) * 0.5
        tint_y = self.entity.y + self._visual_center[1]
        tint = render.get_world_light_tint(tint_x, tint_y)

        if getattr(self.entity, "hurt_time", 0) > 0:
            tint = (255, 72, 72)

        if self._pinned:
            bs = render.block_size
            # 主玩家仍绕过服务器位置插值，但要与鼠标引导的镜头
            # 使用相反屏幕偏移；居中模式下该偏移始终为零。
            screen_cx, screen_cy = render.camera.get_player_screen_center(
                (render.SCREEN_WIDTH, render.SCREEN_HEIGHT), bs
            )
            vc_x, vc_y = self._visual_center
            for part in self._parts_in_draw_order():
                part.rebuild_texture(scale)
                ax = screen_cx + (part.anchor[0] - vc_x) * bs
                ay = screen_cy - (part.anchor[1] - vc_y) * bs
                self._draw_part_at_screen(part, (ax, ay), tint)
        else:
            entity_pos = (self._render_x, self._render_y)
            for part in self._parts_in_draw_order():
                part.draw(render, entity_pos, scale, tint)

    def get_hitbox_render_position(self) -> tuple[float, float]:
        """返回与当前 Skeleton 帧完全一致的判定框世界坐标。"""
        return self._render_x, self._render_y

    def draw_hitbox(self) -> None:
        """沿用 Skeleton 的插值或本地固定坐标绘制实体判定框。"""
        render = self.client.render
        if self._pinned:
            block_size = render.block_size
            screen_cx, screen_cy = render.camera.get_player_screen_center(
                (render.SCREEN_WIDTH, render.SCREEN_HEIGHT), block_size
            )
            visual_center_x, visual_center_y = self._visual_center

            def pinned_transform(position: tuple[float, float]):
                return (
                    screen_cx + (position[0] - visual_center_x) * block_size,
                    screen_cy - (position[1] - visual_center_y) * block_size,
                )

            render.draw_entity_hitbox(
                self.entity,
                position=(0.0, 0.0),
                transform=pinned_transform,
            )
            return

        render.draw_entity_hitbox(
            self.entity,
            position=self.get_hitbox_render_position(),
        )


class PlayerSkeleton(EntitySkeleton):
    """基于 Minecraft Steve 皮肤的 2D 玩家骨架。"""

    # Steve 侧面视图总高 32 像素；皮肤里 16 像素对应一个方块，所以原始高度是 2 格。
    AUTHORED_HEIGHT_BLOCKS = 2.0
    # 玩家视觉模型高度（格），与碰撞体高度分离，保证模型在屏幕上有合理的大小。
    VISUAL_HEIGHT_BLOCKS = 1.8

    # 盔甲不是一套独立骨架；每个渲染层都必须锁定到对应肢体的最终姿态。
    ARMOR_SOURCE_PARTS = {
        "armor_chest_back_arm": "back_arm",
        "armor_leggings_back_leg": "back_leg",
        "armor_boots_back_leg": "back_leg",
        "armor_leggings_body": "body",
        "armor_chest_body": "body",
        "armor_leggings_front_leg": "front_leg",
        "armor_boots_front_leg": "front_leg",
        "armor_chest_front_arm": "front_arm",
        "armor_head": "head",
    }

    @client_method
    def __init__(self, player, *, pinned: bool = True, client=None):
        super().__init__(client, "entity.steve", player)
        # 视觉模型高度与碰撞体高度分离：模型按固定 1.8 格绘制，
        # 脚底对齐 entity.y，模型向上延伸约 1.8 格。
        self.size = self.VISUAL_HEIGHT_BLOCKS / self.AUTHORED_HEIGHT_BLOCKS

        # 客户端主玩家：绕过服务器位置插值，只接受本地镜头引导偏移。
        self._pinned = pinned
        self._visual_center = (
            getattr(player, "width", 1.0) * 0.5,
            self.VISUAL_HEIGHT_BLOCKS / 2,
        )

        # 动画时钟：行走、挥手分别计时，使用正弦函数生成自然摆动。
        self.walk_time = 0.0
        self._swing_time = -1.0  # <0 表示不在挥臂，>=0 为动画进行中
        # 头部角度平滑差值：鼠标→头部不是瞬间跳变
        self._smoothed_head_angle = 0.0
        self._last_facing = self.facing
        self._last_update_time = time.perf_counter()
        self._last_x = player.x
        self._last_y = player.y
        self._current_texture_side = None
        self._held_item_key = None
        self._held_item_pivot = (0.0, 0.0)
        self._held_item_anchor = (0.5, 0.5)
        self._held_item_offset = (0.0, 0.0)
        self._held_item_scale = 0.7
        self._held_item_rotation = 0.0

        self._held_item_textures: dict[int, pygame.Surface] = {}
        self._held_item_pivots: dict[int, tuple[float, float]] = {}
        self._held_item_texture_side = None
        self._armor_key = None
        self._armor_texture_side = None
        self._armor_part_textures = {}
        self._armor_part_visible = {}
        self._build_player_body()
        self._apply_pose(instant=True)
        self.conv_size()

    def _skin(self, rect: tuple[int, int, int, int]) -> pygame.Surface:
        """从 Steve 皮肤图里裁出某个部件的侧面贴图。"""
        return self.texture.subsurface(rect).copy()

    def _build_player_body(self):
        # 这里选的是"侧面"贴图，而不是正面贴图。
        # 这样玩家左右移动时看起来更像横版角色，头、身体、手脚也更容易对齐。
        self._part_textures = {
            self.RIGHT: {
                "head": self._skin((0, 8, 8, 8)),
                "head_overlay": self._skin((32, 8, 8, 8)),
                "body": self._skin((16, 20, 4, 12)),
                "front_arm": self._skin((40, 20, 4, 12)),
                "back_arm": self._skin((32, 52, 4, 12)),
                "front_leg": self._skin((0, 20, 4, 12)),
                "back_leg": self._skin((16, 52, 4, 12)),
            },
            self.LEFT: {
                "head": self._skin((16, 8, 8, 8)),
                "head_overlay": self._skin((48, 8, 8, 8)),
                "body": self._skin((28, 20, 4, 12)),
                "front_arm": self._skin((40, 52, 4, 12)),
                "back_arm": self._skin((48, 20, 4, 12)),
                "front_leg": self._skin((24, 52, 4, 12)),
                "back_leg": self._skin((8, 20, 4, 12)),
            },
        }
        textures = self._part_textures[self.RIGHT]
        empty_item = pygame.Surface((1, 1), pygame.SRCALPHA)
        empty_armor = pygame.Surface((1, 1), pygame.SRCALPHA)
        self.body = {
            # anchor 只是初始化值，真正姿态会在 _apply_pose() 中按玩家高度重算。
            # pivot 的单位是皮肤像素：手脚 pivot=(2,0) 表示从顶部中点挂在肩膀/髋部。
            "back_arm": BodyPart(
                "back_arm", textures["back_arm"], (0.50, 1.50), (2, 0), layer=0
            ),
            "back_leg": BodyPart(
                "back_leg", textures["back_leg"], (0.50, 0.75), (2, 0), layer=1
            ),
            "body": BodyPart("body", textures["body"], (0.50, 1.50), (2, 0), layer=2),
            "front_leg": BodyPart(
                "front_leg", textures["front_leg"], (0.50, 0.75), (2, 0), layer=3
            ),
            "front_arm": BodyPart(
                "front_arm", textures["front_arm"], (0.50, 1.50), (2, 0), layer=4
            ),
            "held_item": BodyPart(
                "held_item", empty_item, (0.50, 1.05), (0.5, 0.5), layer=3, show=False
            ),
            "head": BodyPart("head", textures["head"], (0.50, 1.50), (4, 8), layer=5),
            "head_overlay": BodyPart(
                "head_overlay", textures["head_overlay"], (0.50, 1.50), (4, 8), layer=6
            ),
            "armor_chest_back_arm": BodyPart(
                "armor_chest_back_arm",
                empty_armor,
                (0.50, 1.50),
                (2, 0),
                layer=0.5,
                show=False,
            ),
            "armor_leggings_back_leg": BodyPart(
                "armor_leggings_back_leg",
                empty_armor,
                (0.50, 0.75),
                (2, 0),
                layer=1.3,
                show=False,
            ),
            "armor_boots_back_leg": BodyPart(
                "armor_boots_back_leg",
                empty_armor,
                (0.50, 0.75),
                (2, 0),
                layer=1.6,
                show=False,
            ),
            "armor_leggings_body": BodyPart(
                "armor_leggings_body",
                empty_armor,
                (0.50, 1.50),
                (2, 0),
                layer=2.3,
                show=False,
            ),
            "armor_chest_body": BodyPart(
                "armor_chest_body",
                empty_armor,
                (0.50, 1.50),
                (2, 0),
                layer=2.6,
                show=False,
            ),
            "armor_leggings_front_leg": BodyPart(
                "armor_leggings_front_leg",
                empty_armor,
                (0.50, 0.75),
                (2, 0),
                layer=3.3,
                show=False,
            ),
            "armor_boots_front_leg": BodyPart(
                "armor_boots_front_leg",
                empty_armor,
                (0.50, 0.75),
                (2, 0),
                layer=3.6,
                show=False,
            ),
            "armor_chest_front_arm": BodyPart(
                "armor_chest_front_arm",
                empty_armor,
                (0.50, 1.50),
                (2, 0),
                layer=4.5,
                show=False,
            ),
            "armor_head": BodyPart(
                "armor_head", empty_armor, (0.50, 1.50), (4, 8), layer=7, show=False
            ),
        }
        for name, render_scale in {
            "armor_head": 1.15,
            "armor_leggings_back_leg": 1.05,
            "armor_leggings_body": 1.05,
            "armor_leggings_front_leg": 1.05,
            "armor_chest_back_arm": 1.20,
            "armor_chest_body": 1.20,
            "armor_chest_front_arm": 1.20,
            "armor_boots_back_leg": 1.20,
            "armor_boots_front_leg": 1.20,
        }.items():
            self.body[name].render_scale = render_scale

    def _set_facing_textures(self):
        """根据当前朝向切换左右侧面的皮肤切片。"""
        if self._current_texture_side == self.facing:
            return
        for name, texture in self._part_textures[self.facing].items():
            self.body[name].set_source_texture(texture)
        self._current_texture_side = self.facing

    def _armor_layer(self, stack, layer: int) -> pygame.Surface | None:
        if stack is None or stack.is_empty():
            return None
        texture_name = getattr(stack.material, "armor_texture", None)
        if texture_name is None:
            return None
        texture = self.client.resources_manager.get_texture_img(
            f"models.armor.{texture_name}_layer_{layer}"
        ).copy()
        if texture_name != "leather":
            return texture

        color_getter = getattr(stack.material, "get_dye_color", None)
        color = color_getter(stack) if callable(color_getter) else 0xA06540
        texture.fill(
            ((color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF, 255),
            special_flags=pygame.BLEND_RGBA_MULT,
        )
        overlay = self.client.resources_manager.get_texture_img(
            f"models.armor.leather_layer_{layer}_overlay"
        )
        texture.blit(overlay, (0, 0))
        return texture

    @staticmethod
    def _combine_armor_crops(entries, rect) -> pygame.Surface:
        result = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
        for texture in entries:
            if texture is not None:
                result.blit(texture.subsurface(rect), (0, 0))
        return result

    def _update_armor_textures(self):
        equipment = getattr(self.entity, "equipment", {})
        key = tuple(
            (
                slot,
                getattr(getattr(equipment.get(slot), "material", None), "name_id", "air"),
                repr(getattr(equipment.get(slot), "nbt", {})),
            )
            for slot in ("head", "chest", "legs", "feet")
        )
        if key != self._armor_key:
            layers = {
                (slot, layer): self._armor_layer(equipment.get(slot), layer)
                for slot, layer in (
                    ("head", 1),
                    ("chest", 1),
                    ("legs", 2),
                    ("feet", 1),
                )
            }
            base_parts = {
                "armor_head": self._combine_armor_crops(
                    (layers[("head", 1)],), (0, 8, 8, 8)
                ),
                "armor_chest_body": self._combine_armor_crops(
                    (layers[("chest", 1)],), (16, 20, 4, 12)
                ),
                "armor_chest_front_arm": self._combine_armor_crops(
                    (layers[("chest", 1)],), (40, 20, 4, 12)
                ),
                "armor_chest_back_arm": self._combine_armor_crops(
                    (layers[("chest", 1)],), (40, 20, 4, 12)
                ),
                "armor_leggings_body": self._combine_armor_crops(
                    (layers[("legs", 2)],), (16, 20, 4, 12)
                ),
                "armor_leggings_front_leg": self._combine_armor_crops(
                    (layers[("legs", 2)],), (0, 20, 4, 12)
                ),
                "armor_leggings_back_leg": self._combine_armor_crops(
                    (layers[("legs", 2)],), (0, 20, 4, 12)
                ),
                "armor_boots_front_leg": self._combine_armor_crops(
                    (layers[("feet", 1)],), (0, 20, 4, 12)
                ),
                "armor_boots_back_leg": self._combine_armor_crops(
                    (layers[("feet", 1)],), (0, 20, 4, 12)
                ),
            }
            self._armor_part_textures = {
                self.RIGHT: base_parts,
                self.LEFT: {
                    name: pygame.transform.flip(texture, True, False)
                    for name, texture in base_parts.items()
                },
            }
            self._armor_part_visible = {
                name: bool(texture.get_bounding_rect().width)
                for name, texture in base_parts.items()
            }
            self._armor_key = key
            self._armor_texture_side = None

        if self._armor_texture_side != self.facing:
            for name, texture in self._armor_part_textures.get(self.facing, {}).items():
                self.body[name].set_source_texture(texture)
            self._armor_texture_side = self.facing

    def _update_held_item_texture(self):
        stack = None

        if hasattr(self.entity, "inventory"):
            try:
                slot = max(0, min(8, int(getattr(self.entity, "selected_slot", 0))))
                stack = self.entity.inventory[slot]
            except (AttributeError, TypeError, ValueError, IndexError):
                stack = None
        if stack is None:
            stack = getattr(self.entity, "held_item", None)

        item_id = getattr(getattr(stack, "material", None), "name_id", "air")
        texture_state_key = None
        if stack is not None and not stack.is_empty():
            texture_state_key = stack.get_texture_state_key(self.client)
        key = (item_id, bool(stack and not stack.is_empty()), texture_state_key)
        part = self.body["held_item"]
        if key != self._held_item_key:
            texture = None
            anchor = (0.5, 0.5)
            offset = (0.0, 0.0)
            item_scale = 0.7
            item_rotation = 0.0
            if stack is not None and not stack.is_empty():
                texture = stack.get_texture(1.0, shadow=False)
                try:
                    raw_pose = stack.material.get_anchor()
                    if isinstance(raw_pose, dict):
                        raw_item_anchor = raw_pose.get("anchor", anchor)
                        raw_offset = raw_pose.get("offset", offset)
                        if raw_item_anchor is not None and len(raw_item_anchor) >= 2:
                            anchor = (
                                float(raw_item_anchor[0]),
                                float(raw_item_anchor[1]),
                            )
                        if raw_offset is not None and len(raw_offset) >= 2:
                            offset = (float(raw_offset[0]), float(raw_offset[1]))
                        item_scale = max(0.1, float(raw_pose.get("scale", item_scale)))
                        item_rotation = float(raw_pose.get("rotation", item_rotation))
                    elif raw_pose is not None:
                        if len(raw_pose) >= 2:
                            anchor = (float(raw_pose[0]), float(raw_pose[1]))
                        if len(raw_pose) >= 3:
                            item_scale = max(0.1, float(raw_pose[2]))
                        if len(raw_pose) >= 4:
                            item_rotation = float(raw_pose[3])
                except (AttributeError, TypeError, ValueError):
                    pass
            if texture is None:
                texture = pygame.Surface((1, 1), pygame.SRCALPHA)

            self._held_item_anchor = anchor
            self._held_item_offset = offset
            self._held_item_scale = item_scale
            self._held_item_rotation = item_rotation
            part.render_scale = item_scale
            right_pivot = (
                texture.get_width() * anchor[0],
                texture.get_height() * anchor[1],
            )

            self._held_item_textures = {
                self.RIGHT: pygame.transform.flip(texture, True, False),
                self.LEFT: texture,
            }
            self._held_item_pivots = {
                self.RIGHT: right_pivot,
                self.LEFT: (texture.get_width() - right_pivot[0], right_pivot[1]),
            }
            self._held_item_texture_side = None
            self._held_item_key = key

        if self._held_item_texture_side != self.facing:
            part.set_source_texture(self._held_item_textures[self.facing])
            self._held_item_pivot = self._held_item_pivots[self.facing]
            self._held_item_texture_side = self.facing

    def _update_facing(self):
        """先由基类根据水平速度决定朝向，站立不动时再根据鼠标指向调整。"""
        if not self._pinned:
            facing = int(getattr(self.entity, "facing", self.facing))
            if facing in (self.LEFT, self.RIGHT):
                self.facing = facing
            return
        super()._update_facing()

        # 站立不动时，让玩家朝向当前鼠标选中的方块，挖掘/放置会更自然。
        motion_x = getattr(self.entity.motion, "x", 0.0)
        if abs(motion_x) <= 0.02:
            choosing_position = getattr(self.client.render, "choosing_position", None)
            if choosing_position is not None:
                target_x = choosing_position[0] + 0.5
                center_x = self.entity.x + getattr(self.entity, "width", 1.0) * 0.5
                if abs(target_x - center_x) > 0.35:
                    self.facing = self.RIGHT if target_x > center_x else self.LEFT
        self.entity.facing = self.facing

    # ---------- 公开触发方法 ----------

    def trigger_swing(self):
        if self._swing_time < 0 or self._swing_time >= 0.13:
            self._swing_time = 0.0

    # ---------- 内部动画更新 ----------

    def _update_animation_clocks(self):
        """更新动画计时器，并根据速度决定行走动画快慢。"""
        now = time.perf_counter()
        dt = min(now - self._last_update_time, 0.05)
        self._last_update_time = now

        dx = self.entity.x - self._last_x
        dy = self.entity.y - self._last_y
        self._last_x = self.entity.x
        self._last_y = self.entity.y

        horizontal_speed = max(
            abs(getattr(self.entity.motion, "x", 0.0)), abs(dx) / max(dt, 0.001)
        )
        # 走得越快，摆臂摆腿频率越高
        if horizontal_speed > 0.015:
            self.walk_time += dt * (7.0 + min(horizontal_speed, 1.2) * 3.0)
        else:
            self.walk_time += dt * 2.2

        # 挥臂动画计时：0→0.25s，结束后置 -1 标记停止
        if self._swing_time >= 0:
            self._swing_time += dt
            if self._swing_time > 0.25:
                self._swing_time = -1.0

        return dt, dx, dy, horizontal_speed

    def update(self):
        """玩家骨架每帧先计算目标姿态，再交给基类做平滑和绘制准备。"""
        self._update_facing()
        self._update_animation_clocks()
        if not self._pinned and (
            getattr(self.entity, "breaking", False)
            or getattr(self.entity, "eating", False)
        ):
            self.trigger_swing()

        # 检测潜行状态切换，变化时瞬间跳变到目标姿态
        is_sneaking = getattr(self.entity, "sneaking", False)
        was_sneaking = getattr(self, "_was_sneaking", False)
        sneaking_changed = was_sneaking != is_sneaking
        self._was_sneaking = is_sneaking

        self._apply_pose(instant=sneaking_changed)
        super().update()
        self._sync_armor_parts_to_body()

    def _part_smoothness(self, part: BodyPart) -> float:
        motion_x = getattr(getattr(self.entity, "motion", None), "x", 0.0)
        if part.name in ("front_leg", "back_leg") and abs(motion_x) <= 0.025:
            return 0.12
        return 0.28

    def _sync_armor_parts_to_body(self):
        """让盔甲使用肢体平滑后的实际姿态，避免两套缓动产生逐帧错位。"""
        for armor_name, source_name in self.ARMOR_SOURCE_PARTS.items():
            armor = self.body[armor_name]
            source = self.body[source_name]
            equipped = self._armor_part_visible.get(armor_name, False)

            armor.anchor = source.anchor
            armor.target_anchor = source.target_anchor
            armor.pivot = source.pivot
            armor.target_pivot = source.target_pivot
            armor.angle = source.angle
            armor.target_angle = source.target_angle
            armor.show = equipped and source.show
            armor.target_show = equipped and source.target_show
            armor.flip_x = source.flip_x
            armor.target_flip_x = source.target_flip_x

    def _pose_part(
        self,
        name: str,
        anchor: tuple[float, float],
        pivot: tuple[float, float],
        angle: float,
        *,
        visible: bool = True,
        flip_x: bool | None = None,
    ):
        """给指定部件写入目标姿态，减少 _apply_pose() 里的重复代码。"""
        if flip_x is None:
            flip_x = self.facing == self.LEFT
        self.body[name].set_pose(Pose(anchor, pivot, angle, visible, flip_x))

    def _apply_pose(self, instant: bool = False):
        """编排各子方法，按优先级叠加：行走 → 飞行 → 攻击混合 → 写入部件。"""
        direction = self._facing_sign()
        self._set_facing_textures()
        self._update_held_item_texture()
        self._update_armor_textures()

        # 1. 行走/站立基础姿态
        angles = self._calc_walk_angles(direction)

        # 头部平滑差值：转向时瞬切，静止时渐进跟随
        facing_changed = self._last_facing != self.facing
        self._last_facing = self.facing
        if facing_changed or instant:
            self._smoothed_head_angle = angles["head_angle"]
        else:
            self._smoothed_head_angle = _approach_angle(
                self._smoothed_head_angle, angles["head_angle"], 0.12
            )
        angles["head_angle"] = self._smoothed_head_angle

        # 2. 潜行姿态覆盖
        if getattr(self.entity, "sneaking", False):
            angles = self._calc_sneak_angles(direction, angles)

        # 3. 挥臂动画混合叠加
        if self._swing_time >= 0:
            self._blend_attack_pose(direction, angles)

        # 4. 计算锚点并写入全部部件
        self._write_pose(angles, instant, facing_changed)

    # ---------- 姿态计算子方法 ----------

    def _calc_walk_angles(self, direction: int) -> dict:
        """行走/站立/idle 姿态"""
        motion_x = getattr(self.entity.motion, "x", 0.0)
        moving = abs(motion_x) > 0.025

        cycle = math.sin(self.walk_time)
        counter_cycle = math.sin(self.walk_time + math.pi)

        walk_power = 1.0

        idle = math.sin(time.perf_counter() * 2.4)

        # 静止时极小幅度自然摆动，行走时大幅摆动
        if moving:
            front_arm = direction * (counter_cycle * 28.0)
            back_arm = direction * (cycle * 28.0)
        else:
            front_arm = direction * idle * 2.5
            back_arm = direction * (-idle * 2.5)

        return {
            "bob": 0.0,
            "body_lean": 0.0,
            "head_angle": self._calc_head_angle(direction),
            "front_arm_angle": front_arm,
            "back_arm_angle": back_arm,
            "front_leg_angle": direction
            * (cycle * 55.0 * walk_power if moving else 0.0),
            "back_leg_angle": direction
            * (counter_cycle * 55.0 * walk_power if moving else 0.0),
        }

    def _calc_head_mouse_angle(self, direction: int) -> float:
        """根据鼠标世界坐标计算头部朝向角度（不受运动方向影响）。
        颈部限幅：抬头 ≤45°，低头 ≤80°。"""
        render = self.client.render
        mouse_x, mouse_y = pygame.mouse.get_pos()
        mouse_wx = (
            (mouse_x - render.SCREEN_WIDTH / 2) / render.block_size
            + render.camera.x
            + 0.5
        )
        mouse_wy = (
            (render.SCREEN_HEIGHT / 2 - mouse_y) / render.block_size
            + render.camera.y
            - 0.5
        )

        head_wx = self.entity.x + getattr(self.entity, "width", 1.0) * 0.5
        head_wy = self.entity.y + self.VISUAL_HEIGHT_BLOCKS

        dx = mouse_wx - head_wx
        dy = mouse_wy - head_wy

        raw = math.degrees(math.atan2(dy, max(abs(dx), 1e-4)))
        angle = raw * direction
        return max(-45.0, min(80.0, angle))

    def _calc_head_motion_angle(self, direction: int) -> float:
        """根据实体运动速度计算头部垂直偏角。
        使用 tanh 渐进曲线：下落越快越趋于向上看，最大 ±15°。"""
        motion = getattr(self.entity, "motion", None)
        vy = motion.y if motion else 0.0
        MAX_VERTICAL = 15.0
        SCALE = 5.0
        vertical = -MAX_VERTICAL * math.tanh(-vy / SCALE)
        return direction * vertical

    def _calc_head_angle(self, direction: int) -> float:
        """计算头部朝向角度。

        静止时：完全跟随鼠标。
        移动时：鼠标在玩家前方时主要跟随鼠标，鼠标在后方时主要跟随运动方向。
                两者通过 sigmoid 平滑混合，过渡自然无跳变。
        """
        if not self._pinned:
            try:
                synced = float(getattr(self.entity, "look_angle", 0.0))
            except (TypeError, ValueError):
                synced = 0.0
            return max(-45.0, min(80.0, synced))

        motion = getattr(self.entity, "motion", None)
        motion_x = getattr(motion, "x", 0.0) if motion else 0.0
        moving = abs(motion_x) > 0.025

        mouse_angle = self._calc_head_mouse_angle(direction)

        if not moving:
            self.entity.look_angle = mouse_angle
            return mouse_angle

        # ── 移动时：鼠标与运动方向混合 ──
        motion_angle = self._calc_head_motion_angle(direction)

        # 鼠标相对于玩家朝向的水平偏移（正 = 前方，负 = 后方）
        render = self.client.render
        mouse_x, _ = pygame.mouse.get_pos()
        mouse_wx = (
            (mouse_x - render.SCREEN_WIDTH / 2) / render.block_size
            + render.camera.x
            + 0.5
        )
        head_wx = self.entity.x + getattr(self.entity, "width", 1.0) * 0.5
        dx_ahead = (mouse_wx - head_wx) * direction

        # sigmoid 混合因子：
        #   dx_ahead ≫ 0（鼠标在前方）→ alignment → 1.0 → 鼠标主导
        #   dx_ahead ≪ 0（鼠标在后方）→ alignment → 0.0 → 运动主导
        #   1.5 控制过渡区宽度（格），值越小过渡越陡
        alignment = 1.0 / (1.0 + math.exp(-dx_ahead / 1.5))

        result = mouse_angle * alignment + motion_angle * (1.0 - alignment)
        self.entity.look_angle = result
        return result

    def _calc_sneak_angles(self, direction: int, base: dict) -> dict:
        """潜行姿态覆盖：身体压低、前倾，手脚在潜行基础角度上叠加减弱版行走摆动。"""
        # 身体前倾
        base["body_lean"] = direction * -36.0
        # 头部微微抬起看向前方
        base["head_angle"] = direction * -10.0

        motion_x = getattr(self.entity.motion, "x", 0.0)
        moving = abs(motion_x) > 0.025
        cycle = math.sin(self.walk_time)
        counter_cycle = math.sin(self.walk_time + math.pi)

        walk_power = 1.0

        # 潜行基础角度
        sneak_leg_base = 0.0
        swing_scale = 0.75

        if moving:
            arm_swing = swing_scale * 28.0 * walk_power
            leg_swing = swing_scale * 24.0
        else:
            arm_swing = 0.0
            leg_swing = 0.0

        arm_base = base["body_lean"]
        base["front_arm_angle"] = arm_base + direction * (counter_cycle * arm_swing)
        base["back_arm_angle"] = arm_base + direction * (cycle * arm_swing)
        base["front_leg_angle"] = direction * (sneak_leg_base + cycle * leg_swing)
        base["back_leg_angle"] = direction * (
            sneak_leg_base + counter_cycle * leg_swing
        )
        return base

    def _blend_attack_pose(self, direction: int, angles: dict):
        """攻击/挥手动画混合：单次正弦波从 0 → 峰值 → 0，手臂向前挥动。"""
        t = self._swing_time / 0.25  # 0.25 秒动画
        swing = math.sin(t * math.pi)  # 0→1→0
        # 前臂向前（正方向）挥到 70°，不累加
        angles["front_arm_angle"] = direction * (
            angles["front_arm_angle"] * (1.0 - swing) + 70.0 * swing
        )

    def _write_pose(self, angles: dict, instant: bool, facing_changed: bool):
        """计算锚点坐标并写入全部身体部件。"""
        visual_scale = self.size
        center_x = getattr(self.entity, "width", 1.0) * 0.5
        direction = self._facing_sign()
        bob = angles.get("bob", 0.0)

        center_y = bob * visual_scale
        sneaking = getattr(self.entity, "sneaking", False)

        crouch_y = -0.16 * visual_scale if sneaking else 0.0
        crouch_forward = direction * 0.10 * visual_scale if sneaking else 0.0
        upper_center_x = center_x + crouch_forward
        hip_y = (
            center_y
            + (0.67 * visual_scale if sneaking else 0.75 * visual_scale)
            + crouch_y
        )
        shoulder_y = (
            center_y
            + (1.35 * visual_scale if sneaking else 1.50 * visual_scale)
            + crouch_y
        )
        head_y = shoulder_y + (0.05 * visual_scale if sneaking else 0.0)

        shoulder_spread = (0.10 if sneaking else 0.04) * visual_scale
        hip_spread = 0.035 * visual_scale
        front_x = upper_center_x + direction * shoulder_spread
        back_x = upper_center_x - direction * shoulder_spread
        front_leg_x = center_x + direction * hip_spread
        back_leg_x = center_x - direction * hip_spread

        # 潜行时双腿整体向后偏移，营造蹲伏感
        if getattr(self.entity, "sneaking", False):
            leg_back = 0.25 * visual_scale
            front_leg_x -= direction * leg_back
            back_leg_x -= direction * leg_back

        self._pose_part(
            "back_arm",
            (back_x, shoulder_y),
            (2, 0),
            angles["back_arm_angle"],
            flip_x=False,
        )
        self._pose_part(
            "back_leg",
            (back_leg_x, hip_y),
            (2, 0),
            angles["back_leg_angle"],
            flip_x=False,
        )
        self._pose_part(
            "body",
            (upper_center_x, shoulder_y),
            (2, 0),
            angles["body_lean"],
            flip_x=False,
        )
        self._pose_part(
            "front_leg",
            (front_leg_x, hip_y),
            (2, 0),
            angles["front_leg_angle"],
            flip_x=False,
        )
        self._pose_part(
            "front_arm",
            (front_x, shoulder_y),
            (2, 0),
            angles["front_arm_angle"],
            flip_x=False,
        )

        hand_len = 0.68 * visual_scale
        arm_angle = math.radians(angles["front_arm_angle"])

        hand_x = front_x + math.sin(arm_angle) * hand_len
        hand_y = shoulder_y - math.cos(arm_angle) * hand_len

        offset_x, offset_y = self._held_item_offset
        hand_x += direction * offset_x
        hand_y += offset_y

        item_angle = angles["front_arm_angle"] + direction * self._held_item_rotation
        item_visible = self._held_item_key is not None and self._held_item_key[1]
        self._pose_part(
            "held_item",
            (hand_x, hand_y),
            self._held_item_pivot,
            item_angle,
            visible=item_visible,
            flip_x=False,
        )

        if facing_changed:
            part = self.body["held_item"]
            part.anchor = part.target_anchor
            part.pivot = part.target_pivot
            part.angle = part.target_angle
            part.show = part.target_show
            part.flip_x = part.target_flip_x
        self._pose_part(
            "head", (upper_center_x, head_y), (4, 8), angles["head_angle"], flip_x=False
        )
        self._pose_part(
            "head_overlay",
            (upper_center_x, head_y),
            (4, 8),
            angles["head_angle"],
            flip_x=False,
        )

        for armor_name, source_name in self.ARMOR_SOURCE_PARTS.items():
            source = self.body[source_name]
            self.body[armor_name].set_pose(
                Pose(
                    source.target_anchor,
                    source.target_pivot,
                    source.target_angle,
                    self._armor_part_visible.get(armor_name, False)
                    and source.target_show,
                    False,
                )
            )

        if instant:
            for part in self.body.values():
                part.anchor = part.target_anchor
                part.pivot = part.target_pivot
                part.angle = part.target_angle
                part.show = part.target_show
                part.flip_x = part.target_flip_x
            self._sync_armor_parts_to_body()
