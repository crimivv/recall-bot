from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

OUT = Path(__file__).with_name("assets") / "banner.png"

W, H, S = 800, 220, 4
GLASS = (16, 18, 23)
RED = (234, 27, 15)
SQUARE_ANGLE = -15
HOLE_RATIO = 0.38
CAP = 132 * S
STROKE = 34 * S
GAP = 18 * S
RADIUS = 96 * S
INSET = 8

IMG_SIZE = (W * S, H * S)
PANEL = [INSET, INSET, W * S - INSET, H * S - INSET]


def new_layer() -> Image.Image:
    return Image.new("RGBA", IMG_SIZE, (0, 0, 0, 0))


def rotated_square(draw: ImageDraw.ImageDraw, cx: float, cy: float,
                   side: float, angle: int, fill) -> None:
    r = side / 2
    a = math.radians(angle)
    cos, sin = math.cos(a), math.sin(a)
    corners = [(cx + dx * cos - dy * sin, cy + dx * sin + dy * cos)
               for dx, dy in ((-r, -r), (r, -r), (r, r), (-r, r))]
    draw.polygon(corners, fill=fill)


def letter_L(draw: ImageDraw.ImageDraw, x: float, y: float) -> float:
    width = CAP * 0.78
    draw.rectangle([x, y, x + STROKE, y + CAP], fill=RED)
    draw.rectangle([x, y + CAP - STROKE, x + width, y + CAP], fill=RED)
    return width


def letter_I(draw: ImageDraw.ImageDraw, x: float, y: float) -> float:
    draw.rectangle([x, y, x + STROKE, y + CAP], fill=RED)
    return STROKE


def letter_V(draw: ImageDraw.ImageDraw, x: float, y: float) -> float:
    width = CAP * 0.92
    apex_half = STROKE * 0.80
    top_in = STROKE * 1.05
    center = x + width / 2
    inner_depth = STROKE * 1.55
    draw.polygon(
        [
            (x, y),
            (x + top_in, y),
            (center, y + CAP - inner_depth),
            (x + width - top_in, y),
            (x + width, y),
            (center + apex_half, y + CAP),
            (center - apex_half, y + CAP),
        ],
        fill=RED,
    )
    return width


def letter_E(draw: ImageDraw.ImageDraw, x: float, y: float) -> float:
    width = CAP * 0.70
    draw.rectangle([x, y, x + STROKE, y + CAP], fill=RED)
    draw.rectangle([x, y, x + width, y + STROKE], fill=RED)
    mid = y + (CAP - STROKE) // 2
    draw.rectangle([x, mid, x + width * 0.84, mid + STROKE], fill=RED)
    draw.rectangle([x, y + CAP - STROKE, x + width, y + CAP], fill=RED)
    return width


side = 0.74 * H * S
cy = H * S / 2
angle_rad = math.radians(SQUARE_ANGLE)
sq_half = side / 2 * (abs(math.cos(angle_rad)) + abs(math.sin(angle_rad)))
square_gap = 0.025 * W * S

start_y = (H * S - CAP) / 2
widths = [letter_L, letter_I, letter_V, letter_E]
total = CAP * 0.78 + STROKE + CAP * 0.92 + CAP * 0.70 + GAP * 3

group = sq_half * 2 + square_gap + total
left = 0.025 * W * S
cx = left + sq_half
cursor = cx + sq_half + square_gap

panel_mask = Image.new("L", IMG_SIZE, 0)
ImageDraw.Draw(panel_mask).rounded_rectangle(PANEL, radius=RADIUS, fill=255)

glow = new_layer()
d = ImageDraw.Draw(glow)
d.ellipse([cx - 1200 * S, cy - 130 * S, cx + 900 * S, cy + 130 * S],
          fill=(150, 24, 12, 120))
d.ellipse([cursor, cy - 110 * S, cursor + total * 0.7, cy + 110 * S],
          fill=(214, 36, 26, 90))
d.ellipse([W * S - 900 * S, cy - 140 * S, W * S - 40 * S, cy + 140 * S],
          fill=(52, 66, 132, 55))
glow = glow.filter(ImageFilter.GaussianBlur(110))
d = ImageDraw.Draw(glow)
rotated_square(d, cx, cy, side * HOLE_RATIO, SQUARE_ANGLE, (0, 0, 0, 0))
img = Image.alpha_composite(new_layer(), glow)

glass = new_layer()
d = ImageDraw.Draw(glass)
rows = PANEL[3] - PANEL[1]
for i, y in enumerate(range(PANEL[1], PANEL[3] + 1)):
    shade = int(118 + (168 - 118) * (i / max(1, rows)))
    d.line([(PANEL[0], y), (PANEL[2], y)], fill=(*GLASS, shade))
glass.putalpha(ImageChops.multiply(glass.getchannel("A"), panel_mask))
d = ImageDraw.Draw(glass)
rotated_square(d, cx, cy, side * HOLE_RATIO, SQUARE_ANGLE, (0, 0, 0, 0))
img = Image.alpha_composite(img, glass)

streaks = new_layer()
d = ImageDraw.Draw(streaks)
d.polygon([(-160 * S, H * S + 60 * S), (260 * S, -60 * S),
           (380 * S, -60 * S), (-40 * S, H * S + 60 * S)],
          fill=(255, 255, 255, 26))
streaks = streaks.filter(ImageFilter.GaussianBlur(38))
d = ImageDraw.Draw(streaks)
rotated_square(d, cx, cy, side * HOLE_RATIO, SQUARE_ANGLE, (0, 0, 0, 0))
streaks.putalpha(ImageChops.multiply(streaks.getchannel("A"), panel_mask))
img = Image.alpha_composite(img, streaks)

edges = new_layer()
d = ImageDraw.Draw(edges)
d.rounded_rectangle(PANEL, radius=RADIUS, outline=(255, 255, 255, 55), width=2)
d.line([(PANEL[0] + RADIUS // 2, PANEL[1] + 2 * S),
        (PANEL[2] - RADIUS // 2, PANEL[1] + 2 * S)],
       fill=(255, 255, 255, 110), width=2 * S)
d.line([(PANEL[0] + RADIUS // 2, PANEL[3] - 2 * S),
        (PANEL[2] - RADIUS // 2, PANEL[3] - 2 * S)],
       fill=(0, 0, 0, 70), width=2 * S)
img = Image.alpha_composite(img, edges)

art = new_layer()
d = ImageDraw.Draw(art)
rotated_square(d, cx, cy, side, SQUARE_ANGLE, RED)
rotated_square(d, cx, cy, side * HOLE_RATIO, SQUARE_ANGLE, (0, 0, 0, 0))
cursor_x = cursor
for drawing_fn in widths:
    used = drawing_fn(d, cursor_x, start_y)
    cursor_x += used + GAP
art.putalpha(art.getchannel("A").point(lambda v: v * 200 // 255))
img = Image.alpha_composite(img, art)

sheen = new_layer()
d = ImageDraw.Draw(sheen)
sheen_height = int(CAP * 0.55)
for i, y in enumerate(range(int(start_y), int(start_y) + sheen_height)):
    brightness = int(85 * (1 - i / max(1, sheen_height)))
    d.line([(0, y), (W * S, y)], fill=(255, 255, 255, brightness))
sheen.putalpha(ImageChops.multiply(sheen.getchannel("A"), art.getchannel("A")))
img = Image.alpha_composite(img, sheen)

img.putalpha(ImageChops.multiply(img.getchannel("A"), panel_mask))
img = img.resize((W, H), Image.LANCZOS)
OUT.parent.mkdir(parents=True, exist_ok=True)
img.save(OUT)
