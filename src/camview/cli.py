"""Interface de linha de comando: converte argumentos em configuração validada."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from camview import __version__, camera, effects
from camview.config import CaptureConfig, Corner, PixelFormat, Shape, WindowConfig
from camview.effects import Effect


@dataclass(frozen=True)
class CliRequest:
    """O que o usuário pediu na linha de comando."""

    capture: CaptureConfig
    window: WindowConfig
    effect: Effect = effects.NORMAL
    list_formats: bool = False
    check_mode: bool = True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="camview",
        description="Borderless webcam for screencasts.",
        epilog=(
            "Shortcuts: drag=move, scroll/+/-=size, 0=original size, "
            "1-4=corners, m=mirror, t=always on top, f=fullscreen, q/Esc=quit"
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "-d", "--device", default="/dev/video0", help="V4L2 device (default: /dev/video0)"
    )
    parser.add_argument(
        "-w", "--width", type=int, default=1280, help="capture width (default: 1280)"
    )
    parser.add_argument(
        "-H", "--height", type=int, default=720, help="capture height (default: 720)"
    )
    parser.add_argument(
        "-f", "--fps", type=int, default=30, help="frames per second (default: 30)"
    )
    parser.add_argument(
        "--format",
        choices=[fmt.value for fmt in PixelFormat],
        default=PixelFormat.MJPG.value,
        help="camera format (default: mjpg; use --list to see supported ones)",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="window scale relative to the capture (default: 1.0)",
    )
    parser.add_argument(
        "--position",
        choices=[corner.value for corner in Corner],
        help="screen corner to open the window at",
    )
    parser.add_argument(
        "--shape",
        choices=[shape.value for shape in Shape],
        help="image outline: square, rounded, circle or phone "
        "(phone = centered 9:16 portrait crop, like a phone screen; "
        "default: square; rounded if --radius is given)",
    )
    parser.add_argument(
        "--radius", type=int, default=0, help="rounded corner radius in px (default: 0)"
    )
    parser.add_argument(
        "--mirror", action="store_true", help="mirror the image horizontally"
    )
    parser.add_argument(
        "--no-top", action="store_true", help="do not keep the window always on top"
    )
    parser.add_argument(
        "--no-check",
        action="store_true",
        help="do not validate the requested mode against the camera formats",
    )
    parser.add_argument(
        "--effect",
        choices=effects.ids(),
        default=effects.NORMAL.id,
        help="image effect (default: normal)",
    )
    parser.add_argument(
        "--list", action="store_true", help="list camera formats/resolutions and exit"
    )
    return parser


def parse_args(argv: list[str] | None = None) -> CliRequest:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        capture = CaptureConfig(
            device=args.device,
            width=args.width,
            height=args.height,
            fps=args.fps,
            pixel_format=PixelFormat(args.format),
        )
        if args.shape is not None:
            shape = Shape(args.shape)
        else:
            shape = Shape.ROUNDED if args.radius > 0 else Shape.SQUARE
        window = WindowConfig(
            scale=args.scale,
            position=Corner(args.position) if args.position else None,
            shape=shape,
            radius=args.radius,
            mirror=args.mirror,
            keep_above=not args.no_top,
        )
    except ValueError as exc:
        parser.error(str(exc))
    return CliRequest(
        capture=capture,
        window=window,
        effect=effects.by_id(args.effect),
        list_formats=args.list,
        check_mode=not args.no_check,
    )


def _check_capture_mode(capture: CaptureConfig) -> None:
    """Avisa cedo se a câmera não suporta o modo pedido (melhor que erro do GStreamer)."""
    try:
        formats = camera.query_formats(capture.device)
    except camera.CameraError as exc:
        print(f"warning: could not validate the mode ({exc})", file=sys.stderr)
        return
    if not formats or camera.supports(
        formats, capture.pixel_format, capture.width, capture.height, capture.fps
    ):
        return
    print(
        f"error: {capture.device} does not support "
        f"{capture.pixel_format.fourcc} {capture.width}x{capture.height}@{capture.fps}fps.\n"
        f"Available modes:\n{camera.render(formats)}",
        file=sys.stderr,
    )
    raise SystemExit(1)


def main(argv: list[str] | None = None) -> int:
    request = parse_args(argv)
    if request.list_formats:
        try:
            print(camera.render(camera.query_formats(request.capture.device)))
        except camera.CameraError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        return 0
    if request.check_mode:
        _check_capture_mode(request.capture)
    from camview.window import run

    run(request.capture, request.window, request.effect)
    return 0


if __name__ == "__main__":
    sys.exit(main())
