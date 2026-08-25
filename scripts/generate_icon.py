"""Generate PNG/ICO application assets from the fixed three-color geometry."""

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"


def render(size: int) -> Image.Image:
    scale = size / 256
    image = Image.new("RGBA", (size, size), "#1B1E24")
    draw = ImageDraw.Draw(image)
    def box(x1: int, y1: int, x2: int, y2: int, color: str) -> None:
        draw.rectangle((round(x1 * scale), round(y1 * scale), round(x2 * scale), round(y2 * scale)), fill=color)

    box(46, 48, 70, 208, "#F1F4F6")
    box(46, 48, 91, 72, "#F1F4F6")
    box(46, 184, 91, 208, "#F1F4F6")
    box(186, 48, 210, 208, "#F1F4F6")
    box(165, 48, 210, 72, "#F1F4F6")
    box(165, 184, 210, 208, "#F1F4F6")
    for y, color in ((96, "#F1F4F6"), (136, "#F1F4F6"), (176, "#FF982E")):
        box(109, y, 147, y + 24, color)
    return image


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    render(256).save(ASSETS / "icon.png", optimize=True)
    render(1024).save(ASSETS / "icon-1024.png", optimize=True)
    render(256).save(ASSETS / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    for size in (16, 32):
        render(size).save(ASSETS / f"icon-{size}.png", optimize=True)


if __name__ == "__main__":
    main()
