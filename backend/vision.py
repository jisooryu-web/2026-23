"""Photo -> observation JSON. The model only describes what is visible; it never decides disposal."""
from __future__ import annotations

import base64, io, json
from openai import OpenAI
from PIL import Image, ImageOps

from config import MAX_PIXELS, MAX_SIDE, MODEL
from judge import RULES
from schemas import FIELD_VALUES, UNSUPPORTED

try:  # iPhone HEIC support (optional)
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = OpenAI()  # reads OPENAI_API_KEY from .env
    return _client


PROMPT_TEMPLATE = """You are a visual inspector for a recycling assistant (Seoul, Korea).
Your ONLY job is to report what is visibly present in the photo.
You must NOT decide how the item should be disposed of, and you must NOT apply any recycling rules.
A separate rule engine makes all decisions based on your observations.

# Core principles
1. Report only what you can actually see. Never infer from typical products or common sense.
2. If a feature is hidden, blurry, too dark, cut off, or ambiguous, answer "unknown".
   A wrong answer is far worse than "unknown": "unknown" triggers a retake, a wrong answer misleads the user.
3. Be conservative: when a value is between two options, choose the worse one
   (e.g. between contamination level 2 and 3, answer "3"; if a label might remain, do not answer "absent").
4. Output a single JSON object only. No markdown, no explanations outside the JSON.

# Item categories (choose exactly one item ID)
{ITEM_LINES}
- "X00": anything else, multiple different items with no clear main item, or you cannot tell.
If several objects appear, judge only the single largest, most central object.

# Observation fields
Include ONLY the fields listed for the chosen item. Leave every other field out.
{FIELD_LINES}

# Field definitions
- is_clear: "true" if the bottle plastic itself is colorless and see-through; "false" if the plastic is tinted
  (green, brown, blue, white...). The color of the liquid or the label does NOT count.
- label: "present" if any plastic film or paper label remains on the body, even partially;
  "absent" only if the full body is visible with no label remnant. If a side that could hide a label is not visible, "unknown".
- liquid: "present" if any liquid or contents are visible inside (a layer at the bottom, foam, residue of the product);
  "absent" if the interior is visibly empty (small water droplets from rinsing count as "absent").
- crushed: "true" if the container is visibly flattened or crushed.
- cap: "closed" if a cap is screwed on; "present" if a cap or lid is attached in any way; "absent" if there is no cap.
  For PET bottles use "closed" or "absent"; for glass bottles use "present" or "absent".
- contamination_level: food or contents residue left on/in a food container (NOT oil coloring; that is "stain").
  "1" = no visible food, sauce, smear or contents at all.
  "2" = only thin sauce marks, water drops, or powder covering less than 1/3; no solid food at all.
  "3" = any solid food (rice grains, noodles, chunks) visible, OR residue covering 1/3 to 2/3.
  "4" = food scraps or residue covering most (2/3 or more) of the container; its shape is still recognizable.
  "5" = the whole container is covered so that its shape or material cannot be recognized.
  If the inside is not visible (lid on, photo from the side), "unknown".
- stain: "present" if oil or red/orange color has soaked into the surface (typical of spicy soup) and remains as a tint;
  "absent" if the visible surface keeps its original color. Do NOT confuse printed designs or shadows with stains.
- other_material: "present" if a part of a different material is attached (paper label, aluminum film, sticker).
- plastic_part: "present" if a plastic cap, nozzle cover or ring is attached to a metal can.
- broken: "true" if the item is cracked, chipped or shattered.
- foreign_object: "present" if something that does not belong is inside the bottle (cigarette butt, straw, paper).
- pump_attached: "true" if the pump head is still attached to the container.
- is_white: "true" if the styrofoam is plain white; "false" if colored, printed all over, or coated.
- tape_label: "present" if tape, a shipping label, or a sticker remains on the styrofoam box.
- umbrella_type: "long" for a straight long umbrella, "folding" for a compact folding umbrella.

# Before/after comparison (only when two images are given)
The FIRST image is the BEFORE photo taken earlier. The SECOND image is the CURRENT photo after the user's cleanup.
- Report every observation field for the CURRENT photo only.
- Use the BEFORE photo only to (a) decide "same_item" and (b) judge changes more carefully.
- same_item: "true" if the CURRENT object is very likely the same physical object (same shape, size, brand, print, damage);
  "false" if it is clearly a different object; "unknown" if you cannot tell.
When only one image is given, set "same_item" to "unknown".

# Confidence
"confidence" is your confidence in the "item" ID only (0.0 to 1.0).
Use below 0.6 when the object is partially visible, unusual, or could be another category.

# Notes
"notes" is one short English sentence explaining the key visual evidence. This is for debugging only.

# Output format
{
  "item": {ITEM_KEYS},
  "confidence": number,
  "same_item": "true" | "false" | "unknown",
  "observations": { only the fields listed for the item },
  "notes": string
}

# Examples
Photo: a clear water bottle, blue label around the middle, cap on, empty, not crushed.
{"item":"P01","confidence":0.95,"same_item":"unknown","observations":{"is_clear":"true","label":"present","liquid":"absent","crushed":"false","cap":"closed"},"notes":"Blue label wraps a clear, empty bottle."}

Photo: a styrofoam ramen cup seen from above, thin broth film at the bottom, orange tint on the inner wall.
{"item":"P04","confidence":0.9,"same_item":"unknown","observations":{"contamination_level":"2","stain":"present"},"notes":"Thin broth film and orange tint on the inner wall."}

Photo: a ramen cup photographed from the side with the lid half closed.
{"item":"P04","confidence":0.85,"same_item":"unknown","observations":{"contamination_level":"unknown","stain":"unknown"},"notes":"Interior not visible because of the lid and side angle."}
"""
# The item list and per-item fields come from rules.json, so editing rules.json is enough for the AI to know.
# .replace() instead of .format(): the prompt has many JSON braces that .format() would misread.


