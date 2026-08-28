"""Controles de imagem V4L2 (brilho, iluminação, zoom, ...) via v4l2-ctl.

Facade sobre ``v4l2-ctl --list-ctrls-menus`` / ``--set-ctrl``: o parsing é
código puro e testável; apenas ``query_controls``/``set_control`` executam o
processo externo. Os controles podem ser ajustados enquanto outro processo
(o pipeline) está capturando do mesmo dispositivo.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

from camview.camera import CameraError, v4l2_unavailable
from camview.config import DEVICE_RE

_CTRL_RE = re.compile(r"^\s*(\w+) 0x[0-9a-f]+ \((int|bool|menu)\)\s*: (.*)$")
_MENU_OPTION_RE = re.compile(r"^\s*(\d+): (.+)$")
_PAIR_RE = re.compile(r"(\w+)=(-?\d+)")

# Nome de controle aceito ao montar o argumento --set-ctrl. Vale como defesa
# em profundidade: hoje o parser já restringe os nomes, mas essa checagem
# garante que nenhum nome inesperado vire argumento do v4l2-ctl.
_CTRL_NAME_RE = re.compile(r"^[a-z0-9_]+$")


def _check_device(device: str) -> None:
    if not DEVICE_RE.match(device):
        raise CameraError(f"invalid device: {device!r} (expected /dev/videoN)")


@dataclass(frozen=True)
class IntControl:
    name: str
    minimum: int
    maximum: int
    step: int
    default: int
    value: int
    inactive: bool = False


@dataclass(frozen=True)
class BoolControl:
    name: str
    default: bool
    value: bool
    inactive: bool = False


@dataclass(frozen=True)
class MenuControl:
    name: str
    options: tuple[tuple[int, str], ...]
    default: int
    value: int
    inactive: bool = False


Control = IntControl | BoolControl | MenuControl


def parse_controls(text: str) -> tuple[Control, ...]:
    """Interpreta a saída de ``v4l2-ctl --list-ctrls-menus``.

    Controles de tipos não suportados (bitmask, payloads) são ignorados.
    """
    controls: list[Control] = []
    pending_menu: dict | None = None
    menu_options: list[tuple[int, str]] = []

    def close_menu() -> None:
        nonlocal pending_menu, menu_options
        if pending_menu is None:
            return
        controls.append(
            MenuControl(
                name=pending_menu["name"],
                options=tuple(menu_options),
                default=pending_menu["default"],
                value=pending_menu["value"],
                inactive=pending_menu["inactive"],
            )
        )
        pending_menu, menu_options = None, []

    for line in text.splitlines():
        if match := _CTRL_RE.match(line):
            close_menu()
            name, kind, rest = match.groups()
            pairs = {key: int(val) for key, val in _PAIR_RE.findall(rest)}
            inactive = "inactive" in rest
            if kind == "int":
                controls.append(
                    IntControl(
                        name=name,
                        minimum=pairs.get("min", 0),
                        maximum=pairs.get("max", 0),
                        step=pairs.get("step", 1),
                        default=pairs.get("default", 0),
                        value=pairs.get("value", 0),
                        inactive=inactive,
                    )
                )
            elif kind == "bool":
                controls.append(
                    BoolControl(
                        name=name,
                        default=bool(pairs.get("default", 0)),
                        value=bool(pairs.get("value", 0)),
                        inactive=inactive,
                    )
                )
            else:  # menu
                pending_menu = {
                    "name": name,
                    "default": pairs.get("default", 0),
                    "value": pairs.get("value", 0),
                    "inactive": inactive,
                }
        elif pending_menu is not None and (match := _MENU_OPTION_RE.match(line)):
            menu_options.append((int(match.group(1)), match.group(2).strip()))
    close_menu()
    return tuple(controls)


def query_controls(device: str) -> tuple[Control, ...]:
    """Consulta os controles disponíveis no dispositivo."""
    _check_device(device)
    try:
        result = subprocess.run(
            ["v4l2-ctl", "-d", device, "--list-ctrls-menus"],
            capture_output=True,
            text=True,
            check=True,
        )
    except OSError as exc:
        raise CameraError(v4l2_unavailable(exc)) from exc
    except subprocess.CalledProcessError as exc:
        raise CameraError(
            f"failed to query controls of {device}: {exc.stderr.strip()}"
        ) from exc
    return parse_controls(result.stdout)


def set_control(device: str, name: str, value: int) -> None:
    """Aplica um valor a um controle (funciona com o dispositivo em uso)."""
    _check_device(device)
    if not _CTRL_NAME_RE.match(name):
        raise CameraError(f"invalid control name: {name!r}")
    value = int(value)
    try:
        subprocess.run(
            ["v4l2-ctl", "-d", device, f"--set-ctrl={name}={value}"],
            capture_output=True,
            text=True,
            check=True,
        )
    except OSError as exc:
        raise CameraError(v4l2_unavailable(exc)) from exc
    except subprocess.CalledProcessError as exc:
        raise CameraError(
            f"failed to set {name}={value} on {device}: {exc.stderr.strip()}"
        ) from exc


def reset_controls(device: str, controls: tuple[Control, ...]) -> None:
    """Restaura todos os controles aos valores padrão de fábrica."""
    for control in controls:
        if control.inactive:
            continue
        default = int(control.default)
        try:
            set_control(device, control.name, default)
        except CameraError:
            continue
