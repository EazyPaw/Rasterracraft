"""OpenGL compositor for world-only status-effect post-processing."""

from __future__ import annotations

from pathlib import Path

import pygame


class StatusEffectShader:
    """Upload software world/GUI surfaces and composite them with one GLSL pass."""

    def __init__(self, world_surface: pygame.Surface, gui_surface: pygame.Surface):
        import pygame_shaders
        from pygame_shaders.texture import Texture

        fragment_path = Path(__file__).with_name("shaders") / "status_effects.frag"
        self.world_surface = world_surface
        self.gui_surface = gui_surface
        self.shader = pygame_shaders.Shader(
            pygame_shaders.DEFAULT_VERTEX_SHADER,
            str(fragment_path),
            world_surface,
        )
        self.gui_texture = Texture(gui_surface, self.shader.ctx)
        # pygame's 32-bit surfaces are BGRA in memory on the supported desktop
        # targets.  Swizzling lets us upload their contiguous pixel buffers
        # directly instead of Texture.update() allocating a flipped Surface and
        # an RGBA bytes object for every texture on every frame.
        self.shader.screen_texture.texture.swizzle = "BGRA"
        self.gui_texture.texture.swizzle = "BGRA"
        self.shader.send("imageTexture", 0)
        self.shader.send("guiTexture", 1)
        self.shader.send("guiStrength", 0.0)
        self.set_uniforms(0.0, 0.0, 0.0, 0.0)

    @property
    def size(self) -> tuple[int, int]:
        return self.world_surface.get_size()

    def set_uniforms(
        self,
        time_seconds: float,
        nausea: float,
        blindness: float,
        night_vision: float,
    ) -> None:
        width, height = self.size
        self.shader.send("resolution", (float(width), float(height)))
        self.shader.send("timeSeconds", float(time_seconds))
        self.shader.send("nauseaStrength", max(0.0, min(1.0, float(nausea))))
        self.shader.send("blindnessStrength", max(0.0, min(1.0, float(blindness))))
        self.shader.send(
            "nightVisionStrength", max(0.0, min(1.0, float(night_vision)))
        )

    def _upload(self, *, include_gui: bool) -> None:
        self.shader.screen_texture.texture.write(self.world_surface.get_view("1"))
        if include_gui:
            self.gui_texture.texture.write(self.gui_surface.get_view("1"))
        self.shader.screen_texture.use(0)
        self.gui_texture.use(1)
        self.shader.send("guiStrength", 1.0 if include_gui else 0.0)

    def present(self, *, include_gui: bool) -> None:
        self._upload(include_gui=include_gui)
        context = self.shader.ctx
        context.screen.use()
        context.viewport = (0, 0, *self.size)
        context.clear(0.0, 0.0, 0.0, 1.0)
        self.shader.render_rect.vao.render()

    def capture_surface(self, *, include_gui: bool) -> pygame.Surface:
        """Read back one fully processed frame for the world save icon."""
        self._upload(include_gui=include_gui)
        return self.shader.render(update_surface=False).copy()

    def release(self) -> None:
        objects = (
            getattr(self.gui_texture, "texture", None),
            getattr(getattr(self.shader, "screen_texture", None), "texture", None),
            getattr(self.shader, "framebuffer", None),
            getattr(getattr(self.shader, "render_rect", None), "vao", None),
            getattr(getattr(self.shader, "render_rect", None), "vbo", None),
            getattr(self.shader, "shader", None),
        )
        for resource in objects:
            release = getattr(resource, "release", None)
            if callable(release):
                try:
                    release()
                except Exception:
                    pass
        release_context = getattr(self.shader.ctx, "release", None)
        if callable(release_context):
            try:
                release_context()
            except Exception:
                pass
