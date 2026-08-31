"""OpenGL compositor for world-only status-effect post-processing."""

from __future__ import annotations

from pathlib import Path

import pygame


class StatusEffectShader:
    """Upload software world/GUI surfaces and composite them with one GLSL pass.

    ``offscreen=True`` uses a standalone ModernGL context.  It can coexist with
    a normal SDL software window, so status effects never need to replace the
    live Pygame display with an OpenGL display.
    """

    def __init__(
        self,
        world_surface: pygame.Surface,
        gui_surface: pygame.Surface,
        *,
        offscreen: bool = False,
    ):
        import moderngl
        import pygame_shaders
        from pygame_shaders.screen_rect import ScreenRect
        from pygame_shaders.texture import Texture

        fragment_path = Path(__file__).with_name("shaders") / "status_effects.frag"
        self.world_surface = world_surface
        self.gui_surface = gui_surface
        self.offscreen = bool(offscreen)
        self._pygame_shader = None
        if self.offscreen:
            self.ctx = moderngl.create_standalone_context(require=330)
            self.program = pygame_shaders.Shader.create_vertfrag_shader(
                self.ctx,
                pygame_shaders.DEFAULT_VERTEX_SHADER,
                str(fragment_path),
            )
            self.render_rect = ScreenRect(
                world_surface.get_size(),
                world_surface.get_size(),
                (0, 0),
                self.ctx,
                self.program,
            )
            self.screen_texture = Texture(world_surface, self.ctx)
            self.framebuffer = self.ctx.simple_framebuffer(
                size=world_surface.get_size(), components=4
            )
        else:
            backend = pygame_shaders.Shader(
                pygame_shaders.DEFAULT_VERTEX_SHADER,
                str(fragment_path),
                world_surface,
            )
            self._pygame_shader = backend
            self.ctx = backend.ctx
            self.program = backend.shader
            self.render_rect = backend.render_rect
            self.screen_texture = backend.screen_texture
            self.framebuffer = backend.framebuffer

        self.gui_texture = Texture(gui_surface, self.ctx)
        # pygame's 32-bit surfaces are BGRA in memory on the supported desktop
        # targets.  Swizzling lets us upload their contiguous pixel buffers
        # directly instead of Texture.update() allocating a flipped Surface and
        # an RGBA bytes object for every texture on every frame.
        self.screen_texture.texture.swizzle = "BGRA"
        self.gui_texture.texture.swizzle = "BGRA"
        self._send("imageTexture", 0)
        self._send("guiTexture", 1)
        self._send("guiStrength", 0.0)
        self._send("readbackTopDown", 1.0 if self.offscreen else 0.0)
        # Reuse readback storage; active effects should not allocate two
        # full-window Surfaces every frame.  The shader renders offscreen rows
        # in glReadPixels order, so this Surface can view the GPU readback bytes
        # directly instead of going through NumPy + surfarray every frame.
        width, height = self.size
        self._readback_buffer = bytearray(width * height * 3)
        self._readback_surface = pygame.image.frombuffer(
            self._readback_buffer, self.size, "RGB"
        )
        self.set_uniforms(0.0, 0.0, 0.0, 0.0)

    @property
    def size(self) -> tuple[int, int]:
        return self.world_surface.get_size()

    def _send(self, name: str, value) -> None:
        self.program[name].value = value

    def set_uniforms(
        self,
        time_seconds: float,
        nausea: float,
        blindness: float,
        night_vision: float,
    ) -> None:
        width, height = self.size
        self._send("resolution", (float(width), float(height)))
        self._send("timeSeconds", float(time_seconds))
        self._send("nauseaStrength", max(0.0, min(1.0, float(nausea))))
        self._send("blindnessStrength", max(0.0, min(1.0, float(blindness))))
        self._send(
            "nightVisionStrength", max(0.0, min(1.0, float(night_vision)))
        )

    def _upload(self, *, include_gui: bool) -> None:
        self.screen_texture.texture.write(self.world_surface.get_view("1"))
        if include_gui:
            self.gui_texture.texture.write(self.gui_surface.get_view("1"))
        self.screen_texture.use(0)
        self.gui_texture.use(1)
        self._send("guiStrength", 1.0 if include_gui else 0.0)

    def _render_to_surface(self) -> pygame.Surface:
        self.framebuffer.use()
        self.ctx.viewport = (0, 0, *self.size)
        self.ctx.clear(0.0, 0.0, 0.0, 1.0)
        self.render_rect.vao.render()
        self.framebuffer.read_into(
            self._readback_buffer, components=3, alignment=1
        )
        if self.offscreen:
            return self._readback_surface
        # Direct-window mode only reads pixels for the occasional save icon.
        # Its shader output follows the normal OpenGL window orientation.
        return pygame.transform.flip(self._readback_surface, False, True)

    def present(self, *, include_gui: bool) -> pygame.Surface | None:
        self._upload(include_gui=include_gui)
        if self.offscreen:
            return self._render_to_surface()
        self.ctx.screen.use()
        self.ctx.viewport = (0, 0, *self.size)
        self.ctx.clear(0.0, 0.0, 0.0, 1.0)
        self.render_rect.vao.render()
        return None

    def capture_surface(self, *, include_gui: bool) -> pygame.Surface:
        """Read back one fully processed frame for the world save icon."""
        self._upload(include_gui=include_gui)
        return self._render_to_surface().copy()

    def release(self) -> None:
        objects = (
            getattr(self.gui_texture, "texture", None),
            getattr(self.screen_texture, "texture", None),
            self.framebuffer,
            getattr(self.render_rect, "vao", None),
            getattr(self.render_rect, "vbo", None),
            self.program,
        )
        for resource in objects:
            release = getattr(resource, "release", None)
            if callable(release):
                try:
                    release()
                except Exception:
                    pass
        release_context = getattr(self.ctx, "release", None)
        if callable(release_context):
            try:
                release_context()
            except Exception:
                pass
