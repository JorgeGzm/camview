from camview import camera

V4L2_DEVICES_OUTPUT = """\
HD Pro Webcam C920 (usb-0000:00:14.0-1.1.1):
\t/dev/video4
\t/dev/video5
\t/dev/media2

Integrated_Webcam_HD: Integrate (usb-0000:00:14.0-5):
\t/dev/video0
\t/dev/video1
\t/dev/media0
"""


def test_parse_devices_names_and_nodes():
    devices = camera.parse_devices(V4L2_DEVICES_OUTPUT)
    assert len(devices) == 2
    c920, integrated = devices
    assert c920.name == "HD Pro Webcam C920 (usb-0000:00:14.0-1.1.1)"
    assert c920.nodes == ("/dev/video4", "/dev/video5")
    assert integrated.nodes == ("/dev/video0", "/dev/video1")


def test_parse_devices_ignores_media_nodes():
    devices = camera.parse_devices(V4L2_DEVICES_OUTPUT)
    for device in devices:
        assert all(node.startswith("/dev/video") for node in device.nodes)


def test_parse_devices_empty():
    assert camera.parse_devices("") == ()


def test_capture_node_picks_first_node_with_formats(monkeypatch):
    device = camera.VideoDevice("cam", ("/dev/video1", "/dev/video4"))

    def fake_query(node):
        if node == "/dev/video4":
            return (camera.CameraFormat("MJPG", "Motion-JPEG", ()),)
        return ()

    monkeypatch.setattr(camera, "query_formats", fake_query)
    assert camera.capture_node(device) == "/dev/video4"


def test_capture_node_none_when_no_capture_nodes(monkeypatch):
    device = camera.VideoDevice("cam", ("/dev/video1",))
    monkeypatch.setattr(camera, "query_formats", lambda node: ())
    assert camera.capture_node(device) is None


def _fake_proc(tmp_path, links):
    for pid, target in links.items():
        fd_dir = tmp_path / str(pid) / "fd"
        fd_dir.mkdir(parents=True)
        (fd_dir / "3").symlink_to(target)
    return str(tmp_path)


def test_node_in_use_detects_open_fd(tmp_path):
    proc = _fake_proc(tmp_path, {100: "/dev/video0", 200: "/dev/null"})
    assert camera.node_in_use("/dev/video0", proc_root=proc) is True
    assert camera.node_in_use("/dev/video4", proc_root=proc) is False


def test_free_capture_nodes_skips_busy_and_excluded(monkeypatch):
    monkeypatch.setattr(
        camera, "capture_nodes", lambda: ("/dev/video0", "/dev/video4", "/dev/video6")
    )
    monkeypatch.setattr(camera, "node_in_use", lambda node: node == "/dev/video0")
    assert camera.free_capture_nodes() == ("/dev/video4", "/dev/video6")
    assert camera.free_capture_nodes(exclude="/dev/video4") == ("/dev/video6",)


def test_default_device_falls_back_when_nothing_free(monkeypatch):
    monkeypatch.setattr(camera, "free_capture_nodes", lambda exclude=None: ())
    assert camera.default_device() == "/dev/video0"
