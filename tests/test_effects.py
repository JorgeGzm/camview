import pytest

from camview import effects
from camview.config import CaptureConfig
from camview.effects import Effect
from camview.pipeline import BALANCE_ELEMENT, FUN_ELEMENT, GAMMA_ELEMENT, PipelineBuilder


def test_catalog_has_famous_instagram_filters():
    labels = {effect.label for effect in effects.INSTAGRAM}
    assert {"Clarendon", "Juno", "Lark", "Gingham", "Valencia", "X-Pro II", "Lo-Fi",
            "Inkwell", "Nashville", "1977", "Aden", "Moon"} <= labels


def test_ids_are_unique():
    ids = effects.ids()
    assert len(ids) == len(set(ids))


def test_normal_is_neutral():
    normal = effects.NORMAL
    assert (normal.contrast, normal.saturation, normal.gamma) == (1.0, 1.0, 1.0)
    assert (normal.brightness, normal.hue) == (0.0, 0.0)
    assert normal.preset == "none"
    assert normal.element is None


def test_by_id_finds_every_effect():
    for effect in effects.ALL:
        assert effects.by_id(effect.id) is effect


def test_by_id_rejects_unknown():
    with pytest.raises(ValueError, match="unknown effect"):
        effects.by_id("nope")


def test_black_and_white_filters_have_zero_saturation():
    assert effects.by_id("inkwell").saturation == 0.0
    assert effects.by_id("moon").saturation == 0.0


def test_fun_effects_declare_an_element():
    for effect in effects.FUN:
        if effect.element is not None:
            assert effect.is_fun
    assert effects.by_id("retro").element == "agingtv"
    assert effects.by_id("edges").element == "edgetv"


def test_effect_rejects_unknown_preset():
    with pytest.raises(ValueError, match="unknown color preset"):
        Effect("x", "X", preset="instagram")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"contrast": 2.5},
        {"saturation": -0.1},
        {"brightness": 1.5},
        {"hue": -2.0},
        {"gamma": 0.0},
    ],
)
def test_effect_rejects_out_of_range_values(kwargs):
    with pytest.raises(ValueError, match="out of range"):
        Effect("x", "X", **kwargs)


def test_every_catalog_effect_is_within_gstreamer_ranges():
    for effect in effects.ALL:  # __post_init__ valida; isto documenta a garantia
        assert 0.0 <= effect.contrast <= 2.0
        assert 0.0 <= effect.saturation <= 2.0
        assert -1.0 <= effect.brightness <= 1.0
        assert 0.01 <= effect.gamma <= 10.0


def test_pipeline_includes_color_chain():
    desc = (
        PipelineBuilder()
        .with_capture(CaptureConfig())
        .with_effect(effects.by_id("clarendon"))
        .build_description()
    )
    assert f"videobalance name={BALANCE_ELEMENT}" in desc
    assert "contrast=1.3" in desc
    assert "saturation=1.35" in desc
    assert f"gamma name={GAMMA_ELEMENT}" in desc


def test_pipeline_adds_fun_element_only_when_needed():
    normal = (
        PipelineBuilder()
        .with_capture(CaptureConfig())
        .with_effect(effects.NORMAL)
        .build_description()
    )
    assert FUN_ELEMENT not in normal

    retro = (
        PipelineBuilder()
        .with_capture(CaptureConfig())
        .with_effect(effects.by_id("retro"))
        .build_description()
    )
    assert f"agingtv name={FUN_ELEMENT}" in retro


def test_switching_color_filters_needs_no_rebuild():
    """Filtros de cor só mudam propriedades: mesmo element => sem rebuild."""
    a, b = effects.by_id("clarendon"), effects.by_id("lofi")
    assert a.element == b.element is None
