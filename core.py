"""Core logic for Quick Facts card generation — shared by the Streamlit app.
Ported from the original Flask prototype, adapted for in-memory use.
"""
import base64
import io
import json
import re

import requests
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont, ImageFilter

DEFAULT_API_BASE = "https://llm.talabat.io/proxy/v1"
DEFAULT_MODEL = "gemini-3.1-flash-image"
DEFAULT_STYLE = "premium-minimal"

FONT_DIR_CANDIDATES = [r"C:\Windows\Fonts", "/usr/share/fonts/truetype/dejavu"]


def load_font(name, size):
    fallback = {"arialbd.ttf": "DejaVuSans-Bold.ttf", "arial.ttf": "DejaVuSans.ttf"}
    for d in FONT_DIR_CANDIDATES:
        import os
        for candidate in (name, fallback.get(name, name)):
            path = os.path.join(d, candidate)
            if os.path.isfile(path):
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    pass
    return ImageFont.load_default()


def fetch_image_bytes(url):
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "image/jpeg").split(";")[0]


def _extract_image_b64(obj):
    if obj is None:
        return None
    if isinstance(obj, str):
        marker = "base64,"
        if obj.startswith("data:image") and marker in obj:
            return obj.split(marker, 1)[1]
        return None
    if isinstance(obj, dict):
        for key in ("b64_json", "data"):
            if isinstance(obj.get(key), str) and len(obj[key]) > 100:
                return obj[key]
        if "url" in obj:
            found = _extract_image_b64(obj["url"])
            if found:
                return found
        for v in obj.values():
            found = _extract_image_b64(v)
            if found:
                return found
    if isinstance(obj, list):
        for item in obj:
            found = _extract_image_b64(item)
            if found:
                return found
    return None


FULL_CARD_STYLES = {
    "premium-minimal": (
        "Premium minimalist product infographic, square 1:1. Background is divided into soft "
        "geometric color-block rectangles in a muted warm neutral palette (cream, blush pink, "
        "soft tan, off-white), like a flat-lay color-field design, not a single flat color and "
        "not a photographic background. Elegant thin modern serif title at the top. A small "
        "rounded pill badge reading QUICK FACTS next to or under the title, in a muted sage or "
        "olive tone. Each fact is a short line of text with a matching understated fine-line "
        "icon to its left. Generous breathing room between every element. The product photo "
        "sits in the middle of the composition, clear of all text. Decorative elements such as "
        "leaves or garnishes must stay fully behind or beside the product photo and must never "
        "cross over, touch, or run through any text line — leave clean empty space around every "
        "sentence so all text stays perfectly legible on a single clean background strip."
    ),
}


def generate_full_card_ai(api_base, model, api_key, ref_bytes, mime_type, item_name,
                           display_title, facts, style_key=DEFAULT_STYLE):
    style_desc = FULL_CARD_STYLES.get(style_key, FULL_CARD_STYLES["premium-minimal"])
    facts_lines = "\n".join(f"- {label}: {value}" for label, value in facts)

    prompt = (
        f"Design a complete, finished product infographic card for the grocery item "
        f"\"{item_name}\", using the attached photo as the visual reference for the product "
        f"itself (keep the product's real appearance accurate).\n\n"
        f"The image must have ALL of this text baked in, clearly legible, correctly spelled, "
        f"well composed, with no overlapping elements:\n"
        f"- A large title reading exactly: \"{display_title.upper()}\"\n"
        f"- A small label/badge reading exactly: \"QUICK FACTS\"\n"
        f"- These {len(facts)} fact lines, each legible as its own short line or badge:\n"
        f"{facts_lines}\n\n"
        f"Style direction: {style_desc}\n\n"
        f"This is a finished, publish-ready marketing asset, not a plain photo. No "
        f"placeholder text, no lorem ipsum, no extra invented text beyond what is listed above."
    )

    content = [{"type": "text", "text": prompt}]
    if ref_bytes:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{base64.b64encode(ref_bytes).decode('utf-8')}"},
        })

    client = OpenAI(base_url=api_base.rstrip("/"), api_key=api_key)
    try:
        response = client.chat.completions.create(model=model, messages=[{"role": "user", "content": content}])
    except Exception as e:
        return None, f"Gateway call failed: {e}"

    try:
        raw = response.model_dump()
    except Exception:
        raw = json.loads(response.json()) if hasattr(response, "json") else {}

    b64_image = _extract_image_b64(raw)
    if b64_image:
        return base64.b64decode(b64_image), None
    return None, f"No image found in gateway response. Raw response: {json.dumps(raw)[:1500]}"


