"""Regressões de segurança.

O dispositivo é a única string livre que chega ao GStreamer e ao v4l2-ctl.
Ela é restrita a /dev/videoN na origem (CaptureConfig) e revalidada em cada
Facade, e o pipeline é montado com ElementFactory — nunca por parse_launch —
de modo que nenhum valor de entrada é interpretado como sintaxe.
"""

import pytest

from camview import camera, controls
from camview.camera import CameraError
from camview.config import CaptureConfig
from camview.pipeline import PipelineBuilder

# Tentativas de escapar do valor esperado e injetar elementos/argumentos.
MALICIOUS_DEVICES = [
    "/dev/video0 ! fakesink",
    "/dev/video0 num-buffers=1 ! filesink location=/tmp/roubado",
    "/dev/video0;rm -rf /",
    "/dev/video0 --set-ctrl=brightness=0",
    "/etc/passwd",
    "../../etc/shadow",
    "/dev/video0\n/dev/video1",
    "",
    "/dev/videoX",
]


@pytest.mark.parametrize("device", MALICIOUS_DEVICES)
def test_capture_config_rejects_malicious_device(device):
    with pytest.raises(ValueError, match="invalid device|/dev/videoN"):
        CaptureConfig(device=device)


@pytest.mark.parametrize("device", MALICIOUS_DEVICES)
def test_camera_facade_rejects_malicious_device(device):
    with pytest.raises(CameraError):
        camera.query_formats(device)


@pytest.mark.parametrize("device", MALICIOUS_DEVICES)
def test_controls_facade_rejects_malicious_device(device):
    with pytest.raises(CameraError):
        controls.query_controls(device)
    with pytest.raises(CameraError):
        controls.set_control(device, "brightness", 0)


def test_valid_devices_are_accepted():
    for device in ("/dev/video0", "/dev/video1", "/dev/video42"):
        assert CaptureConfig(device=device).device == device


@pytest.mark.parametrize(
    "name",
    [
        "brightness=0 --set-ctrl=zoom_absolute",
        "brightness;reboot",
        "brightness 0",
        "BRIGHTNESS",
        "",
    ],
)
def test_set_control_rejects_malicious_control_name(name):
    with pytest.raises(CameraError, match="invalid control name"):
        controls.set_control("/dev/video0", name, 0)


def test_pipeline_is_not_built_from_a_parsed_string():
    """build() não deve usar parse_launch (que interpretaria sintaxe)."""
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(PipelineBuilder.build)))
    calls = {
        ast.unparse(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert not any("parse_launch" in call for call in calls)
    assert any("ElementFactory.make" in call for call in calls) or any(
        "_make" in call for call in calls
    )
    assert "ElementFactory.make" in inspect.getsource(PipelineBuilder._make)


def test_pipeline_description_only_carries_validated_device():
    desc = PipelineBuilder().with_capture(CaptureConfig()).build_description()
    assert "device=/dev/video0 !" in desc
    assert desc.count("v4l2src") == 1
