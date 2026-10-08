"""Objetos de valor (Value Objects) imutáveis com a configuração do app.

Imutabilidade (frozen=True) garante que a configuração validada no boot
não seja alterada acidentalmente pelo restante do programa.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

# Só nós de captura V4L2 são aceitos como dispositivo. Isso impede que uma
# string arbitrária chegue ao GStreamer ou ao v4l2-ctl como argumento.
DEVICE_RE = re.compile(r"^/dev/video\d+$")

# Proporção da tela de um celular (retrato). É a mesma dos vídeos verticais
# de stories/reels, então a imagem sai pronta para esse tipo de gravação.
PHONE_ASPECT = (9, 16)

# Recorte manual do usuário, em porcentagem da captura por lado — aqui nada
# é pixel: a conversão para bordas em pixels fica em
# ``geometry.crop_from_percents`` (``geometry.NO_CROP`` é o "sem recorte" em
# pixels). O limite por lado garante que lados opostos nunca somem mais de
# 90% — sempre sobra um quadro utilizável.
MAX_CROP_PERCENT = 45
NO_CROP_PERCENT = (0, 0, 0, 0)


class PixelFormat(str, Enum):
    """Formatos de captura suportados pela câmera."""

    MJPG = "mjpg"
    YUYV = "yuyv"

    @property
    def fourcc(self) -> str:
        """Código FourCC como reportado pelo V4L2 (v4l2-ctl)."""
        return {PixelFormat.MJPG: "MJPG", PixelFormat.YUYV: "YUYV"}[self]


class Shape(str, Enum):
    """Contorno da área de vídeo exibida."""

    SQUARE = "square"
    ROUNDED = "rounded"
    CIRCLE = "circle"
    PHONE = "phone"

    @property
    def aspect(self) -> tuple[int, int] | None:
        """Proporção imposta à imagem (``None`` = a proporção da captura).

        Quando existe, a captura é recortada no centro para essa proporção —
        é o que faz o contorno ``phone`` mostrar um retrato de verdade, e não
        a imagem deitada com tarjas pretas.
        """
        return PHONE_ASPECT if self is Shape.PHONE else None

    @property
    def has_corners(self) -> bool:
        """True se o contorno desenha cantos arredondados (usa ``radius``)."""
        return self in (Shape.ROUNDED, Shape.PHONE)


class Corner(str, Enum):
    """Cantos da área de trabalho para posicionamento da janela."""

    TOP_LEFT = "top-left"
    TOP_RIGHT = "top-right"
    BOTTOM_LEFT = "bottom-left"
    BOTTOM_RIGHT = "bottom-right"

    @property
    def is_left(self) -> bool:
        return self in (Corner.TOP_LEFT, Corner.BOTTOM_LEFT)

    @property
    def is_top(self) -> bool:
        return self in (Corner.TOP_LEFT, Corner.TOP_RIGHT)


@dataclass(frozen=True)
class CaptureConfig:
    """Parâmetros de captura enviados à câmera."""

    device: str = "/dev/video0"
    width: int = 1280
    height: int = 720
    fps: int = 30
    pixel_format: PixelFormat = PixelFormat.MJPG

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"invalid resolution: {self.width}x{self.height}")
        if self.fps <= 0:
            raise ValueError(f"invalid fps: {self.fps}")
        if not DEVICE_RE.match(self.device):
            raise ValueError(
                f"invalid device: {self.device!r} (expected /dev/videoN)"
            )


@dataclass(frozen=True)
class WindowConfig:
    """Aparência e comportamento da janela de exibição."""

    scale: float = 1.0
    position: Corner | None = None
    shape: Shape = Shape.SQUARE
    radius: int = 0
    mirror: bool = False
    keep_above: bool = True
    crop: tuple[int, int, int, int] = NO_CROP_PERCENT

    def __post_init__(self) -> None:
        if self.scale <= 0:
            raise ValueError(f"invalid scale: {self.scale}")
        if self.radius < 0:
            raise ValueError(f"invalid radius: {self.radius}")
        if any(percent < 0 or percent > MAX_CROP_PERCENT for percent in self.crop):
            raise ValueError(f"invalid crop percents: {self.crop}")

    @property
    def has_crop(self) -> bool:
        """True se algum lado da captura é recortado manualmente."""
        return any(self.crop)