def generate_ai_image(api_base, model, api_key, ref_bytes, mime_type, item_name):
    has_reference = ref_bytes is not None
    if has_reference:
        prompt = (
            f"Using the attached product photo as the visual reference for this exact item "
            f"({item_name}), create a professional food-photography style image shot from "
            f"directly above: the whole product plus one piece cut open to show a clean "
            f"cross-section, arranged together on a styled ceramic plate, with one extra cut "
            f"piece placed just outside the plate for scale, soft natural lighting, a couple of "
            f"fresh leaves near the plate for styling, realistic texture and color, no text, "
            f"no logos, no watermarks, no added background color."
        )
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64.b64encode(ref_bytes).decode('utf-8')}"}},
        ]
    else:
        prompt = (
            f"Create a professional food-photography style image of {item_name}, shot from "
            f"directly above: the whole product plus one piece cut open to show a clean "
            f"cross-section, arranged together on a styled ceramic plate, soft natural "
            f"lighting, photorealistic, accurate color and texture, no text, no logos, "
            f"no watermarks, no added background color."
        )
        content = [{"type": "text", "text": prompt}]

    client = OpenAI(base_url=api_base.rstrip("/"), api_key=api_key)
    try:
        response = client.chat.completions.create(model=model, messages=[{"role": "user", "content": content}])
    except Exception as e:
        return None, f"Gateway call failed: {e}"

    try:
        raw = response.model_dump()
    except Exception:
        raw = json.loads(response.json()) if hasattr(response, "json") else {}

    b64_image = _extract_image_b64(raw)
    if b64_image:
        return base64.b64decode(b64_image), None
    return None, f"No image found in gateway response. Raw response: {json.dumps(raw)[:1500]}"


def auto_generate_facts(item_name, api_base, model, api_key):
    prompt = (
        f"Write short Quick Facts product copy for the grocery item \"{item_name}\" sold on an "
        f"online grocery app. Return ONLY a JSON object with exactly these four keys: "
        f"\"profile\", \"texture\", \"best_uses\", \"origin\". Each value must be one short "
        f"sentence (max 14 words), written in a simple, human, non-salesy tone, with no em "
        f"dashes and no unverifiable or exaggerated claims. \"profile\" covers taste, aroma, "
        f"sweetness or tartness. \"texture\" covers bite, skin or firmness. \"best_uses\" lists "
        f"2-3 everyday uses (snacking, salads, juicing, cooking, etc). \"origin\" gives a "
        f"plausible sourcing note or variety advantage versus other varieties. Do not include "
        f"any text outside the JSON object, and do not wrap it in markdown code fences."
    )
    client = OpenAI(base_url=api_base.rstrip("/"), api_key=api_key)
    try:
        response = client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}])
        text = (response.choices[0].message.content or "").strip()
    except Exception as e:
        return None, f"Gateway call failed: {e}"

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None, f"No JSON found in response: {text[:300]}"
    try:
        data = json.loads(match.group(0))
    except Exception as e:
        return None, f"Could not parse JSON from response: {e}"
    return data, None


