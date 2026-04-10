from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from ..models import EndCardBanner


def _hex_to_rgb(hex_value: str) -> tuple[int, int, int]:
    value = hex_value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _pick_background_color(icon_path: Path | None) -> str:
    if icon_path is None or not icon_path.exists():
        return "#111827"
    try:
        with Image.open(icon_path) as icon_image:
            rgba = icon_image.convert("RGBA").resize((32, 32))
            pixels = [pixel for pixel in rgba.getdata() if pixel[3] > 0]
            if not pixels:
                return "#111827"
            avg = tuple(sum(pixel[channel] for pixel in pixels) // len(pixels) for channel in range(3))
            muted = tuple(max(16, min(200, int(channel * 0.55))) for channel in avg)
            return _rgb_to_hex(muted)
    except Exception:
        return "#111827"


def _text_color_for(bg_hex: str) -> str:
    r, g, b = _hex_to_rgb(bg_hex)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#0b0b0b" if luminance > 0.7 else "#ffffff"


def build_end_card_banner(app_name: str, icon_path: Path | None, output_path: Path) -> EndCardBanner:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    background_color = _pick_background_color(icon_path)
    text_color = _text_color_for(background_color)

    width, height = 1080, 1920
    canvas = Image.new("RGB", (width, height), _hex_to_rgb(background_color))
    draw = ImageDraw.Draw(canvas)

    icon_box = 320
    icon_y = 560
    if icon_path is not None and icon_path.exists():
        try:
            with Image.open(icon_path) as raw_icon:
                icon = raw_icon.convert("RGBA")
                icon = ImageOps.contain(icon, (icon_box, icon_box))
                icon_x = (width - icon.width) // 2
                canvas.paste(icon, (icon_x, icon_y), icon)
        except Exception:
            pass

    try:
        font_title = ImageFont.truetype("DejaVuSans-Bold.ttf", 88)
    except Exception:
        font_title = ImageFont.load_default()
    text = app_name.strip() or "App"
    bbox = draw.textbbox((0, 0), text, font=font_title)
    text_x = (width - (bbox[2] - bbox[0])) // 2
    text_y = icon_y + icon_box + 120
    draw.text((text_x, text_y), text, fill=_hex_to_rgb(text_color), font=font_title)

    canvas.save(output_path, format="PNG")
    return EndCardBanner(
        app_name=text,
        background_color=background_color,
        text_color=text_color,
        icon_source=str(icon_path) if icon_path and icon_path.exists() else "",
        output_image=str(output_path),
        layout_notes=[
            "Solid-color background generated from the uploaded app icon when available.",
            "App icon centered in the upper-middle area.",
            "App name centered below the icon.",
        ],
    )
