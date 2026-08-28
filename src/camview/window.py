"""Janela GTK de exibição (a View — única camada que toca GTK/GStreamer).

Todo o restante do pacote é código puro; este módulo apenas liga a
configuração validada ao toolkit gráfico e ao pipeline construído pelo
``PipelineBuilder``.
"""

from __future__ import annotations

import math
import sys

import gi

try:
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("GdkX11", "3.0")
    gi.require_version("Gst", "1.0")
    gi.require_version("GstVideo", "1.0")
except ValueError as exc:
    sys.exit(
        f"error: missing introspection library ({exc}).\n"
        "Install with: sudo apt install gir1.2-gtk-3.0 gir1.2-gstreamer-1.0 "
        "gir1.2-gst-plugins-base-1.0\n"
        "Or run via 'make run', which downloads a local copy without sudo."
    )
from gi.repository import Gdk, GdkX11, GLib, Gst, GstVideo, Gtk  # noqa: E402, F401

from camview.config import CaptureConfig, Corner, Shape, WindowConfig  # noqa: E402
from camview.effects import NORMAL, Effect  # noqa: E402
from camview.geometry import (  # noqa: E402
    NO_CROP,
    Rect,
    centered_crop,
    clamp_radius,
    corner_origin,
    crop_borders,
    edge_at,
    inscribed_circle,
    scaled_size,
    sized_by_height,
)
from camview.pipeline import (  # noqa: E402
    FLIP_ELEMENT,
    PipelineBuilder,
    apply_crop,
    apply_effect,
    crop_available,
)

RESIZE_STEP = 1.1
CORNER_MARGIN = 16
EDGE_MARGIN = 14
DEFAULT_RADIUS = 24

_EDGE_TO_GDK = {
    "north": Gdk.WindowEdge.NORTH,
    "south": Gdk.WindowEdge.SOUTH,
    "west": Gdk.WindowEdge.WEST,
    "east": Gdk.WindowEdge.EAST,
    "north-west": Gdk.WindowEdge.NORTH_WEST,
    "north-east": Gdk.WindowEdge.NORTH_EAST,
    "south-west": Gdk.WindowEdge.SOUTH_WEST,
    "south-east": Gdk.WindowEdge.SOUTH_EAST,
}

_EDGE_TO_CURSOR = {
    "north": "n-resize",
    "south": "s-resize",
    "west": "w-resize",
    "east": "e-resize",
    "north-west": "nw-resize",
    "north-east": "ne-resize",
    "south-west": "sw-resize",
    "south-east": "se-resize",
}

_CORNER_KEYS = {
    "1": Corner.TOP_LEFT,
    "2": Corner.TOP_RIGHT,
    "3": Corner.BOTTOM_LEFT,
    "4": Corner.BOTTOM_RIGHT,
}


