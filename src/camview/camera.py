"""Inspeção da câmera via v4l2-ctl (Facade sobre a ferramenta externa).

O parsing da saída é código puro e testável; apenas ``query_formats``
executa o processo externo.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

from camview.config import DEVICE_RE, PixelFormat

_FORMAT_RE = re.compile(r"\[\d+\]: '(\w+)' \((.+)\)")
_SIZE_RE = re.compile(r"Size: Discrete (\d+)x(\d+)")
_FPS_RE = re.compile(r"Interval: Discrete [\d.]+s \(([\d.]+) fps\)")
_DEVICE_NODE_RE = re.compile(r"^\s+(/dev/video\d+)\s*$")


class CameraError(RuntimeError):
    """Falha ao consultar o dispositivo de vídeo.

    Inclui o caso do ``v4l2-ctl`` estar ausente ou não poder ser executado
    (ex.: sandbox como firejail/flatpak bloqueando o binário). O vídeo em si
    não depende dele — o GStreamer abre /dev/videoN diretamente —, então o
    programa segue funcionando com recursos reduzidos.
    """


def v4l2_unavailable(exc: OSError) -> str:
    """Mensagem para o v4l2-ctl ausente ou bloqueado (sandbox)."""
    if isinstance(exc, PermissionError):
        return (
            "v4l2-ctl could not be executed (permission denied) — a sandbox "
            "(firejail/flatpak/snap) is likely blocking the binary"
        )
    if isinstance(exc, FileNotFoundError):
        return "v4l2-ctl not found (install the v4l-utils package)"
    return f"v4l2-ctl unavailable: {exc}"


@dataclass(frozen=True)
class Resolution:
    width: int
    height: int
    fps: tuple[int, ...]


@dataclass(frozen=True)
class CameraFormat:
    fourcc: str
    description: str
    resolutions: tuple[Resolution, ...]


@dataclass(frozen=True)
class VideoDevice:
    name: str
    nodes: tuple[str, ...]


def parse_formats(text: str) -> tuple[CameraFormat, ...]:
    """Interpreta a saída de ``v4l2-ctl --list-formats-ext``."""
    formats: list[CameraFormat] = []
    current: dict | None = None
    sizes: list[tuple[int, int, list[int]]] = []

    def close_current() -> None:
        nonlocal current, sizes
        if current is None:
            return
        resolutions = tuple(
            Resolution(w, h, tuple(fps)) for w, h, fps in sizes
        )
        formats.append(CameraFormat(current["fourcc"], current["desc"], resolutions))
        current, sizes = None, []

    for line in text.splitlines():
        if match := _FORMAT_RE.search(line):
            close_current()
            current = {"fourcc": match.group(1), "desc": match.group(2)}
        elif match := _SIZE_RE.search(line):
            sizes.append((int(match.group(1)), int(match.group(2)), []))
        elif (match := _FPS_RE.search(line)) and sizes:
            sizes[-1][2].append(int(float(match.group(1))))
    close_current()
    return tuple(formats)


def parse_devices(text: str) -> tuple[VideoDevice, ...]:
    """Interpreta a saída de ``v4l2-ctl --list-devices``."""
    devices: list[VideoDevice] = []
    name: str | None = None
    nodes: list[str] = []

    def close_current() -> None:
        nonlocal name, nodes
        if name is not None and nodes:
            devices.append(VideoDevice(name, tuple(nodes)))
        name, nodes = None, []

    for line in text.splitlines():
        if match := _DEVICE_NODE_RE.match(line):
            nodes.append(match.group(1))
        elif line.strip().endswith(":"):
            close_current()
            name = line.strip().rstrip(":")
    close_current()
    return tuple(devices)


def query_devices() -> tuple[VideoDevice, ...]:
    """Lista os dispositivos de vídeo conectados."""
    try:
        result = subprocess.run(
            ["v4l2-ctl", "--list-devices"],
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise CameraError(v4l2_unavailable(exc)) from exc
    # v4l2-ctl pode retornar código != 0 mesmo listando dispositivos válidos
    return parse_devices(result.stdout)


def capture_node(device: VideoDevice) -> str | None:
    """Primeiro nó do dispositivo que realmente captura vídeo.

    Câmeras USB expõem nós extras (metadados) que não listam formatos.
    """
    for node in device.nodes:
        try:
            if query_formats(node):
                return node
        except CameraError:
            continue
    return None


def query_formats(device: str) -> tuple[CameraFormat, ...]:
    """Consulta os formatos suportados pelo dispositivo."""
    if not DEVICE_RE.match(device):
        raise CameraError(f"invalid device: {device!r} (expected /dev/videoN)")
    try:
        result = subprocess.run(
            ["v4l2-ctl", "-d", device, "--list-formats-ext"],
            capture_output=True,
            text=True,
            check=True,
        )
    except OSError as exc:
        raise CameraError(v4l2_unavailable(exc)) from exc
    except subprocess.CalledProcessError as exc:
        raise CameraError(f"failed to query {device}: {exc.stderr.strip()}") from exc
    return parse_formats(result.stdout)


def supports(
    formats: tuple[CameraFormat, ...],
    pixel_format: PixelFormat,
    width: int,
    height: int,
    fps: int,
) -> bool:
    """Verifica se a câmera aceita o modo de captura pedido."""
    for fmt in formats:
        if fmt.fourcc != pixel_format.fourcc:
            continue
        for res in fmt.resolutions:
            if res.width == width and res.height == height and fps in res.fps:
                return True
    return False


def render(formats: tuple[CameraFormat, ...]) -> str:
    """Formata a lista de modos para exibição ao usuário."""
    lines: list[str] = []
    for fmt in formats:
        lines.append(f"{fmt.fourcc} ({fmt.description})")
        for res in fmt.resolutions:
            fps = ", ".join(str(f) for f in res.fps)
            lines.append(f"  {res.width}x{res.height} @ {fps} fps")
    return "\n".join(lines)
