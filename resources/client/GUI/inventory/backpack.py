# Explain by Deepseek v4 Pro
"""
背包（物品栏）GUI 模块
=======================
实现 Minecraft 风格的背包界面，支持：
- 4行×9列 = 36格物品栏（底部一行为快捷栏，上方三行为存储区）
- 左键：拿起/放下整组物品，与目标槽位合并或交换
- 右键：拿起半组 / 放下1个，与目标槽位合并或交换
- 拖拽分发：按住鼠标拖过多个槽位，均匀分配物品
- Q键丢弃、Ctrl+Q丢弃单个
- 物品栏编号从下往上递增（底部快捷栏 0-8，顶部 27-35）

槽位映射（Minecraft 原版规范）：
  视觉顶部 Row 0 → 槽位 27-35（存储区第三行）
  Row 1        → 槽位 18-26（存储区第二行）
  Row 2        → 槽位 9-17 （存储区第一行）
  视觉底部 Row 3 → 槽位 0-8   （快捷栏）
"""

from copy import deepcopy

import pygame

from resources.client.GUI.gui import GUI
from resources.client.GUI.inventory.item_tooltip import ItemTooltip
from resources.server.item_class import EmptyItemStack, ItemStack
from resources.server.crafting import find_recipe
from resources.server.utils import reverse_search_dict


