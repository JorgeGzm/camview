# docs

Images used by the README.

| file | where it shows up |
|---|---|
| `demo.gif` | right below the title, in the [README](../README.md) |
| `icon.png` | the app icon at the top of the README |

The current `demo.gif` came from a 77 s screencast (a `.webm` from the GNOME
recorder), trimmed to the 40 s to 50 s stretch, where the outline goes from
circle to phone screen. It ended up at 800x475, 10 frames per second, 3.8 MB.

Two things matter for how sharp it looks. First, **crop instead of scaling**:
the recording is a whole 2115x947 desktop, and shrinking all of it to fit a
README leaves the app tiny and mushy. Cropping to the region where things
happen (`crop=1230:730:700:0` here) keeps the app close to its real size.
Second, **denoise before converting**: webcam sensor noise changes every
pixel on every frame, which a GIF cannot compress at all. `hqdn3d` cut this
one from 19 MB to under 4 MB, and it looks cleaner too.

## Recording `demo.gif`

A short clip (10 to 15 s) showing what only makes sense once you see it:
dragging the window, growing it with the scroll wheel, switching the outline
to circle and to phone.

**The easy way**: [Peek](https://github.com/phw/peek). Open it, place the
frame over the area you want to record, hit record, and save straight to
`docs/demo.gif`.

**From the terminal**: record the screen with ffmpeg and convert it using a
palette, which is what keeps the GIF small and free of color banding:

```bash
# 1. record 15 s of a screen region: -video_size WIDTHxHEIGHT -i $DISPLAY+X,Y
ffmpeg -f x11grab -video_size 900x600 -framerate 15 -i "$DISPLAY+100,100" -t 15 /tmp/screencast.mp4

# 2. build the palette and convert
ffmpeg -i /tmp/screencast.mp4 -vf "fps=12,scale=800:-1:flags=lanczos,palettegen" -y /tmp/palette.png
ffmpeg -i /tmp/screencast.mp4 -i /tmp/palette.png \
       -lavfi "fps=12,scale=800:-1:flags=lanczos[x];[x][1:v]paletteuse" -y docs/demo.gif
```

To find the exact position and size of a window:

```bash
xwininfo -name camview     # X, Y, width and height of the video window
```

Keep the file under ~5 MB: GitHub loads the whole GIF on the project page.
If it gets too big, reduce the width (`scale=640:-1`) or the frame rate
(`fps=10`).
