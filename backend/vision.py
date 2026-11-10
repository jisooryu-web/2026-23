"""Photo -> observation JSON. The model only describes what is visible; it never decides disposal."""
from __future__ import annotations

import base64, io, json, os
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageOps

try:  # iPhone HEIC support (optional)
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

load_dotenv()
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_SIDE = 1024          # long side in px; enough for residue/stains, cuts cost and latency
_client = None


def _get_client():
    global _client
    if _client is None:
        _client = OpenAI()  # reads OPENAI_API_KEY from .env
    return _client


SYSTEM_PROMPT = """You are a visual inspector for a recycling assistant.
Your ONLY job is to report what is visibly present in the photo.
You must NOT decide how the item should be disposed of, and you must NOT apply any recycling rules.
A separate rule engine makes all decisions based on your observations.

# Core principles
1. Report only what you can actually see. Never infer from typical products or common sense.
2. If a feature is hidden, blurry, too dark, cut off, or ambiguous, answer "unknown".
   Wrong answers are far worse than "unknown"; "unknown" triggers a retake, a wrong answer misleads the user.
3. Fields that do not apply to the identified item must be "unknown".
4. Output a single JSON object only. No markdown, no explanations outside the JSON.

# Item categories (choose exactly one)
- "pet_bottle": a plastic beverage bottle (water, soda, juice, tea). Includes clear and colored PET bottles.
  Does NOT include shampoo/detergent containers, cups, or food trays.
- "cup_noodle": an instant noodle cup container (styrofoam, paper, or plastic), with or without lid.
- "broken_glass": shattered or cracked glass pieces, or a glass item that is visibly broken.
- "receipt": a printed store/card receipt (thin paper slip with itemized text).
- "unsupported": anything else, multiple different items, no clear main item, or you cannot tell.
If several objects appear, judge only the single largest, most central object. If there is no clear main object, use "unsupported".

# Observation fields and how to judge them
- is_transparent: "true" if the bottle body is clear/colorless and you can see through it;
  "false" if the plastic itself is tinted (green, brown, blue, white, etc.).
  The color of the liquid or the label does NOT count; look at the bottle material where the label does not cover it.
- label_attached: "true" if any plastic film or paper label remains wrapped or stuck on the bottle body, even partially;
  "false" only if the full bottle body is visible and no label remnant is present.
  If the back side or part of the body is not visible and could hide a label, answer "unknown".
- liquid_inside: "true" if any liquid or contents are visible inside (a layer at the bottom, pooled liquid, foam);
  "false" if the interior is visibly empty (small water droplets from rinsing count as "false").
- food_residue: amount of solid or liquid food left inside a food container.
  "none" = interior visibly clean or only water droplets;
  "light" = a few small specks, a thin film, or a small amount of broth;
  "heavy" = noodles, chunks, visible broth pool, or residue covering a large area.
  If the inside of the container is not visible (lid on, photo from the side), answer "unknown".
- red_oil_stain: "true" if red/orange oily discoloration is visible on the inner surface (typical of spicy soup);
  "false" if the inner surface is visible and its original color is uniform.
  Do NOT confuse printed designs or shadows with stains. If unsure, "unknown".
- material: the container material.
  "styrofoam" = white, light, foam-like with a bead texture;
  "paper" = paper cup with a printed outer surface and a smooth or coated inner surface;
  "plastic" = rigid or semi-rigid plastic;
  "unknown" if you cannot tell.

# Before/after comparison (only when two images are given)
The FIRST image is the BEFORE photo taken earlier. The SECOND image is the CURRENT photo after the user's cleanup.
- Report every observation field for the CURRENT photo only.
- Use the BEFORE photo only to (a) decide "same_item" and (b) judge changes more carefully,
  e.g. whether a stain that was visible before is now gone or only fainter.
- same_item: "true" if the CURRENT object is very likely the same physical object (same shape, size, brand, print, damage);
  "false" if it is clearly a different object; "unknown" if you cannot tell.
When only one image is given, set "same_item" to "unknown".

# Confidence
"confidence" is your confidence in the "item" category only (0.0 to 1.0).
Use below 0.6 when the object is partially visible, unusual, or could be another category.

# Notes
"notes" is one short English sentence explaining the key visual evidence. This is for debugging only.

# Output format (exactly these keys)
{
  "item": "pet_bottle" | "cup_noodle" | "broken_glass" | "receipt" | "unsupported",
  "confidence": number,
  "same_item": "true" | "false" | "unknown",
  "observations": {
    "is_transparent": "true" | "false" | "unknown",
    "label_attached": "true" | "false" | "unknown",
    "liquid_inside": "true" | "false" | "unknown",
    "food_residue": "none" | "light" | "heavy" | "unknown",
    "red_oil_stain": "true" | "false" | "unknown",
    "material": "styrofoam" | "paper" | "plastic" | "unknown"
  },
  "notes": string
}

# Examples
Photo: a clear water bottle, blue label around the middle, cap on, empty.
{"item":"pet_bottle","confidence":0.95,"same_item":"unknown","observations":{"is_transparent":"true","label_attached":"true","liquid_inside":"false","food_residue":"unknown","red_oil_stain":"unknown","material":"unknown"},"notes":"Blue label wraps a clear, empty bottle."}

Photo: a styrofoam ramen cup seen from above, a little broth at the bottom, orange tint on the inner wall.
{"item":"cup_noodle","confidence":0.9,"same_item":"unknown","observations":{"is_transparent":"unknown","label_attached":"unknown","liquid_inside":"unknown","food_residue":"light","red_oil_stain":"true","material":"styrofoam"},"notes":"Small broth pool and orange stain on the inner wall of a foam cup."}

Photo: a ramen cup photographed from the side with the lid half closed.
{"item":"cup_noodle","confidence":0.85,"same_item":"unknown","observations":{"is_transparent":"unknown","label_attached":"unknown","liquid_inside":"unknown","food_residue":"unknown","red_oil_stain":"unknown","material":"paper"},"notes":"Interior not visible because of the lid and side angle."}
"""


def prepare_image(data: bytes) -> bytes:
    """Any uploaded image (JPEG/PNG/HEIC...) -> rotated, resized JPEG bytes. Raises ValueError if unreadable."""
    try:
        img = Image.open(io.BytesIO(data))
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