class CamViewWindow(Gtk.Window):
    def __init__(
        self,
        capture: CaptureConfig,
        window: WindowConfig,
        effect: Effect = NORMAL,
    ) -> None:
        super().__init__(title="camview")
        self._capture = capture
        self._config = window
        self._keep_above = window.keep_above
        self._mirrored = window.mirror
        self._shape = window.shape
        self._radius = window.radius if window.radius > 0 else DEFAULT_RADIUS
        self._xid: int | None = None

        self.set_decorated(False)
        self.set_keep_above(self._keep_above)
        view_width, view_height = self._view_size()
        self.set_default_size(
            round(view_width * window.scale), round(view_height * window.scale)
        )
        input_mask = (
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.SCROLL_MASK
            | Gdk.EventMask.KEY_PRESS_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.set_events(input_mask)

        self._video_area = Gtk.DrawingArea()
        self._video_area.set_double_buffered(False)
        self._video_area.add_events(input_mask)
        self.add(self._video_area)

        self.connect("destroy", self.quit)
        self.connect("key-press-event", self._on_key_press)
        self.connect("size-allocate", self._on_size_allocate)
        for widget in (self, self._video_area):
            widget.connect("button-press-event", self._on_button_press)
            widget.connect("scroll-event", self._on_scroll)
            widget.connect("motion-notify-event", self._on_motion)
        self._video_area.connect("realize", self._on_realize)
        self._apply_aspect_hints()

        self._pipeline = None
        self._settings: Gtk.Window | None = None
        self._effect = effect
        self._create_pipeline()

    @property
    def capture(self) -> CaptureConfig:
        """Configuração de captura em uso (lida pela janela de configurações)."""
        return self._capture

    @property
    def effect(self) -> Effect:
        """Efeito de imagem em uso."""
        return self._effect

    def set_effect(self, effect: Effect) -> None:
        """Troca o efeito.

        Filtros de cor são aplicados ao vivo (propriedades). Efeitos que usam
        um elemento extra (agingtv, edgetv, ...) exigem reconstruir o pipeline.
        """
        needs_rebuild = effect.element != self._effect.element
        self._effect = effect
        if needs_rebuild:
            self.restart(self._capture)
        else:
            apply_effect(self._pipeline, effect)

    def _create_pipeline(self) -> None:
        self._pipeline = (
            PipelineBuilder()
            .with_capture(self._capture)
            .with_mirror(self._mirrored)
            .with_effect(self._effect)
            .with_crop(self._crop_borders())
            .build()
        )
        self._flip = self._pipeline.get_by_name(FLIP_ELEMENT)

        bus = self._pipeline.get_bus()
        bus.set_sync_handler(self._on_bus_sync)
        bus.add_signal_watch()
        bus.connect("message::error", self._on_bus_error)

    def restart(self, capture: CaptureConfig) -> None:
        """Troca câmera/modo reconstruindo o pipeline sem fechar a janela."""
        self._pipeline.get_bus().remove_signal_watch()
        self._pipeline.set_state(Gst.State.NULL)
        self._capture = capture
        self._create_pipeline()
        self._apply_aspect_hints()
        width, _ = self.get_size()
        self.resize(*scaled_size(width, *self._view_size(), 1.0))
        self._pipeline.set_state(Gst.State.PLAYING)

    # -- vídeo -----------------------------------------------------------

    def _on_realize(self, widget: Gtk.Widget) -> None:
        self._xid = widget.get_window().get_xid()

    def _on_bus_sync(self, bus: Gst.Bus, message: Gst.Message) -> Gst.BusSyncReply:
        if GstVideo.is_video_overlay_prepare_window_handle_message(message):
            message.src.set_window_handle(self._xid)
            return Gst.BusSyncReply.DROP
        return Gst.BusSyncReply.PASS

    def _on_bus_error(self, bus: Gst.Bus, message: Gst.Message) -> None:
        err, debug = message.parse_error()
        print(f"pipeline error: {err.message}", file=sys.stderr)
        if debug:
            print(f"detail: {debug}", file=sys.stderr)
        print(
            f"hint: list supported modes with: camview --list -d {self._capture.device}",
            file=sys.stderr,
        )
        self.quit()

    # -- interação -------------------------------------------------------

    def _pointer_edge(self, event) -> str | None:
        width, height = self.get_size()
        origin_x, origin_y = self.get_window().get_root_origin()
        return edge_at(
            event.x_root - origin_x, event.y_root - origin_y, width, height, EDGE_MARGIN
        )

    def _on_button_press(self, widget: Gtk.Widget, event: Gdk.EventButton) -> bool:
        if event.button == 1:
            edge = self._pointer_edge(event)
            if edge is not None:
                self.begin_resize_drag(
                    _EDGE_TO_GDK[edge],
                    event.button,
                    int(event.x_root),
                    int(event.y_root),
                    event.time,
                )
            else:
                self.begin_move_drag(
                    event.button, int(event.x_root), int(event.y_root), event.time
                )
        elif event.button == 3:
            self.open_settings()
        return True

    def _on_motion(self, widget: Gtk.Widget, event: Gdk.EventMotion) -> bool:
        edge = self._pointer_edge(event)
        cursor = None
        if edge is not None:
            cursor = Gdk.Cursor.new_from_name(self.get_display(), _EDGE_TO_CURSOR[edge])
        self.get_window().set_cursor(cursor)
        return False

    def open_settings(self) -> None:
        from camview.settings import SettingsWindow

        if self._settings is not None and self._settings.get_visible():
            self._settings.present()
            return
        self._settings = SettingsWindow(self)

    def _on_scroll(self, widget: Gtk.Widget, event: Gdk.EventScroll) -> bool:
        if event.direction == Gdk.ScrollDirection.UP:
            self._resize_by(RESIZE_STEP)
        elif event.direction == Gdk.ScrollDirection.DOWN:
            self._resize_by(1 / RESIZE_STEP)
        return True

    def _on_key_press(self, widget: Gtk.Widget, event: Gdk.EventKey) -> bool:
        key = Gdk.keyval_name(event.keyval)
        if key in ("q", "Escape"):
            self.quit()
        elif key in ("plus", "equal", "KP_Add"):
            self._resize_by(RESIZE_STEP)
        elif key in ("minus", "KP_Subtract"):
            self._resize_by(1 / RESIZE_STEP)
        elif key == "0":
            self.resize(*self._view_size())
        elif key in _CORNER_KEYS:
            self.snap_to_corner(_CORNER_KEYS[key])
        elif key == "c":
            self.open_settings()
        elif key == "m":
            self._toggle_mirror()
        elif key == "t":
            self._toggle_keep_above()
        elif key == "f":
            self._toggle_fullscreen()
        return True

    def _resize_by(self, factor: float) -> None:
        width, _ = self.get_size()
        self.resize(*scaled_size(width, *self._view_size(), factor))

    def resize_to_scale(self, percent: float) -> None:
        """Redimensiona para uma porcentagem do tamanho exibido."""
        view_width, view_height = self._view_size()
        width = max(1, round(view_width * percent / 100))
        self.resize(*scaled_size(width, view_width, view_height, 1.0))

    def current_scale(self) -> float:
        """Tamanho atual da janela como porcentagem do tamanho exibido."""
        width, _ = self.get_size()
        return width * 100 / self._view_size()[0]

    def _apply_aspect_hints(self) -> None:
        """Trava a proporção da imagem exibida nos redimensionamentos interativos."""
        view_width, view_height = self._view_size()
        geometry = Gdk.Geometry()
        geometry.min_aspect = geometry.max_aspect = view_width / view_height
        self.set_geometry_hints(None, geometry, Gdk.WindowHints.ASPECT)

    def _toggle_mirror(self) -> None:
        self._mirrored = not self._mirrored
        self._flip.set_property("method", "horizontal-flip" if self._mirrored else "none")

    @property
    def keep_above(self) -> bool:
        """Se a janela fica à frente das outras (lido pelas configurações)."""
        return self._keep_above

    def set_always_on_top(self, enabled: bool) -> None:
        """Liga/desliga o "sempre no topo" (tecla ``t`` ou a caixa nas configurações).

        Mantém a caixa das configurações em dia quando a troca vem do teclado.
        """
        self._keep_above = enabled
        self.set_keep_above(enabled)
        print("always on top:", "on" if enabled else "off")
        if self._settings is not None and self._settings.get_visible():
            self._settings.sync_keep_above()

    def _toggle_keep_above(self) -> None:
        self.set_always_on_top(not self._keep_above)

    def _toggle_fullscreen(self) -> None:
        if self.get_window().get_state() & Gdk.WindowState.FULLSCREEN:
            self.unfullscreen()
        else:
            self.fullscreen()

    def snap_to_corner(self, corner: Corner) -> None:
        monitor = self.get_display().get_monitor_at_window(self.get_window())
        area = monitor.get_workarea()
        width, height = self.get_size()
        workarea = Rect(area.x, area.y, area.width, area.height)
        self.move(*corner_origin(workarea, width, height, corner, CORNER_MARGIN))

    # -- contorno da imagem -------------------------------------------------

    @property
    def shape(self) -> Shape:
        return self._shape

    @property
    def radius(self) -> int:
        return self._radius

    def _crop(self) -> Rect | None:
        """Região da captura que o contorno atual mostra (None = tudo)."""
        aspect = self._shape.aspect
        if aspect is None or not crop_available():
            return None
        return centered_crop(self._capture.width, self._capture.height, aspect)

    def _crop_borders(self) -> tuple[int, int, int, int]:
        crop = self._crop()
        if crop is None:
            return NO_CROP
        return crop_borders(self._capture.width, self._capture.height, crop)

    def _view_size(self) -> tuple[int, int]:
        """Tamanho da imagem exibida — a captura, já recortada pelo contorno."""
        crop = self._crop()
        if crop is None:
            return self._capture.width, self._capture.height
        return crop.width, crop.height

    def set_shape(self, shape: Shape, radius: int | None = None) -> None:
        """Troca o contorno ao vivo (usado pela janela de configurações)."""
        previous_view = self._view_size()
        self._shape = shape
        if radius is not None and radius > 0:
            self._radius = radius
        if self._view_size() != previous_view:
            # Recorte novo: o vídeo muda de proporção, e a janela o acompanha
            # mantendo a altura (virar retrato não pode estourar a tela).
            apply_crop(self._pipeline, self._crop_borders())
            self._apply_aspect_hints()
            _, height = self.get_size()
            self.resize(*sized_by_height(height, *self._view_size()))
        if self.get_realized():
            width, height = self.get_size()
            self._apply_shape(width, height)

    def _on_size_allocate(self, widget: Gtk.Widget, allocation: Gdk.Rectangle) -> None:
        if not self.get_realized():
            return
        self._apply_shape(allocation.width, allocation.height)
        if self._settings is not None and self._settings.get_visible():
            self._settings.sync_size()

    def _apply_shape(self, width: int, height: int) -> None:
        if self._shape is Shape.SQUARE:
            self.get_window().shape_combine_region(None, 0, 0)
            return
        import cairo

        surface = cairo.ImageSurface(cairo.FORMAT_A8, width, height)
        ctx = cairo.Context(surface)
        if self._shape is Shape.CIRCLE:
            cx, cy, r = inscribed_circle(width, height)
            ctx.arc(cx, cy, r, 0, 2 * math.pi)
        else:  # Shape.ROUNDED e Shape.PHONE
            radius = clamp_radius(self._radius, width, height)
            ctx.new_sub_path()
            ctx.arc(width - radius, radius, radius, -math.pi / 2, 0)
            ctx.arc(width - radius, height - radius, radius, 0, math.pi / 2)
            ctx.arc(radius, height - radius, radius, math.pi / 2, math.pi)
            ctx.arc(radius, radius, radius, math.pi, 3 * math.pi / 2)
            ctx.close_path()
        ctx.set_source_rgba(1, 1, 1, 1)
        ctx.fill()
        region = Gdk.cairo_region_create_from_surface(surface)
        self.get_window().shape_combine_region(region, 0, 0)

    # -- ciclo de vida -----------------------------------------------------

    def start(self) -> None:
        self.show_all()
        if self._config.position is not None:
            GLib.idle_add(self.snap_to_corner, self._config.position)
        self._pipeline.set_state(Gst.State.PLAYING)

    def quit(self, *_args) -> None:
        self._pipeline.set_state(Gst.State.NULL)
        Gtk.main_quit()


def _set_application_icon() -> None:
    """Usa o ícone do pacote em todas as janelas (barra de tarefas, alt-tab)."""
    from importlib.resources import files

    icon = files("camview").joinpath("assets/icon.svg")
    try:
        Gtk.Window.set_default_icon_from_file(str(icon))
    except GLib.Error as exc:
        print(f"warning: could not load the icon ({exc.message})", file=sys.stderr)


def run(capture: CaptureConfig, window: WindowConfig, effect: Effect = NORMAL) -> None:
    """Inicializa GStreamer/GTK e entra no loop principal."""
    # WM_CLASS estável para o GNOME associar a janela ao camview.desktop
    # (é assim que o dock encontra o ícone), mesmo rodando via python -m
    GLib.set_prgname("camview")
    GLib.set_application_name("camview")
    Gst.init(None)
    _set_application_icon()
    view = CamViewWindow(capture, window, effect)
    view.start()
    print(
        f"camview: {capture.device} {capture.width}x{capture.height}@{capture.fps} "
        f"({capture.pixel_format.value}) — q/Esc quits, drag to move, "
        "scroll resizes, m mirrors, 1-4 corners, "
        "c/right-click opens settings"
    )
    Gtk.main()
