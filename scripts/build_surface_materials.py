"""Generate the local, seamless grayscale finish swatches used with user colors."""
import math
import random
from pathlib import Path
from PIL import Image

target = Path(__file__).resolve().parents[1] / 'webapp/static/materials'
target.mkdir(parents=True, exist_ok=True)
size = 256
for name in ('parquet', 'tile', 'stone', 'wallpaper'):
    rng = random.Random(name)
    image = Image.new('RGB', (size, size))
    pixels = image.load()
    for y in range(size):
        for x in range(size):
            if name == 'parquet':
                row = y // 64
                seam = y % 64 < 2 or (x + row % 2 * 128) % 256 < 2
                value = 165 if seam else 228 + 7 * math.sin(x * .24 + 4 * math.sin(y * .049)) + 4 * math.sin(y * .8)
            elif name == 'tile':
                value = 184 if x < 3 or y < 3 else 246 + rng.uniform(-3, 3)
            elif name == 'stone':
                vein = math.sin(x * math.tau / 128 + 2 * math.sin(y * math.tau / 256) + .35 * math.sin(y * math.tau / 64))
                value = 240 - 40 * max(0, (abs(vein) - .88) / .12) + rng.uniform(-3, 3)
            else:
                line = (x + y) % 64 < 2 or (x - y) % 64 < 2
                value = (215 if line else 245) + rng.uniform(-2, 2)
            shade = max(0, min(255, round(value)))
            pixels[x, y] = (shade, shade, shade)
    image.save(target / (name + '.png'), optimize=True)
