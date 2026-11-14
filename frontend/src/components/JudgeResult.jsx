import { useState } from "react";

// 상태별 화면. 백엔드 judgement.status 와 1:1 대응
function JudgeResult({ result, loading, onRetake, onAnswer, onRestart }) {
  const [checked, setChecked] = useState({});

  if (!result?.judgement) return null;
  const j = result.judgement;
  const canRetake = j.attempt < j.max_attempts;

  const allChecked = (j.checklist ?? []).every((item) => checked[item.key]);

  function toggle(key) {
    setChecked((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  return (
    <div className={`result-card status-${j.status}`}>
      {j.name && <p className="item-name">{j.name}</p>}
      <h2>{j.message}</h2>

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
        j.questions.map((q) => (
          <div key={q.key} className="question">
            <p>{q.text}</p>
            {q.options.map((opt) => (
              <button key={opt.value} disabled={loading} onClick={() => onAnswer(q.key, opt.value)}>
                {opt.label}
              </button>
            ))}
          </div>
        ))}

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
          <p>AI 관찰: {result.observation.notes}</p>
          <pre>{JSON.stringify(result.observation.observations, null, 2)}</pre>
          {j.source && <p>기준 출처: {j.source}</p>}
        </details>
      )}
    </div>
  );
}

export default JudgeResult;
