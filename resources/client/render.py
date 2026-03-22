import pygame




class Render:
    def __init__(self):
        self.BLUE = None
        pygame.init()
        self.SCREEN_WIDTH = 800
        self.SCREEN_HEIGHT = 600
        self.screen = pygame.display.set_mode((self.SCREEN_WIDTH, self.SCREEN_HEIGHT))
        pygame.display.set_caption("PyCraft 2D - 0.0.1 SNAPSHOT")
        self.running = False

    def start(self):
        self.running = True
        self.BLUE = (0, 0, 255)
        while self.running:
            # 处理事件队列
            for event in pygame.event.get():
                if event.type == pygame.QUIT:  # 点击关闭按钮
                    self.running = False
                elif event.type == pygame.KEYDOWN:  # 按键事件
                    if event.key == pygame.K_ESCAPE:  # 按 ESC 键退出
                        self.running = False

            # 填充背景颜色（这里用蓝色）
            self.screen.fill(self.BLUE)

            # 可以在窗口上绘制其他内容，例如一个白色矩形
            # pygame.draw.rect(screen, WHITE, (100, 100, 200, 150))

            # 更新显示（将绘制内容呈现到窗口）
            pygame.display.flip()

        # 退出 Pygame
        pygame.quit()



