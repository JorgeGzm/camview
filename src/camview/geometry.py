"""Funções puras de geometria da janela (testáveis sem GTK)."""

from __future__ import annotations

from dataclasses import dataclass

from camview.config import Corner

MIN_WINDOW_WIDTH = 80

# Nenhum lado recortado: a imagem inteira da câmera é exibida.
NO_CROP = (0, 0, 0, 0)


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int


def corner_origin(
    workarea: Rect, window_width: int, window_height: int, corner: Corner, margin: int
) -> tuple[int, int]:
    """Posição (x, y) da janela encostada no canto pedido, com margem."""
    if corner.is_left:
        x = workarea.x + margin
    else:
        x = workarea.x + workarea.width - window_width - margin
    if corner.is_top:
        y = workarea.y + margin
    else:
        y = workarea.y + workarea.height - window_height - margin
    return x, y


def scaled_size(
    current_width: int, capture_width: int, capture_height: int, factor: float
) -> tuple[int, int]:
    """Novo tamanho da janela mantendo a proporção da captura."""
    new_width = max(MIN_WINDOW_WIDTH, round(current_width * factor))
    new_height = round(new_width * capture_height / capture_width)
    return new_width, new_height


def sized_by_height(height: int, view_width: int, view_height: int) -> tuple[int, int]:
    """Tamanho da janela para uma altura, na proporção da imagem exibida.

    Usado ao trocar o contorno: preservar a *altura* evita que a janela
    dispare para fora da tela ao passar de paisagem para retrato (e volte
    ao tamanho anterior quando o contorno é desfeito).
    """
    width = max(MIN_WINDOW_WIDTH, round(height * view_width / view_height))
    return width, round(width * view_height / view_width)


def centered_crop(width: int, height: int, aspect: tuple[int, int]) -> Rect:
    """Maior recorte centrado com a proporção pedida dentro da captura.

    Bordas e dimensões saem em números pares porque os formatos YUV com
    croma subamostrado (I420, YUY2) não aceitam recorte em pixel ímpar.
    """
    aspect_width, aspect_height = aspect
    if aspect_width <= 0 or aspect_height <= 0:
        raise ValueError(f"invalid aspect ratio: {aspect_width}:{aspect_height}")
    if width * aspect_height > height * aspect_width:  # captura mais larga que o alvo
        crop_width, crop_height = round(height * aspect_width / aspect_height), height
    else:
        crop_width, crop_height = width, round(width * aspect_height / aspect_width)
    crop_width = _even(min(crop_width, width))
    crop_height = _even(min(crop_height, height))
    return Rect(
        x=_even((width - crop_width) // 2),
        y=_even((height - crop_height) // 2),
        width=crop_width,
        height=crop_height,
    )


def crop_borders(width: int, height: int, crop: Rect) -> tuple[int, int, int, int]:
    """Pixels descartados em cada lado (esquerda, direita, topo, base)."""
    return (
        crop.x,
        width - crop.x - crop.width,
        crop.y,
        height - crop.y - crop.height,
    )


def _even(value: int) -> int:
    return value - value % 2


def clamp_radius(radius: int, width: int, height: int) -> int:
    """Limita o raio dos cantos ao máximo geometricamente possível."""
    return max(0, min(radius, width // 2, height // 2))


def inscribed_circle(width: int, height: int) -> tuple[float, float, float]:
    """Centro (cx, cy) e raio do maior círculo que cabe na janela."""
    return width / 2, height / 2, min(width, height) / 2


def edge_at(x: float, y: float, width: int, height: int, margin: int) -> str | None:
    """Borda da janela sob o ponteiro, para redimensionar arrastando.

    Retorna ``"north"``, ``"south-east"``, ... ou ``None`` (interior).
    """
    vertical = "north" if y < margin else "south" if y > height - margin else ""
    horizontal = "west" if x < margin else "east" if x > width - margin else ""
    if vertical and horizontal:
        return f"{vertical}-{horizontal}"
    return vertical or horizontal or None
