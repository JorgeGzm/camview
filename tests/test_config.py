import pytest

from camview.config import (
    PHONE_ASPECT,
    CaptureConfig,
    Corner,
    PixelFormat,
    Shape,
    WindowConfig,
)


def test_capture_defaults():
    cfg = CaptureConfig()
    assert cfg.device == "/dev/video0"
    assert (cfg.width, cfg.height, cfg.fps) == (1280, 720, 30)
    assert cfg.pixel_format is PixelFormat.MJPG


@pytest.mark.parametrize(
    "kwargs",
    [
        {"width": 0},
        {"height": -1},
        {"fps": 0},
        {"device": ""},
    ],
)
def test_capture_rejects_invalid_values(kwargs):
    with pytest.raises(ValueError):
        CaptureConfig(**kwargs)


def test_capture_is_immutable():
    cfg = CaptureConfig()
    with pytest.raises(AttributeError):
        cfg.width = 640


@pytest.mark.parametrize("kwargs", [{"scale": 0}, {"scale": -1.5}, {"radius": -1}])
def test_window_rejects_invalid_values(kwargs):
    with pytest.raises(ValueError):
        WindowConfig(**kwargs)


def test_pixel_format_fourcc():
    assert PixelFormat.MJPG.fourcc == "MJPG"
    assert PixelFormat.YUYV.fourcc == "YUYV"


def test_corner_sides():
    assert Corner.TOP_LEFT.is_left and Corner.TOP_LEFT.is_top
    assert not Corner.BOTTOM_RIGHT.is_left and not Corner.BOTTOM_RIGHT.is_top
    assert Corner.BOTTOM_LEFT.is_left and not Corner.BOTTOM_LEFT.is_top


def test_only_the_phone_shape_forces_an_aspect_ratio():
    assert Shape.PHONE.aspect == PHONE_ASPECT
    assert PHONE_ASPECT[0] < PHONE_ASPECT[1]  # retrato: mais alto que largo
    for shape in (Shape.SQUARE, Shape.ROUNDED, Shape.CIRCLE):
        assert shape.aspect is None


def test_shapes_with_rounded_corners():
    assert Shape.ROUNDED.has_corners and Shape.PHONE.has_corners
    assert not Shape.SQUARE.has_corners and not Shape.CIRCLE.has_corners
