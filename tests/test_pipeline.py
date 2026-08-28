import pytest

from camview.config import CaptureConfig, PixelFormat
from camview.pipeline import (
    CROP_ELEMENT,
    FLIP_ELEMENT,
    SINK_ELEMENT,
    MjpegStrategy,
    PipelineBuilder,
    YuyvStrategy,
    crop_available,
    strategy_for,
)


def capture(**kwargs) -> CaptureConfig:
    defaults = {"device": "/dev/video2", "width": 640, "height": 480, "fps": 15}
    defaults.update(kwargs)
    return CaptureConfig(**defaults)


def test_mjpeg_strategy_caps_and_decoder():
    strategy = MjpegStrategy()
    assert strategy.source_caps(capture()) == "image/jpeg,width=640,height=480,framerate=15/1"
    assert strategy.decode_chain() == ["jpegdec"]


def test_yuyv_strategy_caps_without_decoder():
    strategy = YuyvStrategy()
    caps = strategy.source_caps(capture(pixel_format=PixelFormat.YUYV))
    assert caps == "video/x-raw,format=YUY2,width=640,height=480,framerate=15/1"
    assert strategy.decode_chain() == []


def test_strategy_registry_covers_all_formats():
    for fmt in PixelFormat:
        assert strategy_for(fmt) is not None


def test_builder_mjpeg_description():
    """A cadeia começa na fonte e termina no sink, com os filtros no meio."""
    desc = PipelineBuilder().with_capture(capture()).build_description()
    assert desc.startswith(
        "v4l2src device=/dev/video2 ! "
        "image/jpeg,width=640,height=480,framerate=15/1 ! "
        "jpegdec"
    )
    assert "videoconvert ! videobalance" in desc
    assert desc.endswith(
        f"videoflip name={FLIP_ELEMENT} method=none ! "
        f"xvimagesink name={SINK_ELEMENT} force-aspect-ratio=true"
    )
    # efeito neutro por padrão
    assert "contrast=1.0" in desc and "saturation=1.0" in desc


def test_builder_yuyv_has_no_jpegdec():
    desc = (
        PipelineBuilder()
        .with_capture(capture(pixel_format=PixelFormat.YUYV))
        .build_description()
    )
    assert "jpegdec" not in desc
    assert "format=YUY2" in desc


def test_builder_mirror_sets_flip_method():
    desc = PipelineBuilder().with_capture(capture()).with_mirror(True).build_description()
    assert f"videoflip name={FLIP_ELEMENT} method=horizontal-flip" in desc


def test_builder_custom_sink():
    desc = PipelineBuilder().with_capture(capture()).with_sink("ximagesink").build_description()
    assert desc.endswith(f"ximagesink name={SINK_ELEMENT} force-aspect-ratio=true")


def test_builder_crop_borders_reach_the_videocrop():
    """O recorte só aparece onde o elemento videocrop existe."""
    desc = (
        PipelineBuilder().with_capture(capture()).with_crop((80, 80, 0, 0)).build_description()
    )
    expected = f"videocrop name={CROP_ELEMENT} left=80 right=80 top=0 bottom=0"
    assert (expected in desc) is crop_available()


def test_builder_crop_defaults_to_whole_frame():
    desc = PipelineBuilder().with_capture(capture()).build_description()
    if crop_available():
        assert f"videocrop name={CROP_ELEMENT} left=0 right=0 top=0 bottom=0" in desc
    else:
        assert "videocrop" not in desc


def test_builder_rejects_negative_crop():
    with pytest.raises(ValueError):
        PipelineBuilder().with_capture(capture()).with_crop((-1, 0, 0, 0))


def test_builder_requires_capture():
    with pytest.raises(ValueError):
        PipelineBuilder().build_description()
