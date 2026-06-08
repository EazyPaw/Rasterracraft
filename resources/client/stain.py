import cv2
import numpy as np
from pygame import surfarray
import pygame

# 非必要不修改这里的函数

def hex_to_bgr(hex_color):
    """
    将十六进制颜色转换为BGR格式
    """
    hex_color = hex_color.lstrip('#')  # 去除#号
    b = int(hex_color[4:6], 16)
    g = int(hex_color[2:4], 16)
    r = int(hex_color[0:2], 16)
    return np.array([b, g, r])

def colorize_image(image_path, hex_color):
    """
    读取图像并将其染色为指定的目标颜色，保留透明度和明暗变化
    :param image_path: 图像路径
    :param hex_color: 目标颜色的十六进制表示（例如 "#91bd59"）
    """
    # 读取带Alpha通道的图像
    image = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)

    # 检查图片是否成功加载
    if image is None:
        print("图像加载失败")
        return

    # 提取Alpha通道（透明度通道）
    alpha_channel = image[:, :, 3]

    # 将图像转换为BGR格式，同时保留Alpha通道
    bgr_image = image[:, :, :3]

    # 将灰度图转换为灰度
    gray_image = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY)

    # 将目标颜色（十六进制）转换为BGR格式
    target_color = hex_to_bgr(hex_color)

    # 根据灰度值调整目标颜色
    # 使用灰度值来对目标颜色进行亮度加权
    colored_image = np.zeros_like(bgr_image, dtype=np.uint8)
    for i in range(3):
        colored_image[:, :, i] = (target_color[i] * gray_image) / 255

    # 将Alpha通道与染色后的BGR合并
    result_image = cv2.merge([colored_image[:, :, 0], colored_image[:, :, 1], colored_image[:, :, 2], alpha_channel])

    return result_image


def overlay_images(image1, image2):
    """
    将两张图片按图层组合在一起。image1为没有Alpha通道的图像，image2为具有Alpha通道的图像。
    :param image1: 第一张图像（不带Alpha通道，背景透明）
    :param image2: 第二张图像（带Alpha通道，部分透明）
    :return: 合成后的图像
    """
    # 确保两张图像尺寸相同
    if image1.shape[:2] != image2.shape[:2]:
        raise ValueError("错误：两张图像尺寸不同")

    # 提取第二张图像的Alpha通道
    alpha2 = image2[:, :, 3] / 255.0  # Alpha值归一化为0到1之间

    # 提取第二张图像的RGB部分
    rgb2 = image2[:, :, :3]

    # 处理第一张图像（无Alpha通道），假设它的背景是白色
    rgb1 = image1[:, :, :3]  # 只取RGB部分

    # 将两张图像合并，使用Alpha通道对第二张图像进行加权
    result_rgb = alpha2[:, :, np.newaxis] * rgb2 + (1 - alpha2[:, :, np.newaxis]) * rgb1

    # 创建合成图像的Alpha通道：取第二张图像的Alpha通道
    result_alpha = np.maximum(alpha2, 1 - alpha2)  # 使用第二张图的Alpha值

    # 合并RGB与Alpha通道，生成最终图像
    result_image = np.dstack([result_rgb, result_alpha * 255])

    return result_image.astype(np.uint8)


def cv2_to_pygame(cv_image):
    """
    将OpenCV图像转换为Pygame的Surface对象
    :param cv_image: 由OpenCV读取的图像（BGR格式）
    :return: 转换后的Pygame Surface对象
    """
    # OpenCV图像是BGR格式，pygame使用RGB格式，因此需要转换
    rgb_image = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)

    # 将NumPy数组转换为Pygame Surface对象
    # 注意：surfarray.make_surface 期望的是 (width, height, 3) 或 (width, height, 4)
    # 而 cv2 图像通常是 (height, width, channels)，所以需要转置或交换轴
    rgb_image_swapped = np.swapaxes(rgb_image, 0, 1)
    
    surface = surfarray.make_surface(rgb_image_swapped).convert_alpha()

    return surface

def overlay_surfaces(base_surface: pygame.Surface, overlay_surface: pygame.Surface) -> pygame.Surface:
    """
    将 overlay_surface 组合到 base_surface 上，支持 Alpha 混合。
    :param base_surface: 底层 Surface
    :param overlay_surface: 顶层 Surface（带 Alpha 通道）
    :return: 组合后的 Surface
    """
    # 确保尺寸一致
    if base_surface.get_size() != overlay_surface.get_size():
        overlay_surface = pygame.transform.scale(overlay_surface, base_surface.get_size())

    # 创建副本以避免修改原图
    result = base_surface.copy().convert_alpha()
    
    # 使用 BLEND_RGBA_ADD 或 BLEND_ALPHA 进行混合
    # 这里直接使用 blit，因为 overlay_surface 自带 Alpha 通道
    result.blit(overlay_surface, (0, 0))
    
    return result

