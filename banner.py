from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).with_name("assets") / "banner.png"

W, H, S = 800, 220, 4
TRANSPARENT = (0, 0, 0, 0)
RED = (0xEA, 0x1B, 0x0F, 255)
SQUARE_ANGLE = -15
HOLE_RATIO = 0.38
CAP = 132 * S
STROKE = 34 * S
GAP = 18 * S

img = Image.new("RGBA", (W * S, H * S), TRANSPARENT)
d = ImageDraw.Draw(img)


def rotated_square(cx: float, cy: float, side: float, angle: int, fill) -> None:
    r = side / 2
    a = math.radians(angle)
    cos, sin = math.cos(a), math.sin(a)
    corners = []
    for dx, dy in ((-r, -r), (r, -r), (r, r), (-r, r)):
        corners.append((cx + dx * cos - dy * sin, cy + dx * sin + dy * cos))
    d.polygon(corners, fill=fill)


def letter_L(x: float, y: float) -> float:
    width = CAP * 0.78
    d.rectangle([x, y, x + STROKE, y + CAP], fill=RED)
    d.rectangle([x, y + CAP - STROKE, x + width, y + CAP], fill=RED)
    return width


def letter_I(x: float, y: float) -> float:
    d.rectangle([x, y, x + STROKE, y + CAP], fill=RED)
    return STROKE


def letter_V(x: float, y: float) -> float:
    width = CAP * 0.92
    apex_half = STROKE * 0.80
    top_in = STROKE * 1.05
    cx = x + width / 2
    inner_depth = STROKE * 1.55
    d.polygon(
        [
            (x, y),
            (x + top_in, y),
            (cx, y + CAP - inner_depth),
            (x + width - top_in, y),
            (x + width, y),
            (cx + apex_half, y + CAP),
            (cx - apex_half, y + CAP),
        ],
        fill=RED,
    )
    return width


def letter_E(x: float, y: float) -> float:
    width = CAP * 0.70
    d.rectangle([x, y, x + STROKE, y + CAP], fill=RED)
    d.rectangle([x, y, x + width, y + STROKE], fill=RED)
    mid = y + (CAP - STROKE) // 2
    d.rectangle([x, mid, x + width * 0.84, mid + STROKE], fill=RED)
    d.rectangle([x, y + CAP - STROKE, x + width, y + CAP], fill=RED)
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
left = (W * S - group) / 2
cx = left + sq_half
cursor = cx + sq_half + square_gap

rotated_square(cx, cy, side, SQUARE_ANGLE, RED)
rotated_square(cx, cy, side * HOLE_RATIO, SQUARE_ANGLE, TRANSPARENT)

for drawing_fn in widths:
    used = drawing_fn(cursor, start_y)
    cursor += used + GAP

img = img.resize((W, H), Image.LANCZOS)
OUT.parent.mkdir(parents=True, exist_ok=True)
img.save(OUT)
