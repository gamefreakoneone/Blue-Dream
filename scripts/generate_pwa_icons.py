"""Generate installable PWA icons from the checked-in Memoria mascot."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "UI" / "public" / "slime_logo.png"
OUTPUT = ROOT / "UI" / "public" / "icons"


def mascot_layer() -> Image.Image:
    source = Image.open(SOURCE).convert("RGBA")
    # The source is square with the wordmark above the mascot. Keep the face only.
    mascot = source.crop((78, 155, 562, 614))
    pixels = mascot.load()
    for y in range(mascot.height):
        for x in range(mascot.width):
            red, green, blue, alpha = pixels[x, y]
            whiteness = min(red, green, blue)
            if whiteness > 245:
                alpha = max(0, 255 - (whiteness - 245) * 26)
            pixels[x, y] = (red, green, blue, alpha)
    return mascot


def render(size: int, *, maskable: bool = False) -> Image.Image:
    background = "#d9f4e6" if maskable else "#f6faf8"
    canvas = Image.new("RGBA", (size, size), background)
    safe_size = int(size * (0.68 if maskable else 0.82))
    mascot = mascot_layer()
    mascot.thumbnail((safe_size, safe_size), Image.Resampling.LANCZOS)
    x = (size - mascot.width) // 2
    y = (size - mascot.height) // 2
    canvas.alpha_composite(mascot, (x, y))
    return canvas.convert("RGB")


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    render(192).save(OUTPUT / "icon-192.png", optimize=True)
    render(512).save(OUTPUT / "icon-512.png", optimize=True)
    render(512, maskable=True).save(OUTPUT / "icon-maskable-512.png", optimize=True)


if __name__ == "__main__":
    main()
