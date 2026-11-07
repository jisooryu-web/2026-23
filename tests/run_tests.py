"""cases.json의 정답과 LLM 관찰 결과를 비교해 정확도를 출력
실행: tests 폴더에서  python run_tests.py"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from vision import observe
from judge import judge

here = os.path.dirname(__file__)
cases = json.load(open(os.path.join(here, "cases.json"), encoding="utf-8"))
item_ok, field_ok, field_total, rows = 0, 0, 0, []

for c in cases:
    r = observe(os.path.join(here, c["image"]))
    exp, obs = c["expected"], r.get("observations", {})
    hit = r.get("item") == exp["item"]
    item_ok += hit
    wrong = []
    for k, v in exp.items():
        if k == "item":
            continue
        field_total += 1
        if obs.get(k) == v:
            field_ok += 1
        else:
            wrong.append(f"{k}: 정답 {v} / AI {obs.get(k)}")
    status = judge(r)["status"]
    rows.append((c["image"], "O" if hit else f"X({r.get('item')})", status, "; ".join(wrong) or "-"))

print(f"품목 정확도: {item_ok}/{len(cases)}")
print(f"상태 정확도: {field_ok}/{field_total}")
for row in rows:
    print(" | ".join(row))
