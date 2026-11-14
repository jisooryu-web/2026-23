"""실제 사진으로 AI 정확도를 잰다 (API 키 필요, 사진 수 x 반복 횟수만큼 비용 발생).
실행: 프로젝트 맨 위 폴더에서
    python tests/run_tests.py                 # 사진마다 1번
    python tests/run_tests.py --repeat 3      # 사진마다 3번 (답이 흔들리는지 확인)
    python tests/run_tests.py --save before.json   # 결과 저장 (프롬프트 수정 전후 비교용)

cases.json 한 줄 = 사진 하나와 정답
  {"image": "images/p01_label.jpg",
   "expected": {"item": "P01", "label": "present"},   # 사람이 확인한 관찰 정답 (모르는 필드는 안 적어도 됨)
   "expected_status": "need_action"}                   # 질문에 모두 '예/했어요'라고 했을 때 최종 판정
"""
import argparse, json, os, statistics, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

from judge import RULES, _related, judge
from schemas import Observation
from vision import observe_file


def all_yes(item):
    """사용자가 품목 확인과 체크박스에 모두 '예/했어요'라고 답한 경우의 answers."""
    return {f"confirm_{item}": "true", "checkbox": "true"}


def run_once(case):
    """사진 한 장을 AI에 한 번 보내고, 서버와 똑같이 검사·판정한 결과."""
    started = time.perf_counter()
    raw = observe_file(os.path.join(HERE, case["image"]))
    seconds = time.perf_counter() - started
    obs = Observation.model_validate(raw).model_dump()           # 서버와 같은 검사
    status = judge(obs, 1, all_yes(obs["item"]))["status"]
    return obs, status, seconds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=1, help="사진마다 몇 번 보낼지")
    ap.add_argument("--save", help="결과를 저장할 JSON 파일")
    args = ap.parse_args()

    cases = json.load(open(os.path.join(HERE, "cases.json"), encoding="utf-8"))
    n = {"item_ok": 0, "status_ok": 0, "status_total": 0, "wrong_pass": 0,
         "correct": 0, "cautious": 0, "wrong": 0, "errors": 0, "runs": 0}
    times, rows, wrong_fields, unstable = [], [], [], []

    missing = [c["image"] for c in cases if not os.path.exists(os.path.join(HERE, c["image"]))]
    if missing:
        print(f"사진 파일이 없어서 건너뜀 {len(missing)}장: {missing}\n")
        cases = [c for c in cases if c["image"] not in missing]

    for case in cases:
        exp = case["expected"]
        answers_seen = set()
        for _ in range(args.repeat):
            n["runs"] += 1
            try:
                obs, status, seconds = run_once(case)
            except Exception as e:                               # 키 없음, 시간 초과, 이상한 JSON 등
                n["errors"] += 1
                rows.append({"image": case["image"], "error": f"{type(e).__name__}: {e}"})
                continue
            times.append(seconds)
            answers_seen.add(json.dumps({"item": obs["item"], "observations": obs["observations"]}, sort_keys=True))

            # 분기로 이어진 품목(투명 P01 ↔ 유색 P02 등)은 같은 품목으로 인정
            n["item_ok"] += obs["item"] == exp["item"] or (obs["item"] in RULES and _related(obs["item"], exp["item"]))
            for key, want in exp.items():
                if key == "item":
                    continue
                got = obs["observations"].get(key, "unknown")
                if got == want:
                    n["correct"] += 1
                elif got == "unknown":
                    n["cautious"] += 1        # 모른다고 함 → 재촬영으로 가서 안전하지만 불편
                else:
                    n["wrong"] += 1           # 틀리게 단정 → 잘못된 안내. 0에 가깝게 만드는 게 목표
                    wrong_fields.append(f"{case['image']}  {key}: 정답 {want} / AI {got}")
            if "expected_status" in case:
                n["status_total"] += 1
                n["status_ok"] += status == case["expected_status"]
                # 가장 나쁜 오류: 처리가 필요한데 '통과'라고 안내 (판정 원칙 2)
                n["wrong_pass"] += status == "pass" and case["expected_status"] != "pass"
            rows.append({"image": case["image"], "item": obs["item"], "confidence": obs["confidence"],
                         "status": status, "expected_status": case.get("expected_status"),
                         "seconds": round(seconds, 2), "notes": obs["notes"]})
        if len(answers_seen) > 1:
            unstable.append(case["image"])

    done = n["runs"] - n["errors"]
    print(f"사진 {len(cases)}장 x {args.repeat}번 = {n['runs']}회 (실패 {n['errors']}회)")
    print(f"품목 정확도      {n['item_ok']}/{done}")
    print(f"최종 판정 정답   {n['status_ok']}/{n['status_total']}")
    print(f"잘못된 통과      {n['wrong_pass']}회   ← 처리가 필요한데 '통과'라고 안내. 0이어야 함")
    print(f"관찰 필드        정답 {n['correct']} · 모름(unknown) {n['cautious']} · 틀린 단정 {n['wrong']}   ← 틀린 단정이 가장 중요")
    if args.repeat > 1:
        print(f"답 흔들림        {len(unstable)}/{len(cases)}장  {unstable}")
    if times:
        print(f"속도             평균 {statistics.mean(times):.1f}초 · 최대 {max(times):.1f}초")
    if wrong_fields:
        print("\n틀린 단정:")
        for line in wrong_fields:
            print("  " + line)
    print("\n사진별:")
    for r in rows:
        if "error" in r:
            print(f"  {r['image']}  오류 {r['error']}")
        else:
            mark = "" if r["expected_status"] in (None, r["status"]) else f"  (정답 {r['expected_status']})"
            print(f"  {r['image']}  {r['item']}({r['confidence']})  {r['status']}{mark}  {r['seconds']}초")

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump({"summary": n, "unstable": unstable, "rows": rows}, f, ensure_ascii=False, indent=2)
        print(f"\n{args.save}에 저장했어요")


if __name__ == "__main__":
    main()
