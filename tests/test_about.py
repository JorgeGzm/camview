import camview
from camview import about


def test_version_matches_package():
    assert about.collect().version == camview.__version__


def test_version_is_semver_like():
    parts = about.collect().version.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)


def test_collect_fills_every_field():
    info = about.collect()
    for field in (info.version, info.summary, info.license, info.python, info.platform):
        assert field


def test_rows_start_with_version():
    rows = about.collect().as_rows()
    assert rows[0][0] == "Version"
    assert rows[0][1] == camview.__version__


def test_rows_include_environment_versions():
    labels = [label for label, _ in about.collect().as_rows()]
    assert {"Python", "GTK", "GStreamer", "System"} <= set(labels)


def test_about_info_is_immutable():
    import pytest

    info = about.collect()
    with pytest.raises(AttributeError):
        info.version = "9.9.9"
