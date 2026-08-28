#!/bin/bash
# Builds the camview .deb into releases/.
#
# Nothing is compiled: camview is pure Python (Architecture: all). The
# package ships the Python code, the launcher, the icon and the .desktop
# entry, and declares the GTK/GStreamer packages in Depends, so apt pulls
# the whole runtime in by itself.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(grep -m1 '^version' "$ROOT/pyproject.toml" | cut -d'"' -f2)"
PKGDIR="$ROOT/build/deb"
OUT_DIR="$ROOT/releases"
OUT="$OUT_DIR/camview_${VERSION}_all.deb"
PIP="$ROOT/.venv/bin/pip"

WHEEL="$(ls "$ROOT"/dist/camview-"$VERSION"-*.whl 2>/dev/null | head -1)"
[ -n "$WHEEL" ] || { echo "error: wheel not found; run 'make build' first" >&2; exit 1; }

echo "==> Assembling the package tree for camview $VERSION"
rm -rf "$PKGDIR"
mkdir -p "$PKGDIR/DEBIAN" \
         "$PKGDIR/usr/lib/python3/dist-packages" \
         "$PKGDIR/usr/bin" \
         "$PKGDIR/usr/share/applications" \
         "$PKGDIR/usr/share/icons/hicolor/scalable/apps" \
         "$PKGDIR/usr/share/doc/camview"

# dist-packages is where Debian puts system Python modules. --no-deps
# because every dependency is a distro package, declared in Depends below.
# --no-compile because a .pyc built here is tied to this machine's Python
# version and would be dead weight (or wrong) on any other one.
"$PIP" install --quiet --no-deps --no-compile \
       --target "$PKGDIR/usr/lib/python3/dist-packages" "$WHEEL"
# pip drops the console script here; the package ships its own launcher.
rm -rf "$PKGDIR/usr/lib/python3/dist-packages/bin"
find "$PKGDIR" -name __pycache__ -type d -exec rm -rf {} +
# Bookkeeping pip writes for its own uninstall logic. It has no meaning in a
# dpkg-managed package, and direct_url.json would ship the build machine's
# absolute path inside the published .deb.
rm -f "$PKGDIR"/usr/lib/python3/dist-packages/camview-*.dist-info/{INSTALLER,REQUESTED,direct_url.json}

cat > "$PKGDIR/usr/bin/camview" <<'LAUNCHER'
#!/usr/bin/python3
import sys

from camview.cli import main

sys.exit(main())
LAUNCHER
chmod 755 "$PKGDIR/usr/bin/camview"

cp "$ROOT/src/camview/assets/camview.desktop" "$PKGDIR/usr/share/applications/"
cp "$ROOT/src/camview/assets/icon.svg" \
   "$PKGDIR/usr/share/icons/hicolor/scalable/apps/camview.svg"
cp "$ROOT/LICENSE" "$PKGDIR/usr/share/doc/camview/copyright"

cat > "$PKGDIR/DEBIAN/control" <<CONTROL
Package: camview
Version: $VERSION
Section: video
Priority: optional
Architecture: all
Maintainer: Jorge Guzman <jorge@gzm-emb.com>
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-3.0, gir1.2-gstreamer-1.0,
 gir1.2-gst-plugins-base-1.0, gstreamer1.0-plugins-base,
 gstreamer1.0-plugins-good, v4l-utils
Recommends: gstreamer1.0-plugins-bad
Homepage: https://github.com/JorgeGzm/camview
Description: borderless webcam overlay for screencasts and live streams
 camview shows your webcam in a clean window, with no title bar and no
 buttons, always on top of whatever you are recording. It is meant to be
 laid over a screen recording while you talk over code or show a board.
 .
 The image can be shown as a circle, a rectangle, with rounded corners or as
 a phone screen (9:16 portrait), and resized with the scroll wheel, the +/-
 keys or by dragging the edges. Instagram-like filters and the camera's own
 controls (brightness, zoom, focus) apply live, without restarting the
 video.
 .
 It needs an X11 session and uses no network at all.
CONTROL

# Icon and .desktop caches are per-system, so they are refreshed on install
# and on removal. Both tools are optional: a headless box may not have them.
cat > "$PKGDIR/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -f -t /usr/share/icons/hicolor || true
    fi
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
fi
POSTINST

cat > "$PKGDIR/DEBIAN/postrm" <<'POSTRM'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -f -t /usr/share/icons/hicolor || true
    fi
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
fi
POSTRM

# A build machine's umask can leave group-writable files behind (664), which
# is not what an apt-installed package should look like: 644 for files, 755
# for directories and for what has to run.
find "$PKGDIR" -type d -exec chmod 755 {} +
find "$PKGDIR" -type f -exec chmod 644 {} +
chmod 755 "$PKGDIR/usr/bin/camview" "$PKGDIR/DEBIAN/postinst" "$PKGDIR/DEBIAN/postrm"

echo "==> Building $OUT"
mkdir -p "$OUT_DIR"
# --root-owner-group keeps every file owned by root:root without needing
# fakeroot, which is what a package installed by apt expects.
dpkg-deb --build --root-owner-group "$PKGDIR" "$OUT" >/dev/null
echo "==> Done: ${OUT#"$ROOT"/} ($(du -h "$OUT" | cut -f1))"
