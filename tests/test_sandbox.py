"""Regressão: o app deve sobreviver a um v4l2-ctl ausente ou bloqueado.

Cenário relatado em teste de campo: rodando o AppImage sob firejail, o
sandbox nega a execução do binário v4l2-ctl (PermissionError). Antes, isso
derrubava o programa com traceback. O v4l2-ctl é opcional — o GStreamer abre
/dev/videoN diretamente —, então a falta dele deve virar CameraError e o app
deve seguir com recursos reduzidos (sem validação de modo e sem controles de
imagem).
"""

import subprocess

import pytest

from camview import camera, controls
from camview.camera import CameraError
from camview.cli import _check_capture_mode
from camview.config import CaptureConfig


def _blocked(*args, **kwargs):
    """Simula o firejail negando a execução do binário."""
    raise PermissionError(13, "Permission denied", "v4l2-ctl")


def _missing(*args, **kwargs):
    """Simula o v4l-utils não instalado."""
    raise FileNotFoundError(2, "No such file or directory", "v4l2-ctl")


@pytest.fixture
def blocked_v4l2(monkeypatch):
    monkeypatch.setattr(camera.subprocess, "run", _blocked)
    monkeypatch.setattr(controls.subprocess, "run", _blocked)


@pytest.fixture
def missing_v4l2(monkeypatch):
    monkeypatch.setattr(camera.subprocess, "run", _missing)
    monkeypatch.setattr(controls.subprocess, "run", _missing)


def test_query_formats_blocked_raises_camera_error(blocked_v4l2):
    with pytest.raises(CameraError, match="sandbox"):
        camera.query_formats("/dev/video0")


def test_query_devices_blocked_raises_camera_error(blocked_v4l2):
    with pytest.raises(CameraError, match="sandbox"):
        camera.query_devices()


def test_query_controls_blocked_raises_camera_error(blocked_v4l2):
    with pytest.raises(CameraError, match="sandbox"):
        controls.query_controls("/dev/video0")


def test_set_control_blocked_raises_camera_error(blocked_v4l2):
    with pytest.raises(CameraError, match="sandbox"):
        controls.set_control("/dev/video0", "brightness", 10)


def test_missing_v4l2_suggests_package(missing_v4l2):
    with pytest.raises(CameraError, match="v4l-utils"):
        camera.query_formats("/dev/video0")


def test_app_still_starts_when_v4l2_is_blocked(blocked_v4l2, capsys):
    """A validação de modo vira aviso — o app não deve abortar (era o crash)."""
    _check_capture_mode(CaptureConfig())
    assert "warning" in capsys.readouterr().err


def test_reset_controls_survives_blocked_v4l2(blocked_v4l2):
    ctrls = (controls.IntControl("brightness", -64, 64, 1, 0, 10),)
    controls.reset_controls("/dev/video0", ctrls)  # não deve levantar


def test_capture_node_survives_blocked_v4l2(blocked_v4l2):
    device = camera.VideoDevice("cam", ("/dev/video0",))
    assert camera.capture_node(device) is None


def test_generic_oserror_is_wrapped(monkeypatch):
    def boom(*args, **kwargs):
        raise OSError(5, "I/O error")

    monkeypatch.setattr(camera.subprocess, "run", boom)
    with pytest.raises(CameraError, match="unavailable"):
        camera.query_formats("/dev/video0")


def test_called_process_error_still_reported(monkeypatch):
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "v4l2-ctl", stderr="cannot open")

    monkeypatch.setattr(camera.subprocess, "run", fail)
    with pytest.raises(CameraError, match="cannot open"):
        camera.query_formats("/dev/video0")
