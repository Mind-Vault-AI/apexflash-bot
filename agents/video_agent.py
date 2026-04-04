from core.config import BOT_USERNAME
"""
ApexFlash AI Visual Producer (v3.21.0)
────────────────────────────────────────────────────────
Objective: Transform raw signals into viral infographics.
Engine: Pillow (PIL) + Gemini 2.0
"""

import os
import logging
from PIL import Image, ImageDraw, ImageFont
import google.generativeai as genai

logger = logging.getLogger("VisualAlpha")

# ── Asset Paths ────────────────────────────────────────────────────────────────

TEMPLATE_DIR = "marketing/templates"
os.makedirs(TEMPLATE_DIR, exist_ok=True)

# ── Infographic Engine ─────────────────────────────────────────────────────────

SIGNAL_TYPES = {
    "whale": {
        "title": "WHALE ALERT",
        "template": "whale_vortex_template.png",
        "colors": {"main": (255, 215, 0), "sub": (255, 255, 255)}
    },
    "win": {
        "title": "GODMODE WIN",
        "template": "success_template.png",
        "colors": {"main": (0, 255, 127), "sub": (255, 255, 255)}
    },
    "alpha": {
        "title": "ALPHA CLAN DETECTED",
        "template": "alpha_clan_template.png",
        "colors": {"main": (255, 69, 0), "sub": (255, 255, 255)}
    }
}

def generate_viral_infographic(
    signal_type: str,
    data: dict,
    lang: str = "en"
) -> str:
    """
    High-level entry point to generate a signal infographic.
    Returns path to JPEG.
    """
    from core.i18n import get_text
    config = SIGNAL_TYPES.get(signal_type, SIGNAL_TYPES["whale"])
    
    # 1. Base Image (Search for template in marketing/templates)
    bg_path = os.path.join(TEMPLATE_DIR, config["template"])
    if not os.path.exists(bg_path):
        # Fallback to a generic background if template is missing
        bg_path = os.path.join(TEMPLATE_DIR, "fallback.png")
        if not os.path.exists(bg_path):
             return "⚠️ Background asset missing."

    # 2. Content Preparation (Localized)
    title = f"[{config['title']}]"
    if signal_type == "whale":
        text = f"{title}\n{data.get('token', 'Unknown')} {data.get('amount', 'Large')} MOVED\nTarget: {data.get('target', 'Exchange')}\nFOLLOW THE SMART MONEY"
    elif signal_type == "win":
        text = f"{title}\n+{data.get('pnl', '20')}% PROFIT\nTOKEN: ${data.get('token')}\nPRECISION SCALPING"
    else:
        text = f"{title}\n{data.get('count', '3')} WHALES BUYING\nTOKEN: ${data.get('token')}\nINSTITUTIONAL ALPHA"

    output_name = f"viral_{signal_type}_{data.get('token', 'unkn')}.jpg"
    output_path = os.path.join(TEMPLATE_DIR, output_name)
    
    return create_infographic(bg_path, text, output_path)

def create_infographic(
    background_path: str,
    text_content: str,
    output_path: str,
    brand_logo_path: str = None
) -> str:
# ... (rest of the PIL logic)
    """
    Overlay high-impact text and branding on a base crypto image.
    """
    try:
        img = Image.open(background_path).convert("RGBA")
        width, height = img.size
        
        # Overlay for readability (dark tint)
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 100))
        img = Image.alpha_composite(img, overlay)
        
        draw = ImageDraw.Draw(img)
        
        # Font settings (Attempt to find a bold font)
        try:
            # Common paths on windows/linux
            font_path = "arial.ttf" if os.name == 'nt' else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            font = ImageFont.truetype(font_path, size=int(width / 15))
        except:
            font = ImageFont.load_default()

        # Wrap text logic (simple)
        lines = text_content.split("\n")
        y_text = height / 3
        for line in lines:
            # Draw shadow
            draw.text((width/10 + 5, y_text + 5), line, font=font, fill=(0,0,0,255))
            # Draw main text (vibrant gold/white)
            draw.text((width/10, y_text), line, font=font, fill=(255, 215, 0, 255))
            y_text += height / 10

        # Branding (Bottom Right)
        footer_font = ImageFont.load_default()
        draw.text((width - 300, height - 100), f"@{BOT_USERNAME} | Godmode", font=footer_font, fill=(255, 255, 255, 180))

        img = img.convert("RGB")
        img.save(output_path, "JPEG", quality=90)
        return output_path

    except Exception as e:
        logger.error(f"Infographic generation failed: {e}")
        return ""

async def get_visual_composition_prompt(signal_data: dict) -> str:
    """Use Gemini to generate a stylized image prompt for the background."""
    # This prompt is intended for the developer (me) to run generate_image.
    # In an autonomous loop, this could be sent to an image API.
    return (
        f"A cinematic, high-speed crypto-trading visualization representing "
        f"{signal_data.get('type', 'whale move')}. Cyberpunk 2077 aesthetic, "
        f"vibrant gold and purple neon, high-resolution 3D render of Solana coins "
        f"flowing in a digital vortex. Professional financial terminal atmosphere."
    )
