"""Catálogo de efeitos de imagem (aba "Effects").

Cada efeito é um Value Object com os parâmetros de coloração aplicados ao
vivo pelos elementos ``videobalance`` + ``gamma`` + ``coloreffects`` do
GStreamer. Alguns efeitos "divertidos" usam um elemento extra (effectv), que
exige reconstruir o pipeline — daí o campo ``element``.

Os filtros aproximam os presets mais conhecidos do Instagram: são
combinações de contraste, saturação, brilho, matiz e curva de gama, que é
como esses filtros são construídos na prática (color grading), sem depender
de LUTs proprietárias.
"""

from __future__ import annotations

from dataclasses import dataclass

# Faixas dos elementos GStreamer (usadas para validar os presets):
#   videobalance: contrast/saturation 0..2, brightness/hue -1..1
#   gamma: 0.01..10
CONTRAST_RANGE = (0.0, 2.0)
SATURATION_RANGE = (0.0, 2.0)
BRIGHTNESS_RANGE = (-1.0, 1.0)
HUE_RANGE = (-1.0, 1.0)
GAMMA_RANGE = (0.01, 10.0)

# Presets do elemento coloreffects (gst-plugins-bad).
COLOR_PRESETS = ("none", "heat", "sepia", "xray", "xpro", "yellowblue")


@dataclass(frozen=True)
class Effect:
    """Um efeito do catálogo."""

    id: str
    label: str
    preset: str = "none"
    contrast: float = 1.0
    brightness: float = 0.0
    saturation: float = 1.0
    hue: float = 0.0
    gamma: float = 1.0
    element: str | None = None  # elemento effectv extra (exige rebuild)

    def __post_init__(self) -> None:
        if self.preset not in COLOR_PRESETS:
            raise ValueError(f"unknown color preset: {self.preset}")
        for value, (low, high), name in (
            (self.contrast, CONTRAST_RANGE, "contrast"),
            (self.saturation, SATURATION_RANGE, "saturation"),
            (self.brightness, BRIGHTNESS_RANGE, "brightness"),
            (self.hue, HUE_RANGE, "hue"),
            (self.gamma, GAMMA_RANGE, "gamma"),
        ):
            if not low <= value <= high:
                raise ValueError(f"{name} out of range in '{self.id}': {value}")

    @property
    def needs_color_preset(self) -> bool:
        """True se o efeito depende do elemento coloreffects."""
        return self.preset != "none"

    @property
    def is_fun(self) -> bool:
        """True se o efeito usa um elemento extra (agingtv, edgetv, ...)."""
        return self.element is not None


# Filtros no estilo Instagram: color grading com videobalance/gamma/coloreffects.
INSTAGRAM: tuple[Effect, ...] = (
    Effect("normal", "Normal"),
    Effect("clarendon", "Clarendon", contrast=1.30, saturation=1.35, brightness=0.06),
    Effect("juno", "Juno", contrast=1.15, saturation=1.45, hue=0.04, gamma=0.95),
    Effect("lark", "Lark", contrast=1.05, saturation=1.15, brightness=0.10, gamma=1.15),
    Effect("gingham", "Gingham", contrast=0.90, saturation=0.85, brightness=0.08, gamma=1.12),
    Effect("aden", "Aden", contrast=0.95, saturation=0.85, brightness=0.08, hue=0.05, gamma=1.10),
    Effect("valencia", "Valencia", preset="sepia", contrast=1.10, saturation=1.30,
           brightness=0.06),
    Effect("nashville", "Nashville", preset="sepia", contrast=1.05, saturation=1.45,
           brightness=0.10, gamma=1.10),
    Effect("f1977", "1977", contrast=0.90, saturation=1.30, brightness=0.12, hue=0.06,
           gamma=1.20),
    Effect("xpro", "X-Pro II", preset="xpro", contrast=1.25, saturation=1.20),
    Effect("lofi", "Lo-Fi", contrast=1.45, saturation=1.35, gamma=0.88),
    Effect("toaster", "Toaster", preset="heat", contrast=1.15, saturation=1.10),
    Effect("inkwell", "Inkwell", saturation=0.0, contrast=1.20),
    Effect("moon", "Moon", saturation=0.0, contrast=1.05, brightness=0.06, gamma=1.10),
    Effect("willow", "Willow", saturation=0.15, contrast=0.95, brightness=0.08, gamma=1.15),
)

# Efeitos "de webcam" clássicos (Cheese-style), via elementos effectv.
FUN: tuple[Effect, ...] = (
    Effect("retro", "Retro (film)", element="agingtv"),
    Effect("edges", "Edges", element="edgetv"),
    Effect("ripple", "Ripple", element="rippletv"),
    Effect("warp", "Warp", element="warptv"),
    Effect("dice", "Mosaic", element="dicetv"),
    Effect("vertigo", "Vertigo", element="vertigotv"),
    Effect("xray", "X-Ray", preset="xray"),
    Effect("thermal", "Thermal", preset="heat"),
)

ALL: tuple[Effect, ...] = INSTAGRAM + FUN

NORMAL = INSTAGRAM[0]


def by_id(effect_id: str) -> Effect:
    """Busca um efeito pelo id (lança ValueError se não existir)."""
    for effect in ALL:
        if effect.id == effect_id:
            return effect
    raise ValueError(f"unknown effect: {effect_id}")


def ids() -> tuple[str, ...]:
    return tuple(effect.id for effect in ALL)