class Backpack(GUI):
    """背包 GUI 主类，继承自 GUI 基类"""
    _texture_path = "gui.container.inventory"  # 背包背景纹理路径
    crafting_columns = 2
    crafting_rows = 2
    crafting_offset = (98, 17)
    crafting_output_offset = (154, 28)

    def __init__(self, render):
        super().__init__(render)
        # 所有槽位的屏幕坐标列表，每次 draw() 时重新计算
        self.solt_pos = []
        # 鼠标悬停时的高亮边框纹理
        self.selection_texture = self.get_texture(self.render.gui_scale, self.render.client
                                                  , "gui.sprites.container.slot_highlight_back")

        self.priority = 10  # GUI 渲染优先级
        self.item_tooltip = ItemTooltip(self.render)

        # ---- 鼠标拖拽状态 ----
        self.dragging_item = None     # 当前鼠标上拿着的物品（ItemStack 或 EmptyItemStack）
        self.selecting_item = None    # 当前鼠标悬停的槽位中的物品引用
        self.selecting_solt = None    # 当前鼠标悬停的槽位索引
        self.drag_button = None       # 拖拽时按下的鼠标按键（1=左键, 3=右键）
        self.drag_start_slot = None   # 拖拽起始槽位索引
        self.drag_slots = []          # 拖拽经过的所有有效槽位列表
        self.drag_moved = False       # 拖拽过程中是否发生了移动
        self._drag_preview_slots = {} # 拖拽预览：槽位 → 已放入数量（用于撤销/重算）
        self._drag_material = None    # 拖拽开始时的材料引用（用于撤销时比对材料）

        # ---- 布局参数 ----
        self.slot_rows = 4   # 物品栏行数（含快捷栏）
        self.slot_cols = 9   # 物品栏列数
        self.slot_size = 18  # 每格像素尺寸（缩放前基准值）
        self.crafting_slots = [self._empty_stack() for _ in range(self.crafting_columns * self.crafting_rows)]
        self.crafting_result = None
        self.crafting_inputs = []


    @property
    def inventory(self):
        """快捷访问：返回客户端玩家的物品栏列表"""
        return self.render.client.client_player.inventory

    def _empty_stack(self):
        """创建一个空物品堆（EmptyItemStack）的工厂方法"""
        return EmptyItemStack()

    def _is_empty(self, item):
        """判断物品是否为空（None 或 EmptyItemStack 或数量为0的 ItemStack）"""
        return item is None or item.is_empty()

    def _copy_stack(self, item, amount=None):
        """
        复制一个物品堆，可指定新数量。
        :param item: 源物品堆
        :param amount: 新物品堆的数量，默认与源相同
        :return: 新的 ItemStack 实例（共享同一个 material 实例和深拷贝的 nbt）
        """
        if amount is None:
            amount = item.amount
        return ItemStack(item.material, amount, deepcopy(item.nbt))

    def _clear_slot(self, slot):
        """将指定槽位清空（替换为 EmptyItemStack）"""
        self._set_slot_stack(slot, self._empty_stack())

    @staticmethod
    def _is_crafting_slot(slot):
        return isinstance(slot, tuple) and len(slot) == 2 and slot[0] == "crafting"

    def _get_slot_stack(self, slot):
        if self._is_crafting_slot(slot):
            return self.crafting_slots[slot[1]]
        return self.inventory[slot]

    def _set_slot_stack(self, slot, stack):
        if self._is_crafting_slot(slot):
            self.crafting_slots[slot[1]] = stack
        else:
            self.inventory[slot] = stack

    def _craft_positions(self):
        texture = self.get_texture(self.render.gui_scale, self.render.client)
        x = (self.render.SCREEN_WIDTH - texture.get_width()) // 2
        y = (self.render.SCREEN_HEIGHT - texture.get_height()) // 2
        scale = self.render.gui_scale
        positions = []
        for row in range(self.crafting_rows):
            for col in range(self.crafting_columns):
                positions.append((
                    x + (self.crafting_offset[0] + col * self.slot_size) * scale,
                    y + (self.crafting_offset[1] + row * self.slot_size) * scale,
                ))
        output = (
            x + self.crafting_output_offset[0] * scale,
            y + self.crafting_output_offset[1] * scale,
        )
        return positions, output

    def _refresh_crafting(self):
        match = find_recipe(self.crafting_slots, self.crafting_columns, self.crafting_rows)
        if match is None:
            self.crafting_result = None
            self.crafting_inputs = []
        else:
            self.crafting_result, self.crafting_inputs = match

    def _craft_slot_at_pos(self, pos):
        positions, output = self._craft_positions()
        size = self.slot_size * self.render.gui_scale
        for index, (x, y) in enumerate(positions):
            if x <= pos[0] <= x + size and y <= pos[1] <= y + size:
                return ("crafting", index)
        if output[0] <= pos[0] <= output[0] + size and output[1] <= pos[1] <= output[1] + size:
            return "output"
        return None

    def _slot_target_at_pos(self, pos):
        """Return the inventory or crafting-input slot under the cursor."""
        crafting_slot = self._craft_slot_at_pos(pos)
        if crafting_slot is not None:
            return crafting_slot
        return self._slot_at_pos(pos)

    def _handle_crafting_click(self, target, button):
        if target == "output":
            self.render.client.sent_packet({
                "__class__": "CraftingTake",
                "width": self.crafting_columns,
                "height": self.crafting_rows,
            })
            return

        if self._is_crafting_slot(target):
            self.render.client.sent_packet({
                "__class__": "CraftingClick", "slot": target[1], "button": button,
            })
            return
        if button == 1:
            self._left_click_slot(target)
        else:
            self._right_click_slot(target)
        self._refresh_crafting()

    def _draw_crafting_stack(self, stack, pos):
        if self._is_empty(stack):
            return
        icon = stack.get_texture(self.render.gui_scale * 0.7, shadow=True)
        if icon is None:
            return
        size = self.slot_size * self.render.gui_scale
        x = pos[0] + (size - icon.get_width()) / 2
        y = pos[1] + (size - icon.get_height()) / 2
        self.render.blit(icon, (x, y))
        if stack.amount > 1:
            self.render.render_text(str(stack.amount), (pos[0] + size - self.render.gui_scale * 10, pos[1] + size - self.render.gui_scale * 11), (255, 255, 255), int(20 * self.render.gui_scale / 3.5), True)

    def _draw_crafting(self):
        self._refresh_crafting()
        positions, output = self._craft_positions()
        hovered_target = self._craft_slot_at_pos((self.render.mouse_x, self.render.mouse_y))
        for index, pos in enumerate(positions):
            target = ("crafting", index)
            if target in self.drag_slots or target == hovered_target:
                self.render.blit(
                    self.selection_texture,
                    (pos[0] + self.render.gui_scale, pos[1] + self.render.gui_scale),
                )
        for stack, pos in zip(self.crafting_slots, positions):
            self._draw_crafting_stack(stack, pos)
        if self.crafting_result is not None:
            self._draw_crafting_stack(self.crafting_result, output)
        if hovered_target == "output":
            self.render.blit(
                self.selection_texture,
                (output[0] + self.render.gui_scale, output[1] + self.render.gui_scale),
            )

        if self._is_crafting_slot(hovered_target):
            self.selecting_solt = hovered_target
            self.selecting_item = self.crafting_slots[hovered_target[1]]
        elif hovered_target == "output":
            self.selecting_solt = hovered_target
            self.selecting_item = self.crafting_result

    def _split_stack(self, item, amount):
        """
        从物品堆中分离出指定数量的新堆。
        :param item: 源物品堆（会被修改：扣除分离的数量）
        :param amount: 分离的数量
        :return: 分离出的新 ItemStack
        """
        amount = min(amount, item.amount)
        split = self._copy_stack(item, amount)
        item.amount -= amount
        if item.amount <= 0:
            item.amount = 0
            item.material = self._empty_stack().material
        return split

    def _can_stack(self, a, b):
        """
        判断两个物品堆是否可以堆叠在一起。
        条件：两者都非空、材料相同、NBT 相同。
        注意：不检查目标是否已满，容量检查由 _slot_capacity 负责。
        """
        if self._is_empty(a) or self._is_empty(b):
            return False
        return a.material == b.material and a.nbt == b.nbt

    def _slot_at_pos(self, pos):
        """
        根据屏幕坐标查找对应的槽位索引。
        遍历 4×9 网格，检查鼠标坐标是否落在某个槽位区域内。
        :param pos: (mouse_x, mouse_y) 屏幕坐标
        :return: 槽位索引（0-35），未命中返回 None
        """
        texture = self.get_texture(self.render.gui_scale, self.render.client)
        if texture is None:
            return None

        # 背包纹理的居中位置
        gui_x = (self.render.SCREEN_WIDTH - texture.get_width()) // 2
        gui_y = (self.render.SCREEN_HEIGHT - texture.get_height()) // 2
        # 槽位区域相对于背包纹理的偏移量
        slot_area_x = gui_x + 7 * self.render.gui_scale
        slot_area_y = gui_y + 83 * self.render.gui_scale
        slot_pixel_size = self.render.gui_scale * self.slot_size

        mouse_x, mouse_y = pos
        for row in range(self.slot_rows):
            for col in range(self.slot_cols):
                slot_x = slot_area_x + col * slot_pixel_size
                if row == 3:
                    # 底部快捷栏与主存储区之间有 4px 间距
                    slot_y = slot_area_y + row * slot_pixel_size + 4 * self.render.gui_scale
                else:
                    slot_y = slot_area_y + row * slot_pixel_size
                if slot_x <= mouse_x <= slot_x + slot_pixel_size and slot_y <= mouse_y <= slot_y + slot_pixel_size:
                    # 槽位索引从底部向上递增（Minecraft 原版规范：底部快捷栏为 0-8）
                    slot = (self.slot_rows - 1 - row) * self.slot_cols + col
                    if slot < len(self.inventory):
                        return slot
        return None

    def _slot_capacity(self, slot, source=None):
        """
        计算指定槽位对来源物品的剩余可容纳数量。
        :param slot: 目标槽位索引
        :param source: 来源物品堆，默认使用当前拖拽物品
        :return: 该槽位还能容纳 source 物品的数量
        """
        if source is None:
            source = self.dragging_item
        if self._is_empty(source):
            return 0

        target = self._get_slot_stack(slot)
        if self._is_empty(target):
            # 空槽位：可以放入完整的最大堆叠数
            return source.max_stack_size
        if not self._can_stack(target, source):
            # 材料不同或 NBT 不同：无法放入
            return 0
        return max(0, target.max_stack_size - target.amount)

    def _can_add_to_slot(self, slot, source=None):
        """判断来源物品是否至少可以放入 1 个到指定槽位"""
        return self._slot_capacity(slot, source) > 0

    def _add_amount_to_slot(self, slot, source, amount):
        """
        将一定数量的来源物品放入指定槽位。
        :param slot: 目标槽位索引
        :param source: 来源物品堆（会被修改：扣除放入的数量）
        :param amount: 尝试放入的数量（实际数量受容量限制）
        :return: 实际放入的数量
        """
        amount = min(amount, source.amount, self._slot_capacity(slot, source))
        if amount <= 0:
            return 0

        target = self._get_slot_stack(slot)
        if self._is_empty(target):
            # 目标为空：复制一个新的物品堆放入槽位
            self._set_slot_stack(slot, self._copy_stack(source, amount))
        else:
            # 目标非空：直接在原有数量上累加
            target.amount += amount

        source.amount -= amount
        if source.amount <= 0 and source is self.dragging_item:
            self.dragging_item = self._empty_stack()
        return amount

    def _merge_or_swap_with_slot(self, slot):
        """
        左键点击槽位时的核心操作：将手中整组物品与目标槽位合并或交换。
        规则：
        1. 目标为空 → 手中物品放入槽位，手清空
        2. 目标可堆叠 → 尽可能合并到目标槽位
        3. 目标不可堆叠 → 手中的物品与槽位物品交换位置
        """
        if self._is_empty(self.dragging_item):
            return

        target = self._get_slot_stack(slot)
        if self._is_empty(target):
            # 目标槽位为空：放入整组物品
            self._set_slot_stack(slot, self.dragging_item)
            self.dragging_item = self._empty_stack()
        elif self._can_stack(target, self.dragging_item):
            # 可堆叠：尽可能多地合并（受 max_stack_size 限制）
            self._add_amount_to_slot(slot, self.dragging_item, self.dragging_item.amount)
        else:
            # 不可堆叠：交换位置
            self._set_slot_stack(slot, self.dragging_item)
            self.dragging_item = target

    def _place_one_or_swap_with_slot(self, slot):
        """
        右键点击槽位时的核心操作：将手中 1 个物品放入目标槽位或交换。
        与 _merge_or_swap_with_slot 的区别：每次只放入 1 个而非整组。
        """
        if self._is_empty(self.dragging_item):
            return

        target = self._get_slot_stack(slot)
        if self._is_empty(target) or self._can_stack(target, self.dragging_item):
            # 目标为空或可堆叠：放入 1 个
            self._add_amount_to_slot(slot, self.dragging_item, 1)
        else:
            # 不可堆叠：交换位置
            self._set_slot_stack(slot, self.dragging_item)
            self.dragging_item = target

    def _left_click_slot(self, slot):
        """
        左键点击槽位的完整处理流程。
        - 手中无物品 → 拿起槽位中整组物品
        - 手中有物品 → 合并或交换（调用 _merge_or_swap_with_slot）
        """
        if isinstance(slot, int):
            self.render.client.sent_packet({
                "__class__": "InventoryClick", "slot": slot, "button": 1,
            })
            return
        if self._is_crafting_slot(slot):
            self.render.client.sent_packet({
                "__class__": "CraftingClick", "slot": slot[1], "button": 1,
            })
            return
        target = self._get_slot_stack(slot)
        if self._is_empty(self.dragging_item):
            if not self._is_empty(target):
                # 拿起整组物品
                self.dragging_item = target
                self._clear_slot(slot)
            return
        self._merge_or_swap_with_slot(slot)

    def _right_click_slot(self, slot):
        """
        右键点击槽位的完整处理流程。
        - 手中无物品 → 拿起槽位中半组物品（向上取整）
        - 手中有物品 → 放入 1 个或交换（调用 _place_one_or_swap_with_slot）
        """
        if isinstance(slot, int):
            self.render.client.sent_packet({
                "__class__": "InventoryClick", "slot": slot, "button": 3,
            })
            return
        if self._is_crafting_slot(slot):
            self.render.client.sent_packet({
                "__class__": "CraftingClick", "slot": slot[1], "button": 3,
            })
            return
        target = self._get_slot_stack(slot)
        if self._is_empty(self.dragging_item):
            if not self._is_empty(target):
                # 拿起半组（向上取整）：64→32, 63→32, 1→1
                amount = (target.amount + 1) // 2
                self.dragging_item = self._split_stack(target, amount)
                if target.amount <= 0:
                    self._clear_slot(slot)
            return
        self._place_one_or_swap_with_slot(slot)

    def _start_drag(self, button, slot):
        """
        开始拖拽操作。记录拖拽按键和起始槽位。
        :param button: 鼠标按键（1=左键, 3=右键）
        :param slot: 起始槽位索引
        """
        self.drag_button = button
        self.drag_start_slot = slot
        self.drag_slots = []
        self.drag_moved = False
        self._drag_preview_slots = {}  # 重置预览记录
        self._drag_material = self.dragging_item.material if not self._is_empty(self.dragging_item) else None
        if slot is not None and self._can_add_to_slot(slot):
            self.drag_slots.append(slot)
            # 注意：此时不调用 _apply_drag_preview()，
            # 物品只在实际拖拽移动（_add_drag_slot 被调用）后才开始分发

    def _add_drag_slot(self, slot):
        """
        拖拽过程中鼠标经过新槽位时，将其加入拖拽路径并立即应用实时预览。
        只有可以接收物品的槽位才会被加入。
        每次新增槽位后，撤销之前的预览分配，重新计算全部分配方案。

        注意：capacity 检查必须基于「光标 + 预览槽位」的总物品数，
        而非仅光标上的余数（整除时光标为0但预览槽位中有物品，应允许继续拖拽）。
        """
        if slot is None or self.drag_button not in (1, 3):
            return
        if slot not in self.drag_slots:
            # 计算当前可供分配的总物品数（光标余数 + 已在预览槽位中的物品）
            cursor_amount = self.dragging_item.amount if not self._is_empty(self.dragging_item) else 0
            preview_total = sum(self._drag_preview_slots.values())
            total_available = cursor_amount + preview_total

            if total_available > 0 and self._drag_material is not None:
                # 用总物品数构造临时 ItemStack 来检查槽位容量
                temp_source = ItemStack(self._drag_material, total_available)
                if self._can_add_to_slot(slot, source=temp_source):
                    self.drag_slots.append(slot)
                    self.drag_moved = True  # 标记发生了移动（区别于原地点击）
                    # 实时应用预览：将物品立即放入拖拽路径上的所有槽位
                    # The server performs the distribution atomically when the
                    # mouse button is released.

    def _finish_drag(self):
        """
        拖拽结束：物品已在实时预览中放入槽位，余数留在光标。
        此处仅做状态清理，物品保持不动。
        """
        inventory_slots = [slot for slot in self.drag_slots if isinstance(slot, int)]
        crafting_slots = [slot[1] for slot in self.drag_slots if self._is_crafting_slot(slot)]
        if inventory_slots:
            self.render.client.sent_packet({
                "__class__": "InventoryDrag",
                "slots": inventory_slots,
                "button": self.drag_button,
            })
        if crafting_slots:
            self.render.client.sent_packet({
                "__class__": "CraftingDrag",
                "slots": crafting_slots,
                "button": self.drag_button,
            })
        self._drag_material = None
        self._reset_drag()

    def _apply_drag_preview(self):
        """
        实时预览：根据拖拽类型将手中物品分发到所有拖拽槽位。
        - 左键拖拽：均匀分配，总数 ÷ 槽位数，余数留在光标上（整除时为0也不清空光标）
        - 右键拖拽：每个槽位各放入 1 个
        每次调用前会先撤销上一次的预览分配，确保总数量始终一致。
        """
        if len(self.drag_slots) == 0:
            return

        # 先撤销上一次的预览分配，将物品归还到手中
        self._undo_drag_preview()

        # 保存分发前的总量（用于计算最终余数）
        total_before = self.dragging_item.amount if not self._is_empty(self.dragging_item) else 0

        if self.drag_button == 1:
            # 左键拖拽：均匀分配整组物品到所有槽位
            # 每个槽位获得 总数 // 槽位数，余数留在鼠标光标上（Minecraft 原版行为）
            num_slots = len(self.drag_slots)
            per_slot = total_before // num_slots

            for slot in self.drag_slots:
                if per_slot > 0 and self._can_add_to_slot(slot):
                    actual = self._add_amount_to_slot(slot, self.dragging_item, per_slot)
                    if actual > 0:
                        self._drag_preview_slots[slot] = actual

            # 余数留在光标上（整除为0时光标显示0，但不设为 EmptyItemStack，玩家可继续拖拽）
            placed_total = sum(self._drag_preview_slots.values())
            cursor_remainder = total_before - placed_total
            if self._is_empty(self.dragging_item) or self.dragging_item.amount != cursor_remainder:
                self.dragging_item = ItemStack(self._drag_material, cursor_remainder)
        elif self.drag_button == 3:
            # 右键拖拽：每个槽位各放入 1 个
            for slot in self.drag_slots:
                if self.dragging_item.amount <= 0:
                    break
                if self._can_add_to_slot(slot):
                    actual = self._add_amount_to_slot(slot, self.dragging_item, 1)
                    if actual > 0:
                        self._drag_preview_slots[slot] = \
                            self._drag_preview_slots.get(slot, 0) + actual
            # 右键拖拽：光标物品为0时也保留，不设为 EmptyItemStack
            if self._is_empty(self.dragging_item):
                self.dragging_item = ItemStack(self._drag_material, 0)

    def _undo_drag_preview(self):
        """
        撤销所有预览分配：将预览槽位中的物品取出，归还到手中。
        用于在拖拽槽位变化时重新计算分配方案。
        """
        for slot, amount in list(self._drag_preview_slots.items()):
            target = self._get_slot_stack(slot)
            # 使用 _drag_material 比对材料（因为 dragging_item 可能已被设为 EmptyItemStack）
            if not self._is_empty(target) and target.material == self._drag_material:
                take_back = min(amount, target.amount)
                target.amount -= take_back
                if target.amount <= 0:
                    self._clear_slot(slot)
                # 将物品归还到手中
                if self._is_empty(self.dragging_item):
                    # dragging_item 已被清空（之前全部分配完毕），重新创建
                    self.dragging_item = ItemStack(self._drag_material, take_back)
                else:
                    self.dragging_item.amount += take_back
        self._drag_preview_slots = {}

    def _reset_drag(self):
        """重置所有拖拽状态变量"""
        self.drag_button = None
        self.drag_start_slot = None
        self.drag_slots = []
        self.drag_moved = False
        self._drag_preview_slots = {}
        self._drag_material = None

    def drop_item_stack(self, item_stack):
        """
        丢弃物品到世界的钩子方法。
        从物品栏/鼠标上移除物品后调用，将物品生成为世界中的掉落物实体。
        可在掉落物实体实现后替换或扩展此方法。
        """
        player = self.render.client.client_player
        if hasattr(player, "drop_item_stack"):
            player.drop_item_stack(item_stack)
        elif hasattr(self.render.client, "drop_item_stack"):
            self.render.client.drop_item_stack(player, item_stack)

    def _drop_cursor_item(self, single=False):
        """
        丢弃鼠标上拿着的物品。
        :param single: True=只丢弃1个（Ctrl+Q），False=丢弃整组
        """
        if self._is_empty(self.dragging_item):
            return
        self.render.client.sent_packet({
            "__class__": "InventoryDrop", "cursor": True,
            "amount": 1 if single else None,
        })

    def _drop_slot_item(self, slot, single=False):
        """
        丢弃指定槽位中的物品（Q键快捷丢弃）。
        :param slot: 要丢弃物品的槽位索引
        :param single: True=只丢弃1个，False=丢弃整组
        """
        target = self._get_slot_stack(slot)
        if self._is_empty(target) or not isinstance(slot, int):
            return
        self.render.client.sent_packet({
            "__class__": "InventoryDrop", "cursor": False,
            "slot": slot, "amount": 1 if single else None,
        })

    def _handle_click_outside(self, button):
        """
        处理在物品栏界面外点击的事件。
        - 左键点击外部 → 丢弃手中整组物品
        - 右键点击外部 → 丢弃手中 1 个物品
        """
        if button == 1:
            self._drop_cursor_item(single=False)
        elif button == 3:
            self._drop_cursor_item(single=True)


    def draw(self):
        """
        渲染背包界面的完整流程：
        1. 绘制游戏内 GUI 层背景
        2. 居中绘制背包纹理（含槽位边框）
        3. 遍历 4×9 槽位：计算坐标、检测鼠标悬停、绘制物品图标和数量
        4. 最后绘制鼠标上拿着的拖拽物品（始终在最上层）
        """
        # ---- 第1步：加载并渲染背包背景 ----
        texture = self.get_texture(self.render.gui_scale, self.render.client)
        self.render.blit(self.render.ig_gui_layer, (0, 0))
        # 居中渲染
        x = (self.render.SCREEN_WIDTH - texture.get_width()) // 2
        y = (self.render.SCREEN_HEIGHT - texture.get_height()) // 2
        self.render.blit(texture, (x, y))
        self.selecting_solt = None
        self.selecting_item = None

        # 清空并重新计算槽位坐标（每帧重新算，适应窗口大小变化）
        self.solt_pos = []

        # 计算槽位区域的起始位置（相对于背包纹理左上角的偏移）
        slot_area_x = x + 7 * self.render.gui_scale   # 槽位区域左边距
        slot_area_y = y + 83 * self.render.gui_scale  # 槽位区域上边距

        # 每个槽位的实际像素大小（随 GUI 缩放比例变化）
        slot_pixel_size = self.render.gui_scale * self.slot_size

        # ---- 第2步：遍历所有槽位（4行×9列） ----
        for row in range(self.slot_rows):
            for col in range(self.slot_cols):
                # 计算当前槽位的屏幕坐标
                slot_x = slot_area_x + col * slot_pixel_size
                if row == 3:
                    # 底部快捷栏（Row 3）与上方存储区之间有 4px 间距
                    slot_y = slot_area_y + row * slot_pixel_size + 4 * self.render.gui_scale
                else:
                    slot_y = slot_area_y + row * slot_pixel_size
                self.solt_pos.append((slot_x, slot_y))

                # ---- 第2a步：拖拽高亮 + 鼠标悬停检测 ----
                slot_index = (self.slot_rows - 1 - row) * self.slot_cols + col
                is_drag_slot = self.drag_button is not None and slot_index in self.drag_slots
                is_hovered = slot_x <= self.render.mouse_x <= slot_x + slot_pixel_size \
                         and slot_y <= self.render.mouse_y <= slot_y + slot_pixel_size

                # 拖拽路径上的槽位始终高亮（Minecraft 原版实时反馈）
                if is_drag_slot:
                    self.render.blit(self.selection_texture, (slot_x + self.render.gui_scale, slot_y + self.render.gui_scale))

                # 鼠标悬停检测（与拖拽高亮独立，用于 Q 键丢弃等场景）
                if is_hovered:
                    if not is_drag_slot:
                        # 非拖拽槽位才绘制悬停高亮（避免重复绘制）
                        self.render.blit(self.selection_texture, (slot_x + self.render.gui_scale, slot_y + self.render.gui_scale))
                    self.selecting_solt = slot_index
                    self.selecting_item = self.render.client.client_player.inventory[self.selecting_solt]

                # ---- 第2b步：绘制槽位中的物品 ----
                if slot_index < len(self.render.client.client_player.inventory):
                    item = self.render.client.client_player.inventory[slot_index]
                    # 空格子跳过，不渲染
                    if item.is_empty():
                        continue
                    # 获取带阴影的物品纹理（缩放倍率 0.7×gui_scale）
                    texture_item = item.get_texture(self.render.gui_scale * 0.7, shadow=True)

                    if texture_item is not None:
                        # 物品图标在槽位内居中
                        item_x = slot_x + (slot_pixel_size - texture_item.get_width()) / 2
                        item_y = slot_y + (slot_pixel_size - texture_item.get_height()) / 2
                        self.render.blit(texture_item, (item_x, item_y))

                        # 绘制物品数量（数量 > 1 时显示在右下角）
                        if hasattr(item, 'amount') and item.amount > 1:
                            font_size = int(20 * self.render.gui_scale / 3.5)
                            digit_count = len(str(abs(item.amount)))
                            text_x = slot_x + slot_pixel_size - self.render.gui_scale * (3 + digit_count * 3)
                            text_y = slot_y + slot_pixel_size - self.render.gui_scale * 5 - 6
                            self.render.render_text(str(item.amount), (text_x, text_y), (255, 255, 255), font_size, True)

        # ---- 第3步：绘制悬停说明与鼠标上的拖拽物品 ----
        self._draw_crafting()
        if self._is_empty(self.dragging_item) and not self._is_empty(self.selecting_item):
            self.item_tooltip.draw(
                self.selecting_item,
                (self.render.mouse_x, self.render.mouse_y),
            )
        if self.dragging_item and not self.dragging_item.is_empty():
            texture_item = self.dragging_item.get_texture(self.render.gui_scale * 0.7, shadow=True)
            if texture_item is not None:
                # 物品图标居中跟随鼠标
                self.render.blit(texture_item, (self.render.mouse_x - texture_item.get_width() // 2, self.render.mouse_y - texture_item.get_height() // 2))
                # 拖拽物品数量显示在右下角
                if self.dragging_item.amount > 1:
                    self.render.render_text(str(self.dragging_item.amount), (self.render.mouse_x + texture_item.get_width() // 4, self.render.mouse_y + texture_item.get_height() // 4)
                                            , (255, 255, 255), int(20 * self.render.gui_scale / 3.5), True)

    def handle_events(self, events):
        """
        处理物品栏交互事件（鼠标点击、拖拽、键盘）。
        事件处理后会从列表中移除，防止传递到其他 GUI 层。

        支持的操作：
        - 左键点击槽位：拿起/放下整组物品
        - 右键点击槽位：拿起半组/放下1个
        - 拖拽：均匀分发物品到多个槽位
        - 打开/关闭背包键：切换背包显示
        - Q键：丢弃鼠标上的物品或悬停槽位的物品
        - Ctrl+Q：仅丢弃1个
        """
        for event in events[:]:
            # ---- 鼠标按下（左键=1, 右键=3） ----
            if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
                slot = self._slot_target_at_pos(event.pos)
                if slot == "output":
                    self._handle_crafting_click(slot, event.button)
                    events.remove(event)
                    continue
                if self._is_empty(self.dragging_item):
                    # 手中无物品：从槽位拿起物品
                    if slot is not None:
                        if event.button == 1:
                            self._left_click_slot(slot)
                        else:
                            self._right_click_slot(slot)
                    self._reset_drag()
                else:
                    # 手中有物品：点击外部=丢弃，点击槽位=开始拖拽
                    if slot is None:
                        self._handle_click_outside(event.button)
                        self._reset_drag()
                    else:
                        self._start_drag(event.button, slot)
                events.remove(event)

            # ---- 鼠标移动（拖拽过程中记录经过的槽位，即使光标已空也允许继续） ----
            elif event.type == pygame.MOUSEMOTION:
                if self.drag_button in (1, 3) and self.dragging_item is not None:
                    slot = self._slot_target_at_pos(event.pos)
                    self._add_drag_slot(None if slot == "output" else slot)
                    events.remove(event)

            # ---- 鼠标松开（拖拽结束或确认操作） ----
            elif event.type == pygame.MOUSEBUTTONUP and event.button in (1, 3):
                if self.drag_button == event.button:
                    slot = self._slot_target_at_pos(event.pos)
                    slot = None if slot == "output" else slot
                    self._add_drag_slot(slot)
                    # 拖拽移动过且有有效槽位 → 确认分发（物品已在实时预览中放入）
                    if self.drag_moved and len(self.drag_slots) >= 1:
                        # 发生了拖拽移动且经过多个槽位 → 执行均匀分发
                        self._finish_drag()
                    else:
                        # 原地点击（无移动）→ 执行单击逻辑
                        if self.drag_start_slot is not None:
                            if event.button == 1:
                                self._left_click_slot(self.drag_start_slot)
                            else:
                                self._right_click_slot(self.drag_start_slot)
                        elif slot is None:
                            self._handle_click_outside(event.button)
                        self._reset_drag()
                    events.remove(event)

            # ---- 键盘事件 ----
            elif event.type == pygame.KEYDOWN:
                # ESC closes the currently open container instead of opening
                # the pause menu through the global game-event handler.
                if event.key == pygame.K_ESCAPE:
                    open_containers = [
                        gui for gui in self.render.drawing_GUIs
                        if isinstance(gui, Backpack)
                    ]
                    if open_containers and open_containers[-1] is self:
                        self.render.close_gui(self)
                        events.remove(event)
                # 打开/关闭背包快捷键
                elif event.key in reverse_search_dict(self.render.client.key_map, self.render.client.client_player.game_mode.open_inventory):
                    self.render.client.client_player.game_mode.open_inventory()
                    events.remove(event)
                # Q键丢弃物品
                elif event.key == pygame.K_q:
                    # Ctrl+Q = 只丢弃1个，单独Q = 丢弃整组
                    single = not pygame.key.get_mods() & pygame.KMOD_CTRL
                    if not self._is_empty(self.dragging_item):
                        # 丢弃鼠标上拿着的物品
                        self._drop_cursor_item(single=single)
                    else:
                        # 丢弃鼠标悬停槽位中的物品
                        slot = self._slot_at_pos((self.render.mouse_x, self.render.mouse_y))
                        if slot is not None:
                            self._drop_slot_item(slot, single=single)
                    events.remove(event)

    def on_open(self):
        """背包打开时的回调：增加鼠标锁定计数，使玩家视角无法旋转"""
        self.render.client.game_manager.acquire_game_input()

    def on_close(self):
        """背包关闭时归还临时物品并解除鼠标锁定。"""
        for index, stack in enumerate(self.crafting_slots):
            if not self._is_empty(stack):
                self.crafting_slots[index] = self._empty_stack()
        self._refresh_crafting()
        self._reset_drag()
        if not self._is_empty(self.dragging_item):
            self.dragging_item = self._empty_stack()
        self.render.client.sent_packet({"__class__": "CraftingClose"})
        self.render.client.game_manager.release_game_input()
