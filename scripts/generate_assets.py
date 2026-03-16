from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
ICON_DIR = ROOT / "assets" / "icons"
SOURCE_DIR = ROOT / "assets" / "sourcePNG"


def ensure_dirs() -> None:
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)


def create_icon() -> None:
    icon_png = ICON_DIR / "openclaw-skins.png"
    icon_ico = ICON_DIR / "openclaw-skins.ico"
    if icon_png.exists() and icon_ico.exists():
        return

    image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((28, 48, 228, 220), fill=(209, 101, 45, 255), outline=(71, 34, 16, 255), width=8)
    draw.ellipse((58, 28, 108, 78), fill=(244, 237, 224, 255), outline=(71, 34, 16, 255), width=6)
    draw.ellipse((148, 28, 198, 78), fill=(244, 237, 224, 255), outline=(71, 34, 16, 255), width=6)
    draw.ellipse((72, 40, 90, 58), fill=(22, 20, 18, 255))
    draw.ellipse((162, 40, 180, 58), fill=(22, 20, 18, 255))
    draw.arc((78, 104, 178, 180), start=10, end=170, fill=(250, 248, 242, 255), width=7)
    draw.rounded_rectangle((18, 98, 78, 146), radius=22, outline=(71, 34, 16, 255), width=8)
    draw.rounded_rectangle((178, 98, 238, 146), radius=22, outline=(71, 34, 16, 255), width=8)
    image.save(icon_png)
    image.save(icon_ico, sizes=[(256, 256), (128, 128), (64, 64), (32, 32)])


def create_placeholder_frame(path: Path, accent: tuple[int, int, int, int], mouth_open: bool) -> None:
    if path.exists():
        return

    width, height = 2816, 1536
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    border = (87, 42, 19, 255)
    glow = (255, 241, 219, 235)
    panel = (15, 20, 27, 0)

    draw.rounded_rectangle((120, 42, width - 120, height - 54), radius=260, outline=accent, width=36)
    draw.rounded_rectangle((160, 82, width - 160, height - 94), radius=230, outline=border, width=12)
    draw.rounded_rectangle((460, 240, width - 460, height - 300), radius=72, fill=panel, outline=glow, width=6)

    draw.ellipse((980, 1128, 1228, 1404), fill=(233, 215, 196, 255), outline=border, width=8)
    draw.ellipse((1544, 1128, 1792, 1404), fill=(233, 215, 196, 255), outline=border, width=8)
    draw.ellipse((1076, 1190, 1170, 1300), fill=(16, 20, 22, 255))
    draw.ellipse((1640, 1190, 1734, 1300), fill=(16, 20, 22, 255))
    draw.rounded_rectangle((1040, 1252, 1748, 1472), radius=88, fill=(205, 100, 46, 255), outline=border, width=12)

    if mouth_open:
        draw.pieslice((1164, 1308, 1632, 1522), start=12, end=168, fill=(40, 18, 18, 255), outline=(250, 244, 236, 255), width=8)
    else:
        draw.arc((1164, 1334, 1632, 1518), start=12, end=168, fill=(250, 244, 236, 255), width=10)

    draw.rounded_rectangle((790, 126, 1160, 304), radius=68, fill=accent, outline=border, width=10)
    draw.rounded_rectangle((1656, 126, 2026, 304), radius=68, fill=accent, outline=border, width=10)

    image.save(path)


def main() -> int:
    ensure_dirs()
    create_icon()
    create_placeholder_frame(SOURCE_DIR / "openclaw-skin-closed.png", (186, 76, 35, 255), mouth_open=False)
    create_placeholder_frame(SOURCE_DIR / "openclaw-skin-open.png", (221, 108, 44, 255), mouth_open=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
