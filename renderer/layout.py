from dataclasses import dataclass


@dataclass(frozen=True)
class PanelSizes:
    """Pixel sizes of layout regions on the base 2560×1440 canvas."""

    # width, height in pixels
    ART_W: int = 1100
    STATS_W: int = 540
    RELIC_W: int = 470  # tile size (square)
    CANVAS_W: int = 2560
    CANVAS_H: int = 1440


@dataclass(frozen=True)
class ThemeColors:
    """Main color palette (optimizer-purple)."""

    bg_gradient_top: tuple[int, int, int] = (38, 22, 60)  # dark purple
    bg_gradient_bottom: tuple[int, int, int] = (24, 11, 41)

    panel_bg: tuple[int, int, int, int] = (48, 33, 72, 220)  # rgba
    panel_border: tuple[int, int, int] = (128, 94, 176)
    text_primary: tuple[int, int, int] = (235, 228, 255)
    text_secondary: tuple[int, int, int] = (175, 160, 210) 