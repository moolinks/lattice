from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "assets" / "brand"
PUBLIC = ROOT / "frontend" / "public"
BRAND.mkdir(parents=True, exist_ok=True)
PUBLIC.mkdir(parents=True, exist_ok=True)

icon = Image.open(BRAND / "icon-512.png").convert("RGBA")

# Application icon sizes
for size, name in ((512, "icon-512.png"), (192, "icon-192.png"), (180, "apple-touch-icon.png")):
    icon.resize((size, size), Image.Resampling.LANCZOS).save(PUBLIC / name)

# Multi-resolution Windows / browser favicon
icon.save(
    PUBLIC / "favicon.ico",
    sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64)],
)

# Open Graph / social preview
W, H = 1280, 640
canvas = Image.new("RGB", (W, H), "#171b17")
draw = ImageDraw.Draw(canvas, "RGBA")

# Background wash + grid
for y in range(H):
    t = y / H
    draw.line((0, y, W, y), fill=(23 + int(7 * t), 27 + int(6 * t), 23 + int(5 * t)))
for x in range(0, W, 40):
    draw.line((x, 0, x, H), fill=(239, 231, 210, 8))
for y in range(0, H, 40):
    draw.line((0, y, W, y), fill=(239, 231, 210, 8))
draw.ellipse((780, -260, 1500, 420), fill=(200, 75, 49, 28))
draw.rectangle((0, 0, W - 1, H - 1), outline=(239, 231, 210, 30), width=2)

# Icon
icon_large = icon.resize((300, 300), Image.Resampling.LANCZOS)
canvas.paste(icon_large, (92, 170), icon_large)

# Typography
georgia = "C:/Windows/Fonts/georgia.ttf"
segoe = "C:/Windows/Fonts/segoeui.ttf"
consola = "C:/Windows/Fonts/consola.ttf"
font_title = ImageFont.truetype(georgia, 92)
font_body = ImageFont.truetype(segoe, 21)
font_sub = ImageFont.truetype(segoe, 27)
font_small = ImageFont.truetype(consola, 17)
font_label = ImageFont.truetype(consola, 13)

ink = (243, 236, 220)
muted = (166, 164, 148)
accent = (221, 108, 78)

draw.text((438, 210), "LATTICE", font=font_title, fill=ink)
draw.line((442, 322, 556, 322), fill=accent, width=4)
draw.text((438, 348), "A local-first research workbench.", font=font_sub, fill=ink)
draw.text((438, 388), "Read papers. Keep notes. Run experiments. Write.", font=font_body, fill=muted)

draw.text((92, 76), "LOCAL / SINGLE PROCESS / NO CLOUD", font=font_label, fill=muted)
draw.text(
    (92, 540),
    "SQLite FTS5  ·  Markdown source of truth  ·  BM25  ·  pandoc → LaTeX",
    font=font_small,
    fill=muted,
)
draw.text((92, 570), "github.com/moolinks/lattice", font=font_small, fill=(190, 142, 115))

canvas.save(BRAND / "og-image.png", optimize=True)
canvas.resize((640, 320), Image.Resampling.LANCZOS).save(BRAND / "og-image-small.png")
print("brand assets written")
