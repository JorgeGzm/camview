"""Informações sobre o programa e o ambiente (aba "Sobre").

A coleta é código puro e testável; a renderização fica na janela de
configurações. As versões do ambiente também servem para diagnosticar
relatos de problema ("qual GStreamer você está usando?").
"""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass

from camview import __version__

SUMMARY = "Borderless webcam for screencasts"
HOMEPAGE = "https://github.com/JorgeGzm/camview"
LICENSE = "MIT"


@dataclass(frozen=True)
class AboutInfo:
    version: str
    summary: str
    license: str
    homepage: str
    python: str
    gtk: str
    gstreamer: str
    platform: str

    def as_rows(self) -> tuple[tuple[str, str], ...]:
        """Pares (rótulo, valor) para exibição, na ordem de leitura."""
        return (
            ("Version", self.version),
            ("License", self.license),
            ("Python", self.python),
            ("GTK", self.gtk),
            ("GStreamer", self.gstreamer),
            ("System", self.platform),
        )


def _gtk_version() -> str:
    # require_version antes do import: sem isso o gi poderia carregar o GTK4 e
    # conflitar com o GTK3 usado pela interface.
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk

        return f"{Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}"
    except Exception:  # noqa: BLE001 - ambiente sem GTK não deve quebrar o Sobre
        return "unavailable"


def _gstreamer_version() -> str:
    try:
        import gi

        gi.require_version("Gst", "1.0")
        from gi.repository import Gst

        major, minor, micro, _nano = Gst.version()
        return f"{major}.{minor}.{micro}"
    except Exception:  # noqa: BLE001 - idem
        return "unavailable"


def collect() -> AboutInfo:
    """Reúne as informações exibidas na aba Sobre."""
    return AboutInfo(
        version=__version__,
        summary=SUMMARY,
        license=LICENSE,
        homepage=HOMEPAGE,
        python=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        gtk=_gtk_version(),
        gstreamer=_gstreamer_version(),
        platform=f"{platform.system()} {platform.release()}",
    )