PRODUCE_WORDS = sorted([
    "dragon fruit", "passion fruit", "strawberry", "pineapple", "watermelon", "pomegranate",
    "blueberry", "raspberry", "blackberry", "cauliflower", "cucumber", "eggplant", "capsicum",
    "mushroom", "zucchini", "beetroot", "broccoli", "cabbage", "spinach", "lettuce", "avocado",
    "apricot", "lychee", "banana", "orange", "grapes", "grape", "papaya", "guava", "lemon",
    "cherry", "cherries", "melon", "peach", "plum", "apple", "kiwi", "pear", "lime", "fig",
    "date", "dates", "tomato", "potato", "carrot", "onion", "pepper", "garlic", "ginger",
    "pumpkin", "radish", "celery", "corn", "beans", "okra", "peas", "pea",
], key=len, reverse=True)


def simplify_title(item_name):
    name_lower = item_name.lower()
    for word in PRODUCE_WORDS:
        if re.search(r"\b" + re.escape(word) + r"\b", name_lower):
            return word.title()
    first_chunk = item_name.split(",")[0]
    first_chunk = re.sub(r"\b\d+(\.\d+)?\s?(g|kg|ml|l|pcs?|pack)\b", "", first_chunk, flags=re.IGNORECASE)
    words = [w for w in first_chunk.split() if w.strip()]
    return " ".join(words[:2]).strip().title() or item_name


PALETTES = {
    "berry": {"band": (217, 100, 127), "card": (255, 248, 235), "accent": (150, 40, 70), "text": (74, 48, 52)},
    "citrus": {"band": (235, 150, 60), "card": (255, 248, 235), "accent": (165, 75, 15), "text": (74, 54, 36)},
    "green": {"band": (120, 160, 110), "card": (255, 248, 235), "accent": (50, 85, 48), "text": (40, 55, 38)},
    "warm": {"band": (184, 80, 66), "card": (255, 248, 235), "accent": (125, 40, 30), "text": (58, 42, 40)},
}


def pick_palette(item_name):
    name = item_name.lower()
    if any(k in name for k in ["strawberry", "cherry", "berry", "grape", "pomegranate"]):
        return PALETTES["berry"]
    if any(k in name for k in ["orange", "mango", "lemon", "banana", "pineapple", "papaya"]):
        return PALETTES["citrus"]
    if any(k in name for k in ["kiwi", "lettuce", "spinach", "broccoli", "cucumber", "zucchini"]):
        return PALETTES["green"]
    return PALETTES["warm"]


def leaf_image(w, h, color, angle):
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    points = [(0, h / 2), (w * 0.35, 0), (w, h / 2), (w * 0.35, h)]
    d.polygon(points, fill=color)
    d.line([(0, h / 2), (w, h / 2)], fill=(255, 255, 255, 40), width=2)
    return layer.rotate(angle, expand=True, resample=Image.BICUBIC)


