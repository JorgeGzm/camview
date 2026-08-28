"""Janela de configurações: seleção de câmera/modo e controles de imagem.

Aberta a partir da janela principal (tecla ``c`` ou botão direito). A aba
"Câmera" troca dispositivo/resolução reconstruindo o pipeline; a aba
"Imagem" ajusta controles V4L2 (brilho, iluminação 50/60Hz, zoom, ...) ao
vivo, sem interromper o vídeo.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from camview import about, camera, controls, effects, pipeline  # noqa: E402
from camview.config import CaptureConfig, PixelFormat, Shape  # noqa: E402

_SLIDER_DEBOUNCE_MS = 150

# Chave do debounce do slider de tamanho. Enquanto ela existe, quem manda no
# tamanho é o próprio slider — sincronizá-lo aí puxaria o cursor do usuário.
_WINDOW_SIZE_KEY = "__window_size__"

_SHAPE_LABELS = (
    (Shape.SQUARE, "Square"),
    (Shape.ROUNDED, "Rounded corners"),
    (Shape.CIRCLE, "Circle"),
    (Shape.PHONE, "Phone screen (9:16)"),
)

_CONTROL_LABELS = {
    "brightness": "Brightness",
    "contrast": "Contrast",
    "saturation": "Saturation",
    "hue": "Hue",
    "gamma": "Gamma",
    "gain": "Gain",
    "sharpness": "Sharpness",
    "backlight_compensation": "Backlight compensation",
    "power_line_frequency": "Lighting (anti-flicker)",
    "white_balance_automatic": "Automatic white balance",
    "white_balance_temperature": "Color temperature",
    "auto_exposure": "Auto exposure",
    "exposure_time_absolute": "Exposure time",
    "exposure_dynamic_framerate": "Dynamic framerate (exposure)",
    "focus_automatic_continuous": "Autofocus",
    "focus_absolute": "Focus",
    "zoom_absolute": "Zoom",
    "pan_absolute": "Pan",
    "tilt_absolute": "Tilt",
    "led1_mode": "LED",
}


def _label_for(name: str) -> str:
    return _CONTROL_LABELS.get(name, name.replace("_", " ").capitalize())


class SettingsWindow(Gtk.Window):
    """Notebook com as abas Câmera, Imagem, Janela e Sobre."""

    def __init__(self, main_window) -> None:
        super().__init__(title="camview — settings")
        self._main = main_window
        self.set_transient_for(main_window)
        self.set_default_size(420, 480)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.connect("key-press-event", self._on_key)

        self._notebook = Gtk.Notebook()
        self.add(self._notebook)

        self._camera_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._camera_page.set_border_width(12)
        self._notebook.append_page(self._camera_page, Gtk.Label(label="Camera"))

        self._effects_scroll = Gtk.ScrolledWindow()
        self._effects_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._notebook.append_page(self._effects_scroll, Gtk.Label(label="Effects"))

        self._image_scroll = Gtk.ScrolledWindow()
        self._image_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._notebook.append_page(self._image_scroll, Gtk.Label(label="Image"))

        self._window_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._window_page.set_border_width(12)
        self._notebook.append_page(self._window_page, Gtk.Label(label="Window"))

        self._about_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._about_page.set_border_width(12)
        self._notebook.append_page(self._about_page, Gtk.Label(label="About"))

        self._modes: list[tuple[PixelFormat, int, int, int]] = []
        self._device_nodes: list[str] = []
        self._slider_timeouts: dict[str, int] = {}

        self._effect_buttons: dict[str, Gtk.ToggleButton] = {}

        self._build_camera_page()
        self._build_effects_page()
        self._build_image_page()
        self._build_window_page()
        self._build_about_page()
        self.show_all()

    # ------------------------------------------------------------ aba Câmera

    def _build_camera_page(self) -> None:
        page = self._camera_page

        page.pack_start(Gtk.Label(label="Device:", xalign=0), False, False, 0)
        self._device_combo = Gtk.ComboBoxText()
        self._populate_devices()
        page.pack_start(self._device_combo, False, False, 0)

        page.pack_start(Gtk.Label(label="Mode (format / resolution / fps):", xalign=0),
                        False, False, 0)
        self._mode_combo = Gtk.ComboBoxText()
        self._populate_modes(self._current_node())
        page.pack_start(self._mode_combo, False, False, 0)

        self._device_combo.connect("changed", self._on_device_changed)

        apply_button = Gtk.Button(label="Apply")
        apply_button.connect("clicked", self._on_apply)
        page.pack_start(apply_button, False, False, 8)

        self._status = Gtk.Label(label="", xalign=0)
        self._status.set_line_wrap(True)
        page.pack_start(self._status, False, False, 0)

    def _populate_devices(self) -> None:
        self._device_combo.remove_all()
        self._device_nodes = []
        current = self._main.capture.device
        active = 0
        try:
            devices = camera.query_devices()
        except camera.CameraError:
            devices = ()
        for device in devices:
            node = camera.capture_node(device)
            if node is None:
                continue
            short_name = device.name.split(" (")[0]
            self._device_combo.append_text(f"{short_name} — {node}")
            self._device_nodes.append(node)
            if node == current:
                active = len(self._device_nodes) - 1
        if not self._device_nodes:
            self._device_combo.append_text(current)
            self._device_nodes.append(current)
        self._device_combo.set_active(active)

    def _current_node(self) -> str:
        index = self._device_combo.get_active()
        return self._device_nodes[index] if index >= 0 else self._main.capture.device

    def _populate_modes(self, node: str) -> None:
        self._mode_combo.remove_all()
        self._modes = []
        cap = self._main.capture
        active = 0
        try:
            formats = camera.query_formats(node)
        except camera.CameraError:
            formats = ()
        for fmt in formats:
            if fmt.fourcc not in PixelFormat.__members__:
                continue
            pixel_format = PixelFormat[fmt.fourcc]
            for res in fmt.resolutions:
                for fps in res.fps:
                    self._mode_combo.append_text(
                        f"{fmt.fourcc}  {res.width}x{res.height} @ {fps} fps"
                    )
                    self._modes.append((pixel_format, res.width, res.height, fps))
                    if (
                        node == cap.device
                        and pixel_format is cap.pixel_format
                        and (res.width, res.height, fps) == (cap.width, cap.height, cap.fps)
                    ):
                        active = len(self._modes) - 1
        if self._modes:
            self._mode_combo.set_active(active)

    def _on_device_changed(self, combo: Gtk.ComboBoxText) -> None:
        self._populate_modes(self._current_node())

    def _on_apply(self, button: Gtk.Button) -> None:
        index = self._mode_combo.get_active()
        if index < 0:
            self._status.set_text("No modes available for this device.")
            return
        pixel_format, width, height, fps = self._modes[index]
        capture = CaptureConfig(
            device=self._current_node(),
            width=width,
            height=height,
            fps=fps,
            pixel_format=pixel_format,
        )
        self._main.restart(capture)
        self._status.set_text(
            f"Applied: {capture.device} {width}x{height}@{fps} ({pixel_format.value})"
        )
        self._build_image_page()

    # ------------------------------------------------------------ aba Janela

    def _build_window_page(self) -> None:
        page = self._window_page
        page.pack_start(
            Gtk.Label(label="Window size (% of capture):", xalign=0), False, False, 0
        )

        adjustment = Gtk.Adjustment(
            value=self._main.current_scale(),
            lower=10,
            upper=300,
            step_increment=5,
        )
        self._size_scale = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL, adjustment=adjustment
        )
        self._size_scale.set_digits(0)
        self._size_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self._size_scale.connect("value-changed", self._on_size_slider)
        page.pack_start(self._size_scale, False, False, 0)

        presets = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        for percent in (25, 50, 75, 100, 150):
            button = Gtk.Button(label=f"{percent}%")
            button.connect("clicked", self._on_size_preset, percent)
            presets.pack_start(button, True, True, 0)
        page.pack_start(presets, False, False, 0)

        page.pack_start(Gtk.Separator(), False, False, 6)

        self._keep_above_check = Gtk.CheckButton(
            label="Always on top of the other windows"
        )
        self._keep_above_check.set_active(self._main.keep_above)
        self._keep_above_check.connect("toggled", self._on_keep_above_toggled)
        page.pack_start(self._keep_above_check, False, False, 0)

        page.pack_start(
            Gtk.Label(
                label="Tip: in the video window, the mouse wheel and the +/− keys also\n"
                "resize, dragging the edges works like an ordinary window, and the\n"
                "t key toggles “always on top”.",
                xalign=0,
            ),
            False,
            False,
            8,
        )

    def _on_keep_above_toggled(self, button: Gtk.CheckButton) -> None:
        self._main.set_always_on_top(button.get_active())

    def sync_keep_above(self) -> None:
        """Reflete na caixa o que a tecla ``t`` fez, sem disparar o callback."""
        if self._keep_above_check.get_active() == self._main.keep_above:
            return
        self._keep_above_check.handler_block_by_func(self._on_keep_above_toggled)
        self._keep_above_check.set_active(self._main.keep_above)
        self._keep_above_check.handler_unblock_by_func(self._on_keep_above_toggled)

    def _on_size_slider(self, scale: Gtk.Scale) -> None:
        name = _WINDOW_SIZE_KEY
        if name in self._slider_timeouts:
            GLib.source_remove(self._slider_timeouts[name])
        percent = scale.get_value()

        def apply() -> bool:
            self._slider_timeouts.pop(name, None)
            self._main.resize_to_scale(percent)
            return False

        self._slider_timeouts[name] = GLib.timeout_add(_SLIDER_DEBOUNCE_MS, apply)

    def _on_size_preset(self, button: Gtk.Button, percent: int) -> None:
        self._main.resize_to_scale(percent)
        self._size_scale.set_value(percent)

    def sync_size(self) -> None:
        """Reflete no slider o tamanho real da janela.

        Chamado a cada redimensionamento da janela de vídeo — scroll, ``+``/
        ``-``, ``0``, cantos, tela cheia ou arrastar as bordas.
        """
        if _WINDOW_SIZE_KEY in self._slider_timeouts:
            return
        percent = round(self._main.current_scale())
        if percent == round(self._size_scale.get_value()):
            return
        self._size_scale.handler_block_by_func(self._on_size_slider)
        self._size_scale.set_value(percent)
        self._size_scale.handler_unblock_by_func(self._on_size_slider)

    # ----------------------------------------------------------- aba Effects

    def _build_effects_page(self) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(12)

        if not pipeline.color_effects_available():
            warning = Gtk.Label(xalign=0)
            warning.set_markup(
                "<i>Color presets (sepia, cross-process…) need the "
                "gstreamer1.0-plugins-bad package.\nThe other filters work "
                "normally.</i>"
            )
            warning.set_line_wrap(True)
            box.pack_start(warning, False, False, 0)

        box.pack_start(self._effect_group("Filters", effects.INSTAGRAM), False, False, 0)
        box.pack_start(Gtk.Separator(), False, False, 6)
        box.pack_start(self._effect_group("Fun", effects.FUN), False, False, 0)

        self._effects_scroll.add(box)
        self._effects_scroll.show_all()

    def _effect_group(self, title: str, group: tuple[effects.Effect, ...]) -> Gtk.Widget:
        section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        label = Gtk.Label(xalign=0)
        label.set_markup(f"<b>{title}</b>")
        section.pack_start(label, False, False, 0)

        grid = Gtk.FlowBox()
        grid.set_selection_mode(Gtk.SelectionMode.NONE)
        grid.set_max_children_per_line(3)
        grid.set_column_spacing(6)
        grid.set_row_spacing(6)
        for effect in group:
            button = Gtk.ToggleButton(label=effect.label)
            button.set_active(effect.id == self._main.effect.id)
            button.connect("toggled", self._on_effect_toggled, effect)
            self._effect_buttons[effect.id] = button
            grid.add(button)
        section.pack_start(grid, False, False, 0)
        return section

    def _on_effect_toggled(self, button: Gtk.ToggleButton, effect: effects.Effect) -> None:
        if not button.get_active():
            # Clicar no efeito ativo o desliga: volta ao Normal.
            if self._main.effect.id == effect.id:
                self._select_effect(effects.NORMAL)
            return
        self._select_effect(effect)

    def _select_effect(self, effect: effects.Effect) -> None:
        self._main.set_effect(effect)
        for effect_id, button in self._effect_buttons.items():
            active = effect_id == effect.id
            if button.get_active() != active:
                button.handler_block_by_func(self._on_effect_toggled)
                button.set_active(active)
                button.handler_unblock_by_func(self._on_effect_toggled)

    # ------------------------------------------------------------- aba Sobre

    def _build_about_page(self) -> None:
        page = self._about_page
        info = about.collect()

        icon = self._app_icon(72)
        if icon is not None:
            page.pack_start(icon, False, False, 4)

        title = Gtk.Label()
        title.set_markup('<span size="x-large" weight="bold">camview</span>')
        page.pack_start(title, False, False, 0)

        version = Gtk.Label()
        version.set_markup(f'<span size="large">{info.version}</span>')
        page.pack_start(version, False, False, 0)

        summary = Gtk.Label(label=info.summary)
        summary.set_line_wrap(True)
        page.pack_start(summary, False, False, 4)

        grid = Gtk.Grid(column_spacing=16, row_spacing=4, halign=Gtk.Align.CENTER)
        for row, (label, value) in enumerate(info.as_rows()):
            name = Gtk.Label(xalign=1)
            name.set_markup(f"<b>{label}:</b>")
            grid.attach(name, 0, row, 1, 1)
            grid.attach(Gtk.Label(label=value, xalign=0, selectable=True), 1, row, 1, 1)
        page.pack_start(grid, False, False, 8)

        copy = Gtk.Button(label="Copy information")
        copy.set_halign(Gtk.Align.CENTER)
        copy.connect("clicked", self._on_copy_about, info)
        page.pack_start(copy, False, False, 0)

    @staticmethod
    def _app_icon(size: int) -> Gtk.Image | None:
        """Ícone lido do próprio pacote (não depende do tema instalado)."""
        from importlib.resources import files

        from gi.repository import GdkPixbuf

        path = files("camview").joinpath("assets/icon.svg")
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(str(path), size, size)
        except GLib.Error:
            return None
        return Gtk.Image.new_from_pixbuf(pixbuf)

    def _on_copy_about(self, button: Gtk.Button, info: about.AboutInfo) -> None:
        text = "\n".join(f"{label}: {value}" for label, value in info.as_rows())
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(f"camview\n{text}", -1)
        button.set_label("Copied!")
        GLib.timeout_add(1500, lambda: (button.set_label("Copy information"), False)[1])

    # ------------------------------------------------------------ aba Imagem

    def _build_image_page(self) -> None:
        for child in self._image_scroll.get_children():
            self._image_scroll.remove(child)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(12)
        device = self._main.capture.device

        box.pack_start(self._build_shape_section(), False, False, 0)
        box.pack_start(Gtk.Separator(), False, False, 6)

        try:
            device_controls = controls.query_controls(device)
        except camera.CameraError as exc:
            box.pack_start(Gtk.Label(label=str(exc), xalign=0), False, False, 0)
            device_controls = ()

        grid = Gtk.Grid(column_spacing=12, row_spacing=6)
        row = 0
        for control in device_controls:
            label = Gtk.Label(label=_label_for(control.name), xalign=0)
            widget = self._widget_for(device, control)
            if widget is None:
                continue
            widget.set_sensitive(not control.inactive)
            widget.set_hexpand(True)
            grid.attach(label, 0, row, 1, 1)
            grid.attach(widget, 1, row, 1, 1)
            row += 1
        box.pack_start(grid, False, False, 0)

        if device_controls:
            reset = Gtk.Button(label="Restore defaults")
            reset.connect("clicked", self._on_reset, device, device_controls)
            box.pack_start(reset, False, False, 8)

        self._image_scroll.add(box)
        self._image_scroll.show_all()

    def _build_shape_section(self) -> Gtk.Widget:
        section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        section.pack_start(
            Gtk.Label(label="Image outline:", xalign=0), False, False, 0
        )

        self._shape_combo = Gtk.ComboBoxText()
        active = 0
        for i, (shape, label) in enumerate(_SHAPE_LABELS):
            self._shape_combo.append(shape.value, label)
            if shape is self._main.shape:
                active = i
        self._shape_combo.set_active(active)
        self._shape_combo.connect("changed", self._on_shape_changed)
        section.pack_start(self._shape_combo, False, False, 0)

        if not pipeline.crop_available():
            warning = Gtk.Label(xalign=0)
            warning.set_markup(
                "<i>The phone outline crops the image with videocrop, from the "
                "gstreamer1.0-plugins-good package — it is missing, so the "
                "image will not be cropped.</i>"
            )
            warning.set_line_wrap(True)
            section.pack_start(warning, False, False, 0)

        self._radius_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._radius_row.pack_start(
            Gtk.Label(label="Corner radius:", xalign=0), False, False, 0
        )
        adjustment = Gtk.Adjustment(
            value=self._main.radius, lower=4, upper=120, step_increment=2
        )
        self._radius_scale = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL, adjustment=adjustment
        )
        self._radius_scale.set_digits(0)
        self._radius_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self._radius_scale.set_hexpand(True)
        self._radius_scale.connect("value-changed", self._on_radius_slider)
        self._radius_row.pack_start(self._radius_scale, True, True, 0)
        self._radius_row.set_sensitive(self._main.shape.has_corners)
        section.pack_start(self._radius_row, False, False, 0)
        return section

    def _on_shape_changed(self, combo: Gtk.ComboBoxText) -> None:
        shape_id = combo.get_active_id()
        if shape_id is None:
            return
        shape = Shape(shape_id)
        self._main.set_shape(shape, int(self._radius_scale.get_value()))
        self._radius_row.set_sensitive(shape.has_corners)

    def _on_radius_slider(self, scale: Gtk.Scale) -> None:
        name = "__shape_radius__"
        if name in self._slider_timeouts:
            GLib.source_remove(self._slider_timeouts[name])
        radius = int(scale.get_value())

        def apply() -> bool:
            self._slider_timeouts.pop(name, None)
            shape = self._main.shape if self._main.shape.has_corners else Shape.ROUNDED
            self._main.set_shape(shape, radius)
            return False

        self._slider_timeouts[name] = GLib.timeout_add(_SLIDER_DEBOUNCE_MS, apply)

    def _widget_for(self, device: str, control: controls.Control) -> Gtk.Widget | None:
        if isinstance(control, controls.IntControl):
            adjustment = Gtk.Adjustment(
                value=control.value,
                lower=control.minimum,
                upper=control.maximum,
                step_increment=control.step,
            )
            scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adjustment)
            scale.set_digits(0)
            scale.set_value_pos(Gtk.PositionType.RIGHT)
            scale.connect("value-changed", self._on_slider, device, control.name)
            return scale
        if isinstance(control, controls.BoolControl):
            switch = Gtk.Switch(active=control.value, halign=Gtk.Align.START)
            switch.connect("notify::active", self._on_switch, device, control.name)
            return switch
        if isinstance(control, controls.MenuControl):
            combo = Gtk.ComboBoxText()
            active = 0
            for i, (index, text) in enumerate(control.options):
                combo.append(str(index), text)
                if index == control.value:
                    active = i
            combo.set_active(active)
            combo.connect("changed", self._on_menu, device, control.name)
            return combo
        return None

    def _on_slider(self, scale: Gtk.Scale, device: str, name: str) -> None:
        if name in self._slider_timeouts:
            GLib.source_remove(self._slider_timeouts[name])
        value = int(scale.get_value())
        self._slider_timeouts[name] = GLib.timeout_add(
            _SLIDER_DEBOUNCE_MS, self._apply_control, device, name, value
        )

    def _apply_control(self, device: str, name: str, value: int) -> bool:
        self._slider_timeouts.pop(name, None)
        try:
            controls.set_control(device, name, value)
        except camera.CameraError as exc:
            print(exc)
        return False

    def _on_switch(self, switch: Gtk.Switch, _param, device: str, name: str) -> None:
        self._apply_control(device, name, int(switch.get_active()))
        GLib.timeout_add(200, self._refresh_sensitivities)

    def _on_menu(self, combo: Gtk.ComboBoxText, device: str, name: str) -> None:
        active_id = combo.get_active_id()
        if active_id is not None:
            self._apply_control(device, name, int(active_id))
            GLib.timeout_add(200, self._refresh_sensitivities)

    def _refresh_sensitivities(self) -> bool:
        """Auto-controles (ex.: balanço de branco) ativam/desativam outros."""
        self._build_image_page()
        return False

    def _on_reset(self, button: Gtk.Button, device: str, device_controls) -> None:
        controls.reset_controls(device, device_controls)
        self._build_image_page()

    def _on_key(self, widget, event) -> bool:
        if Gdk.keyval_name(event.keyval) == "Escape":
            self.destroy()
            return True
        return False
