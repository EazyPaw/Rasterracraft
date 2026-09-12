"""Shared, defensive clipboard helpers for client text fields."""

import pygame


def sanitize_single_line(text: str) -> str:
    """Remove control characters which can crash pygame font rendering."""
    return "".join(ch for ch in text if ch.isprintable())


def get_clipboard_text() -> str | None:
    """Read Unicode clipboard text with the same fallbacks used by chat."""
    try:
        if not pygame.scrap.get_init():
            pygame.scrap.init()
        raw = pygame.scrap.get(pygame.SCRAP_TEXT)
        if raw:
            return sanitize_single_line(raw.decode("utf-8", errors="ignore"))
    except Exception:
        pass

    try:
        import ctypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.GetClipboardData.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = (ctypes.c_void_p,)
        kernel32.GlobalLock.restype = ctypes.c_void_p
        handle = None
        if user32.OpenClipboard(None):
            try:
                if user32.IsClipboardFormatAvailable(13):  # CF_UNICODETEXT
                    handle = user32.GetClipboardData(13)
                    pointer = kernel32.GlobalLock(handle) if handle else None
                    if pointer:
                        try:
                            return sanitize_single_line(ctypes.wstring_at(pointer))
                        finally:
                            kernel32.GlobalUnlock(handle)
            finally:
                user32.CloseClipboard()
    except Exception:
        pass

    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        try:
            return sanitize_single_line(root.clipboard_get())
        finally:
            root.destroy()
    except Exception:
        return None
