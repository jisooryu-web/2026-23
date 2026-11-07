"""사진 → LLM 관찰 결과(JSON). LLM은 판정하지 않고 보이는 것만 말한다."""
import base64, json, os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI()  # OPENAI_API_KEY는 .env에서 읽음
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

PROMPT = """너는 분리배출 판정을 하지 않는다. 사진에서 '보이는 것'만 아래 JSON으로 답하라.
확실하지 않으면 반드시 "unknown"을 써라. 추측하지 마라.
{
  "item": "pet_bottle | cup_noodle | broken_glass | receipt | unsupported",
  "confidence": 0.0~1.0,
  "observations": {
    "is_transparent": "true | false | unknown",
    "label_attached": "true | false | unknown",
    "liquid_inside": "true | false | unknown",
    "food_residue": "none | light | heavy | unknown",
    "red_oil_stain": "true | false | unknown",
    "material": "styrofoam | paper | plastic | unknown"
  }
}
해당 품목과 관계없는 항목은 "unknown"으로 둔다."""


def _encode(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def observe(image_path):
    res = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{_encode(image_path)}"}},
            ],
        }],
    )
    return json.loads(res.choices[0].message.content)


if __name__ == "__main__":
    import sys
    print(json.dumps(observe(sys.argv[1]), ensure_ascii=False, indent=2))