def rounded_rect(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def rounded_photo(img, size, radius):
    img = img.convert("RGBA")
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side)).resize(size, Image.LANCZOS)
    mask = Image.new("L", size, 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def pill_row(draw, x, y, w, h, label, value, label_font, body_font, icon_font,
             pill_color, icon_bg, text_color, icon_glyph):
    rounded_rect(draw, (x, y, x + w, y + h), h / 2.2, pill_color)
    icon_d = min(h - 14, 52)
    icon_cx, icon_cy = x + 16 + icon_d / 2, y + h / 2
    draw.ellipse((icon_cx - icon_d / 2, icon_cy - icon_d / 2, icon_cx + icon_d / 2, icon_cy + icon_d / 2), fill=icon_bg)
    draw.text((icon_cx, icon_cy), icon_glyph, font=icon_font, fill=pill_color, anchor="mm")
    text_x = x + 16 + icon_d + 18
    text_w = x + w - 24 - text_x
    full_text = label + ": " + value
    lines = wrap_text(draw, full_text, body_font, text_w)[:3]
    line_h = body_font.size + 8
    total_text_h = line_h * len(lines)
    ty = y + (h - total_text_h) / 2
    for i, line in enumerate(lines):
        if i == 0 and ":" in line:
            lbl, _, rest = line.partition(":")
            draw.text((text_x, ty), lbl + ":", font=label_font, fill=text_color)
            lbl_w = draw.textlength(lbl + ": ", font=label_font)
            draw.text((text_x + lbl_w, ty), rest.strip(), font=body_font, fill=text_color)
        else:
            draw.text((text_x, ty), line, font=body_font, fill=text_color)
        ty += line_h


def vertical_ghost_strip(draw, x0, y0, x1, y1, fill_color, text, text_color):
    rounded_rect(draw, (x0, y0, x1, y1), 0, fill_color)
    font = load_font("arialbd.ttf", 150)
    tmp = Image.new("RGBA", (1, 1))
    tdraw = ImageDraw.Draw(tmp)
    tw = tdraw.textlength(text, font=font)
    th = font.size + 20
    label = Image.new("RGBA", (int(tw) + 20, th + 20), (0, 0, 0, 0))
    ldraw = ImageDraw.Draw(label)
    ldraw.text((10, 0), text, font=font, fill=text_color)
    rotated = label.rotate(90, expand=True, resample=Image.BICUBIC)
    strip_w = x1 - x0
    strip_h = y1 - y0
    px = x0 + (strip_w - rotated.width) / 2
    py = y0 + (strip_h - rotated.height) / 2
    return rotated, (int(px), int(py))


def build_card_template(item_name, facts, product_img_bytes, display_title=None):
    """Reliable coded fallback template (no AI text rendering)."""
    W = H = 1400
    pal = pick_palette(item_name)
    img = Image.new("RGB", (W, H), pal["card"])
    draw = ImageDraw.Draw(img)

    strip_w = 150
    strip_x0 = W - strip_w
    ghost_color = tuple(max(0, c - 18) for c in pal["accent"])
    rounded_rect(draw, (strip_x0, 0, W, H), 0, pal["accent"])
    ghost_img, ghost_pos = vertical_ghost_strip(draw, strip_x0, 0, W, H, pal["accent"], "FACTS", ghost_color + (255,))
    img.paste(ghost_img, ghost_pos, ghost_img)

    leaf_color = tuple(max(0, c - 35) for c in pal["band"]) + (130,)
    leaf1 = leaf_image(190, 85, leaf_color, 25)
    img.paste(leaf1, (-40, -10), leaf1)

    title_font = load_font("arialbd.ttf", 92)
    tag_font = load_font("arialbd.ttf", 26)
    label_font = load_font("arialbd.ttf", 25)
    body_font = load_font("arial.ttf", 25)
    icon_font = load_font("arialbd.ttf", 24)

    content_w = strip_x0 - 70
    title_text = (display_title or simplify_title(item_name)).upper()
    title_lines = wrap_text(draw, title_text, title_font, content_w)[:2]
    ty = 55
    for line in title_lines:
        draw.text((60, ty), line, font=title_font, fill=pal["accent"], anchor="la")
        ty += 98

    pill_text = "QUICK FACTS"
    pill_w = draw.textlength(pill_text, font=tag_font) + 56
    pill_h = 54
    py = ty + 14
    rounded_rect(draw, (60, py, 60 + pill_w, py + pill_h), pill_h / 2, pal["accent"])
    draw.text((60 + pill_w / 2, py + pill_h / 2), pill_text, font=tag_font, fill=(255, 250, 240), anchor="mm")

    facts_top = py + pill_h + 40
    photo_h = 620
    photo_top = H - photo_h - 50
    gap = 18
    facts_bottom = photo_top - 30
    available_h = max(facts_bottom - facts_top, 0)

    fact_slots = facts[:4] or [("Profile", "Details coming soon for this item.")]
    count = len(fact_slots)
    row_h = min(130, (available_h - gap * (count - 1)) / count) if count else 0
    row_h = max(row_h, 70)
    block_h = row_h * count + gap * (count - 1)
    start_y = facts_top + max((available_h - block_h) / 2, 0)

    icon_glyphs = ["1", "2", "3", "4"]
    y = start_y
    for i, (label, value) in enumerate(fact_slots):
        pill_row(draw, 60, y, content_w, row_h, label, value, label_font, body_font, icon_font,
                  pal["accent"], (255, 250, 240), (255, 250, 240), icon_glyphs[i])
        y += row_h + gap

    photo_w = W - 60 - 40
    photo_size = (photo_w, photo_h)
    prod = Image.open(io.BytesIO(product_img_bytes))
    photo = rounded_photo(prod, photo_size, 30)

    shadow = Image.new("RGBA", (photo_size[0] + 50, photo_size[1] + 50), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((25, 28, photo_size[0] + 25, photo_size[1] + 28), 30, fill=(0, 0, 0, 80))
    shadow = shadow.filter(ImageFilter.GaussianBlur(16))
    img.paste(shadow, (60 - 25, int(photo_top) - 22), shadow)
    img.paste(photo, (60, int(photo_top)), photo)

    leaf2 = leaf_image(150, 65, leaf_color, 200)
    img.paste(leaf2, (30, H - 110), leaf2)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def generate_card(mpc, item_name, image_url, profile, texture, best_uses, origin,
                   api_key, api_base=DEFAULT_API_BASE, model=DEFAULT_MODEL,
                   skip_ai_design=False, display_title=""):
    """Returns (ok, png_bytes_or_None, filename, warning_or_error)."""
    if not mpc or not item_name:
        return False, None, None, "MPC and Item Name are required."

    ref_bytes, mime_type = None, None
    if image_url:
        try:
            ref_bytes, mime_type = fetch_image_bytes(image_url)
        except Exception as e:
            return False, None, None, f"Could not fetch reference image: {e}"

    warning = None

    if not all([profile, texture, best_uses, origin]):
        if api_key:
            auto_data, err = auto_generate_facts(item_name, api_base, model, api_key)
            if auto_data:
                profile = profile or str(auto_data.get("profile", "")).strip()
                texture = texture or str(auto_data.get("texture", "")).strip()
                best_uses = best_uses or str(auto_data.get("best_uses", "")).strip()
                origin = origin or str(auto_data.get("origin", "")).strip()
            else:
                note = f"Could not auto-generate the missing fact field(s): {err}"
                warning = f"{warning} {note}".strip() if warning else note
        else:
            note = "Some fact fields were left blank and no API key is configured to auto-generate them."
            warning = f"{warning} {note}".strip() if warning else note

    facts = [(l, v) for l, v in [
        ("Profile", profile), ("Texture", texture),
        ("Best Uses", best_uses), ("Origin & Advantage", origin),
    ] if v]
    resolved_title = display_title.strip() or simplify_title(item_name)
    fname = f"{mpc}.png"

    if api_key and not skip_ai_design:
        full_bytes, err = generate_full_card_ai(
            api_base, model, api_key, ref_bytes, mime_type, item_name, resolved_title, facts, DEFAULT_STYLE
        )
        if full_bytes:
            note = "AI-designed card — please check for any text glitches before publishing."
            warning = f"{warning} {note}".strip() if warning else note
            return True, full_bytes, fname, warning
        else:
            note = f"AI full-card design failed, used the simple template instead. ({err})"
            warning = f"{warning} {note}".strip() if warning else note
    else:
        note = "Used the simple template (AI design skipped)." if skip_ai_design else \
               "No API key configured — used the simple template instead."
        warning = f"{warning} {note}".strip() if warning else note

    product_img_bytes = ref_bytes
    if product_img_bytes is None:
        if not api_key:
            return False, None, None, "No reference image given and no API key configured, so there is no image to use."
        ai_bytes, err = generate_ai_image(api_base, model, api_key, ref_bytes, mime_type, item_name)
        if not ai_bytes:
            return False, None, None, f"No reference image given and AI image generation failed: {err}"
        product_img_bytes = ai_bytes

    card_bytes = build_card_template(item_name, facts, product_img_bytes, display_title=resolved_title)
    return True, card_bytes, fname, warning
