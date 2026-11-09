from PIL import Image, ImageDraw
from pathlib import Path
import random

out = Path(__file__).resolve().parent / "textures"
out.mkdir(exist_ok=True)


# --------------------------------------------------
# GROUND TEXTURE
# --------------------------------------------------

img = Image.new("RGB", (64, 64), (86, 150, 86))
d = ImageDraw.Draw(img)

for _ in range(800):
    x = random.randint(0, 63)
    y = random.randint(0, 63)

    r = random.randint(40, 90)
    g = random.randint(110, 180)
    b = random.randint(40, 90)

    d.point((x, y), fill=(r, g, b))

for x in range(0, 64, 8):
    d.line((x, 0, x, 63), fill=(70, 120, 70), width=1)

for y in range(0, 64, 8):
    d.line((0, y, 63, y), fill=(70, 120, 70), width=1)

img.save(out / "ground.png")


# --------------------------------------------------
# BRICK TEXTURE
# --------------------------------------------------

img = Image.new("RGB", (64, 64), (150, 60, 50))
d = ImageDraw.Draw(img)

for y in range(0, 64, 16):
    d.rectangle((0, y, 63, y + 2), fill=(85, 85, 85))

for row, y in enumerate(range(0, 64, 16)):
    offset = 0 if row % 2 == 0 else 8

    for x in range(offset, 64, 16):
        d.rectangle((x, y, x + 2, y + 16), fill=(85, 85, 85))

img.save(out / "brick.png")


# --------------------------------------------------
# METAL TEXTURE
# --------------------------------------------------

img = Image.new("RGB", (64, 64), (130, 135, 145))
d = ImageDraw.Draw(img)

for _ in range(500):
    x = random.randint(0, 63)
    y = random.randint(0, 63)

    v = random.randint(110, 160)

    d.point((x, y), fill=(v, v, v + 5))

for x, y in [(8, 8), (56, 8), (8, 56), (56, 56)]:
    d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(80, 85, 95))

img.save(out / "metal.png")


print("Created textures in:", out)