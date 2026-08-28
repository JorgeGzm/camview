#!/bin/bash
# Monta o AppImage do camview em releases/.
#
# O AppImage embute o pacote Python e os typelibs do GStreamer que costumam
# faltar (GstVideo & cia.), e usa o Python/GTK/GStreamer do sistema — as
# mesmas dependências base do Cheese, presentes em qualquer desktop GNOME.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(grep -m1 '^version' "$ROOT/pyproject.toml" | cut -d'"' -f2)"
ARCH="x86_64"
APPDIR="$ROOT/build/AppDir"
TOOL="$ROOT/build/appimagetool"
OUT_DIR="$ROOT/releases"
OUT="$OUT_DIR/camview-$VERSION-$ARCH.AppImage"
PIP="$ROOT/.venv/bin/pip"
GIR_PKG="gir1.2-gst-plugins-base-1.0"

WHEEL="$(ls "$ROOT"/dist/camview-"$VERSION"-*.whl 2>/dev/null | head -1)"
[ -n "$WHEEL" ] || { echo "error: wheel not found; run 'make build' first" >&2; exit 1; }

echo "==> Assembling the AppDir for camview $VERSION"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib/camview" "$APPDIR/usr/lib/girepository-1.0" \
         "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/scalable/apps"

"$PIP" install --quiet --no-deps --target "$APPDIR/usr/lib/camview" "$WHEEL"

# typelibs do gst-plugins-base (GstVideo etc.): usa os do sistema, os já
# baixados no venv, ou baixa o pacote sem sudo
if ls /usr/lib/*/girepository-1.0/GstVideo-1.0.typelib >/dev/null 2>&1; then
    cp /usr/lib/*/girepository-1.0/Gst{Video,Audio,Tag,Pbutils,Allocators,App}-1.0.typelib \
       "$APPDIR/usr/lib/girepository-1.0/" 2>/dev/null || \
    cp /usr/lib/*/girepository-1.0/GstVideo-1.0.typelib "$APPDIR/usr/lib/girepository-1.0/"
elif [ -f "$ROOT/.venv/girepository/GstVideo-1.0.typelib" ]; then
    cp "$ROOT/.venv/girepository/"*.typelib "$APPDIR/usr/lib/girepository-1.0/"
else
    tmp="$(mktemp -d)"
    ( cd "$tmp" && apt-get download "$GIR_PKG" && dpkg -x "$GIR_PKG"*.deb x )
    find "$tmp/x" -name '*.typelib' -exec cp {} "$APPDIR/usr/lib/girepository-1.0/" \;
    rm -rf "$tmp"
fi

# plugin coloreffects (presets de cor dos filtros): do sistema, do venv, ou baixado
mkdir -p "$APPDIR/usr/lib/gstreamer-1.0"
if ls /usr/lib/*/gstreamer-1.0/libgstcoloreffects.so >/dev/null 2>&1; then
    cp /usr/lib/*/gstreamer-1.0/libgstcoloreffects.so "$APPDIR/usr/lib/gstreamer-1.0/"
elif [ -f "$ROOT/.venv/gstplugins/libgstcoloreffects.so" ]; then
    cp "$ROOT/.venv/gstplugins/libgstcoloreffects.so" "$APPDIR/usr/lib/gstreamer-1.0/"
else
    tmp="$(mktemp -d)"
    ( cd "$tmp" && apt-get download gstreamer1.0-plugins-bad && \
      dpkg -x gstreamer1.0-plugins-bad*.deb x )
    find "$tmp/x" -name 'libgstcoloreffects.so' \
         -exec cp {} "$APPDIR/usr/lib/gstreamer-1.0/" \;
    rm -rf "$tmp"
fi

cp "$ROOT/src/camview/assets/camview.desktop" "$APPDIR/camview.desktop"
cp "$ROOT/src/camview/assets/camview.desktop" "$APPDIR/usr/share/applications/"
cp "$ROOT/src/camview/assets/icon.svg" "$APPDIR/camview.svg"
cp "$ROOT/src/camview/assets/icon.svg" \
   "$APPDIR/usr/share/icons/hicolor/scalable/apps/camview.svg"

cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
export PYTHONPATH="$HERE/usr/lib/camview${PYTHONPATH:+:$PYTHONPATH}"
export GI_TYPELIB_PATH="$HERE/usr/lib/girepository-1.0${GI_TYPELIB_PATH:+:$GI_TYPELIB_PATH}"
export GST_PLUGIN_PATH="$HERE/usr/lib/gstreamer-1.0${GST_PLUGIN_PATH:+:$GST_PLUGIN_PATH}"
exec python3 -m camview "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

# Release fixa (não a tag móvel "continuous") + hash conferido: garante que o
# binário usado na build é sempre o mesmo e não foi adulterado em trânsito.
TOOL_VERSION="1.9.1"
TOOL_URL="https://github.com/AppImage/appimagetool/releases/download/$TOOL_VERSION/appimagetool-$ARCH.AppImage"
TOOL_SHA256="ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"

if [ ! -x "$TOOL" ]; then
    echo "==> Downloading appimagetool $TOOL_VERSION"
    curl -sSL -o "$TOOL.part" "$TOOL_URL"
    actual="$(sha256sum "$TOOL.part" | cut -d' ' -f1)"
    if [ "$actual" != "$TOOL_SHA256" ]; then
        rm -f "$TOOL.part"
        echo "error: appimagetool hash mismatch!" >&2
        echo "  expected: $TOOL_SHA256" >&2
        echo "  got:      $actual" >&2
        exit 1
    fi
    mv "$TOOL.part" "$TOOL"
    chmod +x "$TOOL"
fi

echo "==> Building $OUT"
mkdir -p "$OUT_DIR"
ARCH="$ARCH" "$TOOL" --appimage-extract-and-run "$APPDIR" "$OUT" >/dev/null
echo "==> Done: ${OUT#"$ROOT"/} ($(du -h "$OUT" | cut -f1))"
