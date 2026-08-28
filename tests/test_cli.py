import pytest

from camview.cli import parse_args
from camview.config import Corner, PixelFormat, Shape


def test_defaults():
    request = parse_args([])
    assert request.capture.device == "/dev/video0"
    assert (request.capture.width, request.capture.height) == (1280, 720)
    assert request.capture.pixel_format is PixelFormat.MJPG
    assert request.window.keep_above is True
    assert request.window.position is None
    assert request.list_formats is False
    assert request.check_mode is True


def test_custom_capture_arguments():
    request = parse_args(
        ["-d", "/dev/video2", "-w", "640", "-H", "480", "-f", "15", "--format", "yuyv"]
    )
    assert request.capture.device == "/dev/video2"
    assert (request.capture.width, request.capture.height, request.capture.fps) == (640, 480, 15)
    assert request.capture.pixel_format is PixelFormat.YUYV


def test_window_arguments():
    request = parse_args(
        ["--scale", "0.4", "--position", "bottom-right", "--radius", "24", "--mirror", "--no-top"]
    )
    assert request.window.scale == 0.4
    assert request.window.position is Corner.BOTTOM_RIGHT
    assert request.window.radius == 24
    assert request.window.mirror is True
    assert request.window.keep_above is False


def test_shape_defaults_to_square():
    assert parse_args([]).window.shape is Shape.SQUARE


def test_shape_derived_from_radius():
    assert parse_args(["--radius", "24"]).window.shape is Shape.ROUNDED


def test_shape_explicit_wins():
    request = parse_args(["--shape", "circle"])
    assert request.window.shape is Shape.CIRCLE
    request = parse_args(["--shape", "square", "--radius", "24"])
    assert request.window.shape is Shape.SQUARE


def test_shape_phone():
    request = parse_args(["--shape", "phone"])
    assert request.window.shape is Shape.PHONE
    assert request.window.shape.aspect == (9, 16)


def test_shape_invalid_rejected():
    with pytest.raises(SystemExit):
        parse_args(["--shape", "triangle"])


def test_list_and_no_check_flags():
    assert parse_args(["--list"]).list_formats is True
    assert parse_args(["--no-check"]).check_mode is False


@pytest.mark.parametrize(
    "argv",
    [
        ["-w", "0"],
        ["-f", "-5"],
        ["--scale", "0"],
        ["--radius", "-2"],
        ["--format", "h264"],
        ["--position", "middle"],
    ],
)
def test_invalid_arguments_exit_with_error(argv):
    with pytest.raises(SystemExit):
        parse_args(argv)
