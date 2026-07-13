"""Render the 'Otto' macOS app icon (rounded-square, indigo→sky gradient, glowing pulse orb)
and pack a multi-size Otto.icns. No macOS tools needed — the icns is packed by hand.

Usage:  uv run --with pillow python desktop/make_icon.py [--out PATH] [--preview PATH]
Regenerates desktop/Otto.app/Contents/Resources/Otto.icns by default (see `make app`)."""

import argparse
import struct
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SS = 2  # supersample factor for crisp anti-aliasing
BASE = 1024


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def vertical_gradient(w, h, top, bottom):
    strip = Image.new("RGB", (1, h))
    px = strip.load()
    for y in range(h):
        px[0, y] = lerp(top, bottom, y / (h - 1))
    return strip.resize((w, h))


def render(size_px: int) -> Image.Image:
    W = size_px * SS
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))

    # rounded-square body with a vertical indigo→sky gradient
    margin = int(W * 0.085)
    radius = int((W - 2 * margin) * 0.2237)  # macOS 11 squircle-ish corner
    grad = vertical_gradient(W, W, (79, 70, 229), (14, 165, 233)).convert("RGBA")
    mask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [margin, margin, W - margin, W - margin], radius=radius, fill=255
    )
    img.paste(grad, (0, 0), mask)

    # soft top gloss for depth
    gloss = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    gd = ImageDraw.Draw(gloss)
    gd.rounded_rectangle(
        [margin, margin, W - margin, int(W * 0.52)],
        radius=radius,
        fill=(255, 255, 255, 42),
    )
    gloss = gloss.filter(ImageFilter.GaussianBlur(W * 0.02))
    img = Image.alpha_composite(img, Image.composite(gloss, Image.new("RGBA", (W, W)), mask))

    cx = cy = W // 2

    # pulse rings radiating out (thin, fading)
    rings = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rings)
    for r, a in [(int(W * 0.30), 70), (int(W * 0.375), 40)]:
        lw = max(2, int(W * 0.010))
        rd.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255, a), width=lw)
    rings = rings.filter(ImageFilter.GaussianBlur(W * 0.004))
    img = Image.alpha_composite(img, rings)

    # glowing core orb (radial white→soft), with a specular highlight
    orb_r = int(W * 0.205)
    glow = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse(
        [cx - int(orb_r * 1.6), cy - int(orb_r * 1.6), cx + int(orb_r * 1.6), cy + int(orb_r * 1.6)],
        fill=(180, 220, 255, 90),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(W * 0.03))
    img = Image.alpha_composite(img, glow)

    orb = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    od = ImageDraw.Draw(orb)
    # build radial gradient orb by stacking fading circles
    steps = 60
    for i in range(steps, 0, -1):
        t = i / steps
        rr = int(orb_r * t)
        col = lerp((219, 234, 254), (255, 255, 255), 1 - t)  # edge bluish → bright center
        od.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(*col, 255))
    # specular highlight
    hx, hy, hr = cx - int(orb_r * 0.33), cy - int(orb_r * 0.36), int(orb_r * 0.42)
    hl = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    ImageDraw.Draw(hl).ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=(255, 255, 255, 150))
    hl = hl.filter(ImageFilter.GaussianBlur(W * 0.02))
    orb = Image.alpha_composite(orb, hl)
    img = Image.alpha_composite(img, orb)

    return img.resize((size_px, size_px), Image.LANCZOS)


def main() -> None:
    default_out = Path(__file__).resolve().parent / "Otto.app/Contents/Resources/Otto.icns"
    ap = argparse.ArgumentParser(description="Render the Otto app icon → Otto.icns")
    ap.add_argument("--out", type=Path, default=default_out, help="destination .icns path")
    ap.add_argument("--preview", type=Path, default=None, help="also write a PNG preview here")
    args = ap.parse_args()

    master = render(BASE)
    if args.preview:
        args.preview.parent.mkdir(parents=True, exist_ok=True)
        master.save(args.preview)

    # pack .icns with PNG-encoded entries (modern macOS reads these)
    types = [
        (b"icp4", 16), (b"icp5", 32), (b"icp6", 64),
        (b"ic07", 128), (b"ic08", 256), (b"ic09", 512), (b"ic10", 1024),
        (b"ic11", 32), (b"ic12", 64), (b"ic13", 256), (b"ic14", 512),
    ]
    chunks = b""
    for ostype, sz in types:
        im = master if sz == BASE else master.resize((sz, sz), Image.LANCZOS)
        buf = BytesIO()
        im.save(buf, format="PNG")
        data = buf.getvalue()
        chunks += ostype + struct.pack(">I", len(data) + 8) + data
    icns = b"icns" + struct.pack(">I", len(chunks) + 8) + chunks
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(icns)
    print(f"wrote {args.out} ({len(icns)} bytes)")


if __name__ == "__main__":
    main()
