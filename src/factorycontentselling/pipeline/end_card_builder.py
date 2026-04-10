from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from ..models import EndCardBanner
from ..services.openai_adapter import OpenAIAdapter


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


def _blend_color(color_a: tuple[int, int, int], color_b: tuple[int, int, int], ratio: float) -> tuple[int, int, int]:
    return tuple(int(a + (b - a) * ratio) for a, b in zip(color_a, color_b))


def _build_gradient_background(size: tuple[int, int], base_hex: str) -> Image.Image:
    width, height = size
    base = _hex_to_rgb(base_hex)
    top_color = _blend_color(base, (255, 255, 255), 0.18)
    bottom_color = _blend_color(base, (5, 10, 20), 0.22)
    canvas = Image.new("RGB", size, base)
    draw = ImageDraw.Draw(canvas)

    for y in range(height):
        ratio = y / max(height - 1, 1)
        row_color = _blend_color(top_color, bottom_color, ratio)
        draw.line((0, y, width, y), fill=row_color)

    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((-120, -80, width * 0.72, height * 0.55), fill=(255, 255, 255, 42))
    glow_draw.ellipse((width * 0.3, height * 0.48, width * 1.08, height * 1.08), fill=(255, 255, 255, 18))
    return Image.alpha_composite(canvas.convert("RGBA"), glow).convert("RGB")


def _generate_ai_banner_background(app_name: str, app_description: str, output_path: Path) -> Path | None:
    adapter = OpenAIAdapter()
    prompt = (
        f"Create a premium vertical mobile app install banner background for an app called {app_name}. "
        f"App description: {app_description}. "
        "Generate only a clean abstract background that makes the app feel desirable and worth downloading immediately. "
        "Use a polished App Store style visual language: rich gradients, soft glow, subtle depth, elegant lighting, minimal abstract shapes. "
        "Leave clear empty space in the center for a real app icon and app name overlay. "
        "Do not include any objects, people, devices, screenshots, icons, logos, symbols, coins, stars, text, letters, words, or interface elements."
    )
    return adapter.generate_image(prompt, output_path)


def _load_bold_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "DejaVuSans-Bold.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()


def build_end_card_banner(app_name: str, app_description: str, icon_path: Path | None, output_path: Path) -> EndCardBanner | None:
    if icon_path is None or not icon_path.exists():
        return None

    output_path.parent.mkdir(parents=True, exist_ok=True)
    background_color = _pick_background_color(icon_path)
    text_color = _text_color_for(background_color)

    width, height = 1080, 1920
    ai_background_path = _generate_ai_banner_background(
        app_name,
        app_description or "A polished mobile app experience with a strong payoff.",
        output_path.with_name(f"{output_path.stem}_bg.png"),
    )
    if ai_background_path is not None and ai_background_path.exists():
        with Image.open(ai_background_path) as raw_background:
            canvas = raw_background.convert("RGB").resize((width, height))
    else:
        canvas = _build_gradient_background((width, height), background_color)
    draw = ImageDraw.Draw(canvas)

    icon_box = 380
    icon_y = 430
    try:
        with Image.open(icon_path) as raw_icon:
            icon = raw_icon.convert("RGBA")
            icon = ImageOps.contain(icon, (icon_box, icon_box))
            icon_x = (width - icon.width) // 2
            canvas.paste(icon, (icon_x, icon_y), icon)
    except Exception:
        return None

    font_title = _load_bold_font(140)
    text = app_name.strip() or "App"
    bbox = draw.textbbox((0, 0), text, font=font_title)
    text_width = bbox[2] - bbox[0]
    text_x = (width - text_width) // 2
    text_y = icon_y + icon_box + 90
    shadow_color = (0, 0, 0, 90)
    draw.text((text_x, text_y + 6), text, fill=shadow_color, font=font_title)
    draw.text((text_x, text_y), text, fill=_hex_to_rgb(text_color), font=font_title)

    canvas.save(output_path, format="PNG")
    return EndCardBanner(
        app_name=text,
        background_color=background_color,
        text_color=text_color,
        icon_source=str(icon_path) if icon_path and icon_path.exists() else "",
        output_image=str(output_path),
        layout_notes=[
            "Banner uses AI-generated install-oriented background when available.",
            "App icon centered in the upper-middle area.",
            "App name centered below the icon.",
        ],
    )
