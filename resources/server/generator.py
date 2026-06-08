import noise
from resources.server.blocks import *

class Generator:
    def __init__(self, seed):
        self.seed = seed

    def get_original_block(self, x, y, z):
        return AIR()

class ClassicFlat(Generator):
    def get_original_block(self, x, y, z):
        # --- 地形层 ---
        if 60 < y < 70:
            return DIRT()
        elif y == 70:
            return GRASS_BLOCK()
        elif y == 0:
            return BEDROCK()
        elif y <= 60:
            return STONE()

        # --- 植被层 (y=71) ---
        elif y == 71:
            # 1. 植被团 (低频，决定哪里会有植物)
            #    阈值保持宽松 (-0.15)，让大部分草地都有植被
            veg_patch = noise.pnoise2(
                x * 0.02, z * 0.02,
                octaves=2, persistence=0.5, lacunarity=2.0,
                base=self.seed
            )
            if veg_patch > -0.15:
                # 2. 草 — 保持原有破碎感不变
                grass_detail1 = noise.pnoise2(x * 0.25, z * 0.25, base=self.seed + 10)
                grass_detail2 = noise.pnoise2(x * 0.4, z * 0.4, base=self.seed + 11)
                if (grass_detail1 + grass_detail2) / 2 > -0.3:
                    # 3. 花 — 大幅提高阈值，使花极其稀疏
                    flower_patch = noise.pnoise2(
                        x * 0.03, z * 0.03,   # 频率稍低，保持团状趋势
                        octaves=1,
                        base=self.seed + 100
                    )
                    flower_local = noise.pnoise2(
                        x * 0.15, z * 0.15,
                        base=self.seed + 150
                    )
                    # 只有当两个噪声都超过较高阈值时才生花
                    if flower_patch > 0.55 and flower_local > 0.5:
                        if noise.pnoise2(x * 0.7, z * 0.7, base=self.seed + 200) > 0:
                            return POPPY()
                        else:
                            return DANDELION()
                    else:
                        return SHORT_GRASS()

            return AIR()

        else:
            return AIR()

class bedrock_flat_generator(Generator):
    def get_original_block(self, x, y, z):
        return BEDROCK() if y == 0 else AIR()