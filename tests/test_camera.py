import pytest

from camview import camera
from camview.config import PixelFormat

V4L2_OUTPUT = """\
ioctl: VIDIOC_ENUM_FMT
\tType: Video Capture

\t[0]: 'MJPG' (Motion-JPEG, compressed)
\t\tSize: Discrete 1280x720
\t\t\tInterval: Discrete 0.033s (30.000 fps)
\t\tSize: Discrete 640x480
\t\t\tInterval: Discrete 0.033s (30.000 fps)
\t[1]: 'YUYV' (YUYV 4:2:2)
\t\tSize: Discrete 640x480
\t\t\tInterval: Discrete 0.033s (30.000 fps)
\t\tSize: Discrete 1280x720
\t\t\tInterval: Discrete 0.100s (10.000 fps)
"""


@pytest.fixture
def formats():
    return camera.parse_formats(V4L2_OUTPUT)


def test_parse_finds_both_formats(formats):
    assert [fmt.fourcc for fmt in formats] == ["MJPG", "YUYV"]
    assert formats[0].description == "Motion-JPEG, compressed"


def test_parse_resolutions_and_fps(formats):
    mjpg = formats[0]
    assert [(r.width, r.height) for r in mjpg.resolutions] == [(1280, 720), (640, 480)]
    assert mjpg.resolutions[0].fps == (30,)
    yuyv = formats[1]
    assert yuyv.resolutions[1].fps == (10,)


def test_parse_empty_output():
    assert camera.parse_formats("") == ()


def test_supports_accepts_valid_mode(formats):
    assert camera.supports(formats, PixelFormat.MJPG, 1280, 720, 30)
    assert camera.supports(formats, PixelFormat.YUYV, 1280, 720, 10)


def test_supports_rejects_wrong_fps_or_size(formats):
    assert not camera.supports(formats, PixelFormat.YUYV, 1280, 720, 30)
    assert not camera.supports(formats, PixelFormat.MJPG, 1920, 1080, 30)


def test_render_is_human_readable(formats):
    text = camera.render(formats)
    assert "MJPG (Motion-JPEG, compressed)" in text
    assert "  1280x720 @ 30 fps" in text


def test_query_formats_raises_when_tool_missing(monkeypatch):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("v4l2-ctl")

    monkeypatch.setattr(camera.subprocess, "run", fake_run)
    with pytest.raises(camera.CameraError):
        camera.query_formats("/dev/video0")
