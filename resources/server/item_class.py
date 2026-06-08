import resources.server.materials as materials
import pygame

class ItemStack:
    def __init__(self, material: 'Material', amount: int = 1, nbt = None):
        if nbt is None:
            nbt = {}
        self.nbt = nbt
        self.material = material
        self.amount = amount
        self.max_stack_size = material.max_stack_size

    def is_empty(self) -> bool:
        """
        判断物品是否为空
        """
        return self.material == materials.AIR() or self.amount == 0

    def is_stackable_with(self, other: 'ItemStack') -> bool:
        """
        判断两个物品是否可以堆叠
        """
        return (self.material == other.material and
                self.nbt == other.nbt and self.amount + other.amount <= self.max_stack_size)

    def stack_item(self, other: 'ItemStack') -> bool:
        """
        尝试将两个物品堆叠在一起, 返回是否成功
        """
        if self.is_stackable_with(other):
            self.amount += other.amount
            other.amount = 0
            other.material = materials.AIR()
            return True
        else:
            return False

    def add_amount(self, amount: int) -> bool:
        """
        增加物品数量, 修改原 ItemStack
        """
        if self.amount + amount <= self.max_stack_size:
            self.amount += amount
            return True
        else:
            return False

    def reduce_amount(self, amount: int) -> bool:
        """
        减少物品数量, 修改原 ItemStack
        """
        if self.amount - amount >= 0:
            self.amount -= amount
            if self.amount == 0:
                self.material = materials.AIR()
            return True
        else:
            return False

    def get_texture(self, scale: float, client, shadow=False, multiply=False):
        if (shadow, multiply) in self.material.texture_cache:
            return self.material.texture_cache[(shadow, multiply)]

        px_scale = client.render.gui_scale

        res = self.material.get_texture(scale, client)
        if shadow and res is not None:

            # 创建带阴影的最终纹理
            width = res.get_width()
            height = res.get_height()
            
            # 创建一个更大的surface来容纳阴影偏移
            result = pygame.Surface((width + px_scale, height + px_scale), pygame.SRCALPHA)
            
            # 创建阴影层：复制原纹理并设置为半透明黑色
            shadow_surface = res.copy()
            # 将所有像素设置为黑色，保持alpha通道
            for x in range(width):
                for y in range(height):
                    pixel = shadow_surface.get_at((x, y))
                    if pixel.a > 0:  # 只处理非透明像素
                        shadow_surface.set_at((x, y), (0, 0, 0, int(255 * 0.5)))
            
            # 将阴影绘制到结果surface（向右下偏移1px）
            result.blit(shadow_surface, (px_scale, px_scale))

            # 将原纹理绘制到结果surface
            result.blit(res, (0, 0))

            result.convert_alpha()

            self.material.texture_cache[(shadow, multiply)] = result
            
            return result
        
        return res


class EmptyItemStack(ItemStack):
    def __init__(self):
        super().__init__(materials.AIR(), 0)

    def is_empty(self) -> bool:
        """
        判断物品是否为空
        """
        return True
