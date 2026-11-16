
import { useState, useEffect } from "react";
import JudgeResult from "./components/JudgeResult";
import { judgeImage, isMock, wakeServer } from "./services/judgeApi";
import "./App.css";

const MOCK_STATUSES = [
  "pass",
  "need_action",
  "retake",
  "question",
  "fallback",
  "different_item",
  "unsupported",
];

function App() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);

  const [attempt, setAttempt] = useState(1);
  const [firstFile, setFirstFile] = useState(null);
  const [firstItem, setFirstItem] = useState(null);

  const [answers, setAnswers] = useState({});
  const [result, setResult] = useState(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [mockStatus, setMockStatus] = useState("pass");
  const [showMockTest, setShowMockTest] = useState(false);

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
    event.target.value = "";

    if (!selected) return;

    if (
      !selected.type.startsWith("image/") &&
      !/\.(heic|heif)$/i.test(selected.name)
    ) {
      setError("이미지 파일만 선택할 수 있어요.");
      return;
    }

    // 결과를 보던 중에 사진 카드의 "다시 촬영하기"로 새 사진을 고르면 처음부터 새로 판정
    // (재촬영 흐름은 결과 카드의 버튼으로. 이전 답·직접 고른 품목이 새 물건에 남지 않게)
    const fresh = result !== null;
    if (fresh) {
      setAttempt(1);
      setFirstFile(null);
      setFirstItem(null);
      setAnswers({});
    }

    setFile(selected);
    setResult(null);
    setError("");

    runJudge(fresh ? {} : answers, null, selected, fresh);
  }

  // AI 판정
  async function runJudge(
    nextAnswers = answers,
    reuseObservation = null,
    imageOverride = file,
    fresh = false
  ) {
    if (!imageOverride) {
      setError("먼저 사진을 선택해 주세요.");
      return;
    }

    try {
      setLoading(true);
      setError("");

      const currentAttempt = fresh ? 1 : attempt;
      const isRetake = currentAttempt > 1;

      const data = await judgeImage({
        image: imageOverride,
        attempt: currentAttempt,
        prevImage: isRetake ? firstFile : null,
        prevItem: isRetake ? firstItem : null,
        answers: nextAnswers,
        observation: reuseObservation,
        mockStatus,
      });

      if (!isRetake && data.judgement.status !== "unsupported") {
        setFirstFile(imageOverride);
        setFirstItem(data.judgement.item);
      }

      setResult(data);
    } catch (err) {
      setError(err.message || "오류가 발생했어요.");
    } finally {
      setLoading(false);
    }
  }

  // 질문 답변
  function handleAnswer(key, value) {
    const next = { ...answers, [key]: value };
    setAnswers(next);

    runJudge(
      next,
      key === "item_hint"
        ? null
        : result?.observation ?? null
    );
  }

  // "품목이 달라요" → 고른 품목 기준으로 지금 사진을 처음부터 다시 판정 (이전 답은 버림)
  function handleCorrect(itemId) {
    const next = { item_hint: itemId };
    setAttempt(1);
    setFirstFile(null);
    setFirstItem(null);
    setAnswers(next);
    runJudge(next, null, file, true);
  }

  // 재촬영
  function handleRetake(countsAsAttempt) {
    if (countsAsAttempt) {
      setAttempt((prev) => prev + 1);
    }

    const checkedBox = (
      result?.judgement?.checklist ?? []
    ).some((item) => item.key === "checkbox");

    setAnswers((prev) => {
      const next = { ...prev };

      delete next.confirm_same_item;

      if (countsAsAttempt && checkedBox) {
        next.checkbox = "true";
      }

      return next;
    });

    setFile(null);
    setResult(null);
    setError("");
  }

  // 처음으로 돌아가기
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
    <main className="main-container">

      <section className={`workspace ${file ? "has-result" : ""}`}>

        {/* 사진 영역: 업로드 전후에도 같은 창을 유지 */}
        <div className={`upload-area upload-card ${file ? "photo-card" : ""}`}>

          <div className="brand">
            <span className="brand-icon">🌱</span>
            <span>RE:SCAN</span>
          </div>

          <div className="upload-title">
            <h2>오늘도 올바르게 🌿</h2>
            <p>
              {file
                ? "분리배출 결과를 확인해 보세요!"
                : "버릴 준비가 되었나요?"}
            </p>
          </div>

          {isMock && showMockTest && (
              <div className="mock-test">
                <select
                  value={mockStatus}
                  onChange={(e) => setMockStatus(e.target.value)}
                >
                  {MOCK_STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </div>
            )}


        {/* 사진 업로드 전 */}
        {!file && (
          <div className="upload-placeholder">
            <span className="camera-icon material-symbols-outlined">
              photo_camera
            </span>
            <p>사진을 업로드 해 주세요</p>
          </div>
        )}

        {/* 사진 미리보기 */}
        {file && preview && (
          <div className="preview">
            <img src={preview} alt="업로드한 사진" />
          </div>
        )}

        <label className={`upload-button ${file ? "retake-button" : ""}`}>
          {file ? "다시 촬영하기" : (
            <>
              <span className="upload-icon material-symbols-outlined">
                upload
              </span>
              사진 업로드하기
            </>
          )}

          <input
            type="file"
            accept="image/*"
            capture="environment"
            onChange={handleFileChange}
          />
        </label>

        {/* 갤러리에 있는 사진으로 판정 (capture가 없으면 폰에서 사진 보관함을 고를 수 있음) */}
        <label className="upload-button gallery-button">
          <span className="upload-icon material-symbols-outlined">
            photo_library
          </span>
          갤러리에서 고르기
          <input
            type="file"
            accept="image/*"
            onChange={handleFileChange}
          />
        </label>

          {!file && error && (
            <p className="error">{error}</p>
          )}

        </div>

        {/* 사진 업로드 후 오른쪽에 나타나는 AI 결과 */}
        {file && (
          <div className="judgement-panel">

            {/* AI 판정 중: 서버가 잠들어 있으면 첫 판정은 30초 이상 걸릴 수 있음 */}
            {loading && !result && (
              <div className="loading-card">
                <div className="spinner" />
                <p>AI가 사진을 확인하고 있어요...</p>
                <p className="loading-sub">처음 판정은 조금 오래 걸릴 수 있어요.</p>
              </div>
            )}

            <JudgeResult
              key={`${attempt}-${result?.judgement?.status}`}
              result={result}
              loading={loading}
              onRetake={handleRetake}
              onAnswer={handleAnswer}
              onRestart={handleRestart}
              onCorrect={handleCorrect}
            />

            {error && (
              <p className="error">{error}</p>
            )}
          </div>
        )}

      </section>

    </main>
  </div>
);
}

export default App;
