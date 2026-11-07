
function JudgeResult({ result, onRetake, attempt }) {
  if (!result?.judgement) return null;

  const judgement = result.judgement;

  switch (judgement.status) {
    case "pass":
      return (
        <div className="result-card">
          <h2>분리배출 가능!</h2>
          <p>{judgement.disposal}</p>

          {judgement.warnings?.length > 0 && (
            <>
              <h3>주의사항</h3>
              <ul>
                {judgement.warnings.map((warning, index) => (
                  <li key={index}>{warning}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      );

    case "need_action":
      return (
        <div className="result-card">
          <h2>먼저 처리해야 할 항목이 있어요.</h2>
          <ul>
            {judgement.checklist?.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
          <button onClick={onRetake} disabled={attempt >= 3}>
            다시 찍기
          </button>
        </div>
      );

    case "retake":
      return (
        <div className="result-card">
          <h2>사진을 다시 찍어 주세요.</h2>
          <p>{judgement.message}</p>
          <button onClick={onRetake} disabled={attempt >= 3}>
            다시 찍기
          </button>
        </div>
      );

    case "question":
      return (
        <div className="result-card">
          <h2>추가 확인이 필요해요.</h2>
          {judgement.questions?.map((question, index) => (
            <p key={index}>{question}</p>
          ))}
        </div>
      );

    case "fallback":
      return (
        <div className="result-card">
          <h2>대체 배출 방법</h2>
          <p>{judgement.disposal}</p>
        </div>
      );

    case "unsupported":
      return (
        <div className="result-card">
          <h2>지원하지 않는 품목</h2>
          <p>{judgement.message}</p>
        </div>
      );

    default:
      return <p>알 수 없는 판정 결과입니다.</p>;
  }
}

export default JudgeResult;
