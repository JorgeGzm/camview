from importlib.resources import files


def test_icon_svg_is_packaged():
    icon = files("camview").joinpath("assets/icon.svg")
    content = icon.read_text(encoding="utf-8")
    assert content.lstrip().startswith("<svg")
    assert 'viewBox="0 0 256 256"' in content


def test_desktop_entry_is_packaged():
    desktop = files("camview").joinpath("assets/camview.desktop")
    content = desktop.read_text(encoding="utf-8")
    assert "[Desktop Entry]" in content
    assert "Exec=camview" in content
    assert "Icon=camview" in content
