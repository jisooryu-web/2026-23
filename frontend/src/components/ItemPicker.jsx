import { useState } from "react";

// 품목 직접 선택: 검색 전에는 자주 찾는 품목만, 입력하면 이름·다른 이름(keywords)으로 찾아서 보여 준다
const SHOW = 8;
const norm = (s) => String(s).toLowerCase().replace(/[\s·(),/-]/g, "");

function ItemPicker({ question, disabled, onPick }) {
  const [query, setQuery] = useState("");
  const q = norm(query);
  const options = question.options ?? [];
  const matches = q
    ? options.filter((o) => [o.label, ...(o.keywords ?? [])].some((w) => norm(w).includes(q)))
    : options;

  return (
    <div className="question item-picker">
      <p>{question.text}</p>
      <input
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="예: 우유팩, 택배 상자, 치킨 뼈"
      />
      <p className="picker-hint">{q ? `검색 결과 ${matches.length}개` : "자주 찾는 품목"}</p>
      <div className="picker-options">
        {matches.slice(0, SHOW).map((o) => (
          <button key={o.value} disabled={disabled} onClick={() => onPick(question.key, o.value)}>
            {o.label}
          </button>
        ))}
      </div>
      {q && matches.length === 0 && (
        <p className="picker-hint">찾는 품목이 없어요. 아직 지원하지 않는 품목일 수 있어요.</p>
      )}
    </div>
  );
}

export default ItemPicker;
