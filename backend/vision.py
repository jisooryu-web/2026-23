"""Photo -> observation JSON. The model only describes what is visible; it never decides disposal."""
from __future__ import annotations

import base64, io, json
from openai import OpenAI
from PIL import Image, ImageOps

from config import AI_TIMEOUT, MAX_PIXELS, MAX_SIDE, MIN_SIDE, MODEL, PREV_IMAGE_DETAIL
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
        _client = OpenAI(timeout=AI_TIMEOUT, max_retries=1)  # reads OPENAI_API_KEY from .env
    return _client


PROMPT_TEMPLATE = """You are a visual inspector for a recycling assistant (Seoul, Korea).
Your ONLY job is to report what is visibly present in the photo.
You must NOT decide how the item should be disposed of, and you must NOT apply any recycling rules.
A separate rule engine makes all decisions based on your observations.

# Core principles
1. Report only what you can actually see. Never infer from typical products or common sense.
2. If a feature is hidden, blurry, too dark, cut off, or ambiguous, answer "unknown".
   A wrong answer is far worse than "unknown": "unknown" triggers a retake, a wrong answer misleads the user.
3. Be conservative only about what you actually see: when a value is between two options, choose the worse one
   (e.g. between contamination level 2 and 3, answer "3"; if a torn label edge remains, answer "present").
   But never report a part that is not visible in the photo: if the relevant surface is clearly visible and clean, answer "absent".
4. Output a single JSON object only. No markdown, no explanations outside the JSON.

# Choosing the subject (do this first)
The photo is taken by a user who wants to throw away ONE object. Other things often appear too
(table, floor, shelves, other trash, packaging, hands). Pick the SUBJECT: the object the photographer is aiming at.
- Usually it is near the center, the largest in the frame, in the sharpest focus, closest to the camera, or held in a hand.
- Ignore everything else completely. Background objects must never change your answer and never make it "other".
- All observation fields describe the SUBJECT only.

# Identify the material before the category
Many objects have the same shape (cup, bottle, tray) but different materials, and the material decides the category.
Look at the visual cues of the SUBJECT itself, not its contents or background:
- glass: hard, thick walls, shiny reflections and highlights, sharp see-through edges, heavy-looking base.
- rigid plastic: lighter, thinner walls, molded seams, often slightly cloudy or tinted, may be squeezable.
- paper: opaque and matte, printed surface, rolled or folded paper edges.
- styrofoam: light white foam with a fine bead-like texture, thick soft-looking walls.
- soft film: thin, crinkled, flexible plastic film.
- metal: metallic shine, rolled rim, seams.
A drink inside (e.g. coffee in a glass) does not change the material of the container.

# Item categories (choose exactly one item name for the SUBJECT, spelled exactly as listed)
{ITEM_LINES}
- "other": the SUBJECT is clearly none of the categories above (e.g. a phone charger, a hair tie, food itself).
  For "other", still report general_class in observations.
- "unknown": there is no recognizable subject at all (blank, extremely dark or blurred, only background).
Choose a category only when the subject IS that kind of object (a real example of it).
- If it is that kind of object but partly hidden, unusual or hard to see, still choose it, with confidence below 0.6.
- If it is a different kind of object that is not listed, answer "other". Never force it into the closest-sounding category
  (e.g. a pen, cable, remote control, plastic case or kitchen tool is NOT a toothbrush, hanger or CD; a mug is NOT a tumbler).

# Observation fields
Include ONLY the fields listed for the chosen item. Leave every other field out.
{FIELD_LINES}

# Field definitions
- is_clear: "true" if the bottle plastic itself is colorless and see-through; "false" if the plastic is tinted
  (green, brown, blue, white...). The color of the liquid or the label does NOT count.
- label: "present" if a SEPARATE plastic film, paper label or sticker remains on the body, even partially;
  "absent" if the visible body has no such separate label. Text, logos or patterns printed directly on the plastic,
  embossed marks molded into it, and small sticky glue marks left after peeling, are NOT labels. If a large side that could hide a label is not visible, "unknown".
- liquid: "present" if any liquid or contents are visible inside (a layer at the bottom, foam, residue of the product);
  "absent" if the interior is visibly empty (small water droplets from rinsing count as "absent").
- crushed: "true" if the container or box is visibly flattened, crushed, or folded flat.
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
- other_material: "present" if a part of a different material is attached (paper label, aluminum film, sticker,
  a paper sleeve on a plastic cup).
- plastic_part: "present" if a plastic cap, nozzle cover, ring or straw is attached to a metal can, a paper carton,
  or a plastic film package (e.g. the hard plastic lid of a wet-wipe pouch).
- broken: "true" if the item is cracked, chipped or shattered.
- foreign_object: "present" if something that does not belong is inside the bottle or cup (cigarette butt, straw, paper).
- pump_attached: "true" if the pump head is still attached to the container.
- is_white: "true" if the styrofoam is plain white; "false" if colored, printed all over, or coated.
- tape_label: "present" if tape, a shipping label, a sticker, or plastic wrap film covering a tray remains on the styrofoam
  or cardboard; "absent" if the visible surface has none of these.
- umbrella_type: "long" for a straight long umbrella, "folding" for a compact folding umbrella.
- general_class: only for "other". The broad kind of the SUBJECT. Check in this order and pick the first that fits:
  "electronic" if it runs on electricity or batteries (has a plug, cable, battery, screen or circuit board);
  "large" if it is too big to fit in a 50-liter trash bag (bicycle, large toy, big plastic storage box);
  "non_combustible" if it is made mainly of glass, ceramic, stone, concrete or soil;
  "general" for everything else (fabric, plastic, wood, rubber or mixed small items, e.g. a hair tie, a phone case, a small plastic toy).
  "unknown" if you cannot tell.

# Before/after comparison (only when two images are given)
The FIRST image is the BEFORE photo taken earlier. The SECOND image is the CURRENT photo after the user's cleanup.
- Report every observation field for the CURRENT photo only.
- Use the BEFORE photo only to (a) decide "same_item" and (b) judge changes more carefully.
- Do NOT copy observations from the BEFORE photo. If a label, wrap, tape or contents seen BEFORE is gone in the CURRENT photo,
  report it as "absent" for the CURRENT photo.
- same_item: "true" if the CURRENT object is very likely the same physical object (same shape, size, brand, print, damage);
  "false" if it is clearly a different object; "unknown" if you cannot tell.
When only one image is given, set "same_item" to "unknown".

# Confidence
"confidence" is your confidence in the "item" ID only (0.0 to 1.0).
Use below 0.6 when the object is partially visible, unusual, or could be another category.

# Subject name
"subject" is a short, SPECIFIC Korean description of the SUBJECT (up to about 20 characters),
written so a person can tell exactly what it is: what the object is, plus its key material or contents if that matters.
Do NOT generalize to a broader word (a nail-clipper case is NOT "가방"; a cosmetics jar is NOT "용기").
It must agree with "notes". Always fill it, even when the item is "other".
Examples: "투명 페트병", "케첩 통", "커피가 든 유리컵", "손톱깎이 세트 케이스", "랩 씌운 스티로폼 트레이", "고무줄 머리끈".

# Notes
"notes" is one short English sentence: name the subject you chose and the key visual evidence. This is for debugging only.

# Output format
{
  "item": {ITEM_KEYS},
  "confidence": number,
  "same_item": "true" | "false" | "unknown",
  "observations": { only the fields listed for the item },
  "subject": string,
  "notes": string
}

# Examples
Photo: a pair of glasses on a desk, a phone and papers in the background.
{"item":"eyeglasses","confidence":0.9,"same_item":"unknown","observations":{},"subject":"검은 뿔테 안경","notes":"Eyeglasses in the center; background ignored."}

Photo: a wooden chair in a room.
{"item":"furniture","confidence":0.9,"same_item":"unknown","observations":{},"subject":"나무 의자","notes":"A chair is furniture."}

Photo: a hair dryer with its power cord on a bathroom counter.
{"item":"other","confidence":0.9,"same_item":"unknown","observations":{"general_class":"electronic"},"subject":"헤어드라이어","notes":"Electric appliance with a plug."}

Photo: a black zippered case holding nail clippers and small scissors.
{"item":"other","confidence":0.9,"same_item":"unknown","observations":{"general_class":"general"},"subject":"손톱깎이 세트 케이스","notes":"A black case with nail clippers and scissors; not a listed category."}

Photo: a clear water bottle, blue label around the middle, cap on, empty, not crushed.
{"item":"pet_bottle","confidence":0.95,"same_item":"unknown","observations":{"is_clear":"true","label":"present","liquid":"absent","crushed":"false","cap":"closed"},"subject":"투명 페트병","notes":"Blue label wraps a clear, empty bottle."}

Photo: a ketchup squeeze bottle, red sauce visible inside, brand text printed directly on the plastic.
{"item":"other_rigid_plastic_container","confidence":0.9,"same_item":"unknown","observations":{"liquid":"present"},"subject":"케첩 통","notes":"Squeeze sauce bottle, not a drink bottle; printing is on the plastic itself."}

Photo: a clear drinking glass with iced coffee, thick walls and shiny highlights, on a cafe table.
{"item":"ceramic_or_special_glass","confidence":0.9,"same_item":"unknown","observations":{},"subject":"커피가 든 유리컵","notes":"Thick shiny glass cup; the coffee is the contents, the container is glass."}

Photo: a white styrofoam meat tray, plastic wrap and price sticker removed, a few red drops on the tray.
{"item":"styrofoam_box","confidence":0.9,"same_item":"unknown","observations":{"is_white":"true","tape_label":"absent","contamination_level":"2"},"subject":"스티로폼 트레이","notes":"White foam tray, no wrap or sticker left, small red drops."}

Photo: a styrofoam ramen cup seen from above, thin broth film at the bottom, orange tint on the inner wall.
{"item":"cup_noodle_container","confidence":0.9,"same_item":"unknown","observations":{"contamination_level":"2","stain":"present"},"subject":"컵라면 용기","notes":"Thin broth film and orange tint on the inner wall."}

Photo: a ramen cup photographed from the side with the lid half closed.
{"item":"cup_noodle_container","confidence":0.85,"same_item":"unknown","observations":{"contamination_level":"unknown","stain":"unknown"},"subject":"컵라면 용기","notes":"Interior not visible because of the lid and side angle."}
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


ITEM_LINES = "\n".join(f'- "{rule.ai_key}": {rule.ai_hint}' for rule in RULES.values())
ITEM_KEYS = " | ".join(f'"{rule.ai_key}"' for rule in RULES.values()) + ' | "other" | "unknown"'
FIELD_LINES = "\n".join(
    f'- {rule.ai_key}: ' + (", ".join(f"{f} ({_values(f)})" for f in _fields(rule)) or "no fields")
    for rule in RULES.values()) + f'\n- other: general_class ({_values("general_class")})\n- unknown: no fields'
SYSTEM_PROMPT = (PROMPT_TEMPLATE.replace("{ITEM_LINES}", ITEM_LINES)
                 .replace("{ITEM_KEYS}", ITEM_KEYS).replace("{FIELD_LINES}", FIELD_LINES))


def prepare_image(data: bytes) -> bytes:
    """Any uploaded image (JPEG/PNG/HEIC...) -> rotated, resized JPEG bytes. Raises ValueError if unreadable."""
    try:
        img = Image.open(io.BytesIO(data))       # reads only the header here, pixels are not decoded yet
        if img.width * img.height > MAX_PIXELS:   # e.g. a 20000x20000 PNG would take ~1.2GB of memory
            raise ValueError("image too large in pixels")
        if min(img.size) < MIN_SIDE:               # e.g. a 10x10 thumbnail: nothing to see
            raise ValueError("image too small")
        img = ImageOps.exif_transpose(img)        # respect phone rotation
        img = img.convert("RGB")
        img.thumbnail((MAX_SIDE, MAX_SIDE))
    except Exception as e:
        raise ValueError("unreadable image") from e
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85)      # re-encoding also drops EXIF (GPS etc.)
    return out.getvalue()


def _image_part(jpeg: bytes, detail: str = "high"):
    b64 = base64.b64encode(jpeg).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": detail}}


def observe(image: bytes, prev_image: bytes | None = None, item_hint: str | None = None) -> dict:
    """image / prev_image: JPEG bytes from prepare_image().
    item_hint: item ID the user picked by hand (e.g. "P01") when the AI could not recognize the subject."""
    text = ("Two images follow: BEFORE, then CURRENT. Return the observation JSON for the CURRENT photo."
            if prev_image else "Inspect this photo and return the observation JSON.")
    if item_hint in RULES:
        key = RULES[item_hint].ai_key
        text += (f' The user says the subject is "{key}" ({RULES[item_hint].ai_hint})'
                 f' Use item "{key}" and report the fields listed for it.')
    content = [{"type": "text", "text": text}]
    if prev_image:
        # the BEFORE photo is only for "same item?" so low detail is enough (faster, cheaper)
        content.append(_image_part(prev_image, PREV_IMAGE_DETAIL))
    content.append(_image_part(image))

    extra = {}
    if MODEL.startswith(("gpt-4", "gpt-3")):
        extra["temperature"] = 0     # same photo -> same answer (reasoning models do not accept this option)
    res = _get_client().chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        **extra,
        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": content}],
    )
    return json.loads(res.choices[0].message.content)


SAME_PROMPT = """Two photos follow: an earlier photo of an object, then a new photo taken after the user cleaned it
(e.g. removed a label, emptied or rinsed it). Decide only whether the main object in the new photo is the SAME physical
object as in the earlier photo.
These changes are expected and do NOT make it a different object: a label, wrap, tape or sticker removed; contents
emptied; dirt rinsed off; the object crushed or flattened; a different angle, distance, lighting, hand or background.
Answer "false" only when the new photo clearly shows a different object: a different kind of object (e.g. a bottle vs a
can), or a clearly different shape, size, material color or cap color.
If it is the same kind of object and nothing clearly contradicts, answer "true". If you really cannot tell, "unknown".
Answer JSON only: {"same_item": "true" | "false" | "unknown"}"""


def compare_same(prev_image: bytes, image: bytes) -> str:
    """Retake check, separate from observe(): asking one call to compare two photos AND describe the current one made the
    model copy features (e.g. a label) from the BEFORE photo into the current observation. Returns "true"/"false"/"unknown"."""
    extra = {"temperature": 0} if MODEL.startswith(("gpt-4", "gpt-3")) else {}
    res = _get_client().chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        **extra,
        messages=[{"role": "system", "content": SAME_PROMPT},
                  {"role": "user", "content": [{"type": "text", "text": "Earlier photo, then new photo."},
                                               _image_part(prev_image, PREV_IMAGE_DETAIL),
                                               _image_part(image, PREV_IMAGE_DETAIL)]}],
    )
    value = str(json.loads(res.choices[0].message.content).get("same_item", "")).strip().lower()
    return value if value in ("true", "false") else "unknown"


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
