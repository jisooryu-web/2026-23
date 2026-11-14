import { useState, useEffect } from "react";
import JudgeResult from "./components/JudgeResult";
import { judgeImage, isMock, wakeServer } from "./services/judgeApi";
import "./App.css";

const MOCK_STATUSES = ["pass", "need_action", "retake", "question", "fallback", "different_item", "unsupported"];

function App() {
  const [file, setFile] = useState(null);         // 지금 찍은 사진
  const [preview, setPreview] = useState(null);
  const [attempt, setAttempt] = useState(1);      // 몇 번째 촬영인지
  const [firstFile, setFirstFile] = useState(null); // 처음 찍은 사진 (재촬영 전후 비교용)
  const [firstItem, setFirstItem] = useState(null); // 처음 판정된 품목 (같은 물건인지 확인용)
  const [answers, setAnswers] = useState({});     // 질문 답
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [mockStatus, setMockStatus] = useState("pass");

  useEffect(() => {
    wakeServer();
  }, []);

  useEffect(() => {
    if (!file) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function handleFileChange(event) {
    const selected = event.target.files[0];
    event.target.value = ""; // 같은 파일 다시 선택 가능
    if (!selected) return;
    if (!selected.type.startsWith("image/") && !/\.(heic|heif)$/i.test(selected.name)) {
      setError("이미지 파일만 선택할 수 있어요.");
      return;
    }
    setFile(selected);
    setResult(null);
    setError("");
  }

  // reuseObservation: 질문에 답할 때 직전 AI 관찰을 다시 써서 AI 호출을 생략
  async function runJudge(nextAnswers = answers, reuseObservation = null) {
    if (!file) {
      setError("먼저 사진을 찍거나 선택해 주세요.");
      return;
    }
    try {
      setLoading(true);
      setError("");
      const isRetake = attempt > 1;
      const data = await judgeImage({
        image: file,
        attempt,
        prevImage: isRetake ? firstFile : null,
        prevItem: isRetake ? firstItem : null,
        answers: nextAnswers,
        observation: reuseObservation,
        mockStatus,
      });
      // 첫 촬영에서 지원 품목이 나오면 "처음 사진"으로 기억
      if (!isRetake && data.judgement.status !== "unsupported") {
        setFirstFile(file);
        setFirstItem(data.judgement.item);
      }
      setResult(data);
    } catch (err) {
      setError(err.message || "오류가 발생했어요.");
    } finally {
      setLoading(false);
    }
  }

  // 질문에 답하면 같은 사진으로 다시 판정 (촬영 횟수는 그대로)
  function handleAnswer(key, value) {
    const next = { ...answers, [key]: value };
    setAnswers(next);
    runJudge(next, result?.observation ?? null);
  }

  // countsAsAttempt: 처리 후 재촬영이면 true, 다른 물건을 찍어서 다시 찍는 거면 false
  function handleRetake(countsAsAttempt) {
    if (countsAsAttempt) setAttempt((prev) => prev + 1);
    // 체크리스트의 체크박스 항목(예: "헹궈 주세요")은 체크하고 다시 찍었으니 '했어요'로 기억 → 다음 판정에서 다시 묻지 않음
    const checkedBox = (result?.judgement?.checklist ?? []).some((item) => item.key === "checkbox");
    setAnswers((prev) => {
      const next = { ...prev };
      delete next.confirm_same_item; // "같은 물건이 맞나요?"는 새 사진마다 다시 확인
      if (countsAsAttempt && checkedBox) next.checkbox = "true";
      return next;
    });
    setFile(null);
    setResult(null);
    setError("");
  }

  function handleRestart() {
    setFile(null);
    setAttempt(1);
    setFirstFile(null);
    setFirstItem(null);
    setAnswers({});
    setResult(null);
    setError("");
  }

  return (
    <div className="app">
      <h1>AI 분리배출 판정</h1>
      <p>{attempt === 1 ? "버릴 물건을 찍어 주세요." : "처리한 뒤 같은 물건을 다시 찍어 주세요."}</p>

      {!result && (
        <>
          <div className="upload-area">
            {/* capture: 휴대폰에서 바로 후면 카메라 실행 */}
            <input type="file" accept="image/*" capture="environment" onChange={handleFileChange} />
            {preview && (
              <div className="preview">
                <img src={preview} alt="업로드한 사진" />
              </div>
            )}
          </div>

          <button onClick={() => runJudge()} disabled={!file || loading}>
            {loading ? "AI가 확인하는 중..." : "판정하기"}
          </button>
        </>
      )}

      {error && <p className="error">{error}</p>}

      <JudgeResult
        key={`${attempt}-${result?.judgement?.status}`}
        result={result}
        loading={loading}
        onRetake={handleRetake}
        onAnswer={handleAnswer}
        onRestart={handleRestart}
      />

      {/* Mock 모드에서만 보이는 테스트 도구 */}
      {isMock && (
        <div className="mock-test">
          <h3>Mock 응답 선택 (백엔드 없이 화면 테스트)</h3>
          <select value={mockStatus} onChange={(e) => setMockStatus(e.target.value)}>
            {MOCK_STATUSES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
}

export default App;
