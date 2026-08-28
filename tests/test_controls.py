import pytest

from camview import controls
from camview.camera import CameraError

V4L2_CTRLS_OUTPUT = """\
User Controls

                     brightness 0x00980900 (int)    : min=-64 max=64 step=1 default=0 value=10 flags=0x00001000
        white_balance_automatic 0x0098090c (bool)   : default=1 value=1
           power_line_frequency 0x00980918 (menu)   : min=0 max=2 default=2 value=2 (60 Hz)
\t\t\t\t0: Disabled
\t\t\t\t1: 50 Hz
\t\t\t\t2: 60 Hz
      white_balance_temperature 0x0098091a (int)    : min=2800 max=6500 step=10 default=4600 value=4600 flags=inactive, 0x00001000
   region_of_interest_rectangle 0x00981ae1 (unknown): type=107 value=unsupported payload type flags=has-payload, 0x00001000
  region_of_interest_auto_ctrls 0x00981ae2 (bitmask): max=0x00000001 default=0x00000001 value=0 flags=0x00001000

Camera Controls

                  auto_exposure 0x009a0901 (menu)   : min=0 max=3 default=3 value=3 (Aperture Priority Mode)
\t\t\t\t1: Manual Mode
\t\t\t\t3: Aperture Priority Mode
"""


@pytest.fixture
def parsed():
    return controls.parse_controls(V4L2_CTRLS_OUTPUT)


def test_parse_finds_supported_controls_only(parsed):
    names = [c.name for c in parsed]
    assert names == [
        "brightness",
        "white_balance_automatic",
        "power_line_frequency",
        "white_balance_temperature",
        "auto_exposure",
    ]


def test_int_control_fields(parsed):
    brightness = parsed[0]
    assert isinstance(brightness, controls.IntControl)
    assert (brightness.minimum, brightness.maximum, brightness.step) == (-64, 64, 1)
    assert brightness.default == 0
    assert brightness.value == 10
    assert brightness.inactive is False


def test_bool_control_fields(parsed):
    wb_auto = parsed[1]
    assert isinstance(wb_auto, controls.BoolControl)
    assert wb_auto.value is True


def test_menu_control_options(parsed):
    plf = parsed[2]
    assert isinstance(plf, controls.MenuControl)
    assert plf.options == ((0, "Disabled"), (1, "50 Hz"), (2, "60 Hz"))
    assert plf.value == 2


def test_menu_with_sparse_indexes(parsed):
    exposure = parsed[4]
    assert isinstance(exposure, controls.MenuControl)
    assert exposure.options == ((1, "Manual Mode"), (3, "Aperture Priority Mode"))


def test_inactive_flag_detected(parsed):
    wb_temp = parsed[3]
    assert wb_temp.inactive is True


def test_parse_empty():
    assert controls.parse_controls("") == ()


def test_set_control_raises_on_failure(monkeypatch):
    import subprocess

    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0], stderr="unknown control")

    monkeypatch.setattr(controls.subprocess, "run", fake_run)
    with pytest.raises(CameraError):
        controls.set_control("/dev/video0", "nope", 1)