def _fields(rule):
    keys = [c.key for c in rule.conditions]
    if rule.split and rule.split.method == "photo":
        keys.append(rule.split.key)
    return keys


def _values(key):
    return " | ".join(f'"{v}"' for v in sorted(FIELD_VALUES[key])) + ' | "unknown"'


ITEM_LINES = "\n".join(f'- "{key}": {rule.ai_hint}' for key, rule in RULES.items())
ITEM_KEYS = " | ".join(f'"{key}"' for key in [*RULES, UNSUPPORTED])
FIELD_LINES = "\n".join(
    f'- {key}: ' + (", ".join(f"{f} ({_values(f)})" for f in _fields(rule)) or "no fields")
    for key, rule in RULES.items())
SYSTEM_PROMPT = (PROMPT_TEMPLATE.replace("{ITEM_LINES}", ITEM_LINES)
                 .replace("{ITEM_KEYS}", ITEM_KEYS).replace("{FIELD_LINES}", FIELD_LINES))


def prepare_image(data: bytes) -> bytes:
    """Any uploaded image (JPEG/PNG/HEIC...) -> rotated, resized JPEG bytes. Raises ValueError if unreadable."""
    try:
        img = Image.open(io.BytesIO(data))       # reads only the header here, pixels are not decoded yet
        if img.width * img.height > MAX_PIXELS:   # e.g. a 20000x20000 PNG would take ~1.2GB of memory
            raise ValueError("image too large in pixels")
        img = ImageOps.exif_transpose(img)        # respect phone rotation
        img = img.convert("RGB")
        img.thumbnail((MAX_SIDE, MAX_SIDE))
    except Exception as e:
        raise ValueError("unreadable image") from e
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85)      # re-encoding also drops EXIF (GPS etc.)
    return out.getvalue()


def _image_part(jpeg: bytes):
    b64 = base64.b64encode(jpeg).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}}


def observe(image: bytes, prev_image: bytes | None = None) -> dict:
    """image / prev_image: JPEG bytes from prepare_image()."""
    content = [{"type": "text", "text": (
        "Two images follow: BEFORE, then CURRENT. Return the observation JSON for the CURRENT photo."
        if prev_image else "Inspect this photo and return the observation JSON.")}]
    if prev_image:
        content.append(_image_part(prev_image))
    content.append(_image_part(image))

    res = _get_client().chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": content}],
    )
    return json.loads(res.choices[0].message.content)


def observe_file(path: str, prev_path: str | None = None) -> dict:
    """Convenience for CLI and tests: file paths instead of bytes."""
    with open(path, "rb") as f:
        cur = prepare_image(f.read())
    prev = None
    if prev_path:
        with open(prev_path, "rb") as f:
            prev = prepare_image(f.read())
    return observe(cur, prev)


if __name__ == "__main__":
    import sys
    # python vision.py current.jpg [before.jpg]
    print(json.dumps(observe_file(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None),
                     ensure_ascii=False, indent=2))
