import { useEffect, useState } from "react";
import ItemPicker from "./ItemPicker";
import { getItems } from "../services/judgeApi";

// 상태별 화면. 백엔드 judgement.status 와 1:1 대응
// 판정 근거 화면: 관찰 키의 한국어 이름은 서버가 rules.json(field_labels)에서 보내 준 labels를 먼저 쓰고,
// labels가 없는 예전 응답·Mock일 때만 아래 이름을 씀
const FALLBACK_LABELS = {
  contamination_level: "오염도",
  stain: "착색 흔적",
  other_material: "다른 재질",
  label: "라벨",
  liquid: "내용물",
  cap: "뚜껑",
  crushed: "압축 여부",
  is_clear: "투명 여부",
  general_class: "일반 분류",
};

const VALUE_NAMES = {
  present: "있음",
  absent: "없음",
  true: "예",
  false: "아니요",
  unknown: "확인 어려움",
  closed: "닫혀 있음",
  long: "장우산",
  folding: "접이식 우산",
  general: "일반쓰레기",
  non_combustible: "불연성 쓰레기",
  large: "대형 폐기물",
  electronic: "전자제품",
};

function fieldName(labels, key) {
  return (labels && labels[key]) || FALLBACK_LABELS[key] || key;
}

function JudgeResult({ result, loading, onRetake, onAnswer, onRestart, onCorrect }) {
  const [checked, setChecked] = useState({});
  // "품목이 달라요": AI가 품목을 잘못 봤을 때 검색해서 고르면 그 품목 기준으로 다시 판정
  const [picker, setPicker] = useState(null);   // null = 닫힘, {text, items} = 열림

  useEffect(() => setPicker(null), [result]);   // 새 결과가 오면 닫기

  if (!result?.judgement) return null;
  const j = result.judgement;
  const canRetake = j.attempt < j.max_attempts;

  const allChecked = (j.checklist ?? []).every((item) => checked[item.key]);

  async function openPicker() {
    const data = await getItems();
    setPicker({ text: data.text || "찍은 물건이 무엇인가요? 검색해서 고르면 그 품목 기준으로 다시 확인할게요.",
                items: data.items ?? [] });
  }

  // 품목 고르기 목록이 이미 있는 화면(지원 안 함)에서는 버튼을 따로 두지 않음
  const canCorrect = onCorrect && !(j.questions ?? []).some((q) => q.key === "item_hint");

  function toggle(key) {
    setChecked((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  return (
    <div className={`result-card status-${j.status}`}>
      {(j.name || canCorrect) && (
        <div className="item-row">
          {j.name && <p className="item-name">{j.name}</p>}
          {canCorrect && !picker && (
            <button type="button" className="correct-link" disabled={loading} onClick={openPicker}>
              품목이 달라요
            </button>
          )}
        </div>
      )}
      {picker && (
        <div className="correct-picker">
          {picker.items.length > 0 ? (
            <ItemPicker
              question={{ key: "item_hint", text: picker.text, options: picker.items }}
              disabled={loading}
              onPick={(_, value) => onCorrect(value)}
            />
          ) : (
            <p className="picker-hint">품목 목록을 불러오지 못했어요. 잠시 후 다시 시도해 주세요.</p>
          )}
          <button type="button" className="correct-link" onClick={() => setPicker(null)}>닫기</button>
        </div>
      )}
      <h2 className="message">{j.message}</h2>

      {/* 통과 / 대체 안내: 배출 방법을 크게 */}
      {(j.status === "pass" || j.status === "fallback") && (
        <div className="disposal">
          <span className="disposal-label">배출 방법</span>
          <strong>{j.disposal}</strong>
        </div>
      )}

      {/* 버리는 순서 (통과했을 때만) */}
      {j.status === "pass" && j.how?.length > 0 && (
        <div className="how">
          <strong>이렇게 버려요</strong>
          <ol>
            {j.how.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </div>
      )}

      {/* 어디에 버리는지: 아파트 / 단독주택 */}
      {(j.status === "pass" || j.status === "fallback") && j.places?.length > 0 && (
        <div className="places">
          {j.places.map((p) => (
            <div key={p.title} className="place">
              <strong>📍 {p.title}</strong>
              <ul>
                {p.where.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </div>
          ))}
          <p className="place-note">배출 요일과 장소는 사는 구마다 달라요. 구청 홈페이지에서 확인해 주세요.</p>
        </div>
      )}

      {/* 처리할 일: 체크해야 다시 찍기 가능 */}
      {j.status === "need_action" && (
        <ul className="checklist">
          {j.checklist.map((item) => (
            <li key={item.key}>
              <label>
                <input type="checkbox" checked={!!checked[item.key]} onChange={() => toggle(item.key)} />
                {item.text}
              </label>
            </li>
          ))}
        </ul>
      )}

      {/* 대체 안내: 사진으로 확인하지 못한 항목은 직접 확인 */}
      {j.status === "fallback" && j.checklist?.length > 0 && (
        <div className="self-check">
          <strong>버리기 전에 직접 확인해 주세요</strong>
          <ul>
            {j.checklist.map((item) => (
              <li key={item.key}>{item.text}</li>
            ))}
          </ul>
        </div>
      )}

      {/* 질문: 선택지를 누르면 같은 사진으로 다시 판정 */}
      {j.questions?.length > 0 &&
        j.questions.map((q) =>
          q.key === "item_hint" ? (
            <ItemPicker key={q.key} question={q} disabled={loading} onPick={onAnswer} />
          ) : (
          <div key={q.key} className="question">
            <p>{q.text}</p>
            {q.options.map((opt) => (
              <button key={opt.value} disabled={loading} onClick={() => onAnswer(q.key, opt.value)}>
                {opt.label}
              </button>
            ))}
          </div>
          )
        )}

      {/* 팁: 권고 조건 (안 해도 배출 가능) */}
      {j.tips?.length > 0 && (
        <div className="tips">
          <strong>💡 이렇게 하면 더 좋아요</strong>
          <ul>
            {j.tips.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </div>
      )}

      {/* 주의사항 (깨진 유리 등) */}
      {j.warnings?.length > 0 && (
        <div className="warnings">
          <strong>⚠️ 주의</strong>
          <ul>
            {j.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {/* 버튼 */}
      <div className="actions">
        {j.status === "need_action" && (
          <button onClick={() => onRetake(true)} disabled={!allChecked || !canRetake}>
            {allChecked ? "처리했어요, 다시 찍기" : "모두 체크하면 다시 찍을 수 있어요"}
          </button>
        )}
        {j.status === "retake" && (
          <button onClick={() => onRetake(true)} disabled={!canRetake}>다시 찍기</button>
        )}
        {j.status === "different_item" && (
          <button onClick={() => onRetake(false)}>같은 물건 다시 찍기</button>
        )}
        {["pass", "fallback", "unsupported"].includes(j.status) && (
          <button onClick={onRestart}>다른 물건 판정하기</button>
        )}
      </div>

      <p className="attempt">촬영 {j.attempt} / {j.max_attempts}</p>

      {/* 판정 근거: AI가 본 것 + 기준 출처 (발표 때 신뢰도 설명용) */}
      {result.observation && (
        <details className="evidence">
          <summary>판정 근거 보기</summary>
          <div className="evidence-content">
            <h4>AI 관찰 데이터</h4>
            {Object.entries(result.observation.observations || {}).map(([key, value]) => (
              <p key={key}>
                <strong>{fieldName(result.labels, key)}: </strong>
                {key === "contamination_level" ? `${value}단계` : VALUE_NAMES[String(value)] || String(value)}
              </p>
            ))}
          </div>
          {j.source && <p>기준 출처: {j.source}</p>}
        </details>
      )}
    </div>
  );
}

export default JudgeResult;
