
import { useState, useEffect } from "react";
import JudgeResult from "./components/JudgeResult";
import { judgeImage } from "./services/judgeApi";
import "./App.css";

function App() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);

  const [attempt, setAttempt] = useState(1);
  const [result, setResult] = useState(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Mock 테스트용 상태 선택
  const [mockStatus, setMockStatus] = useState("pass");

  // 사진 미리보기 URL 관리
  useEffect(() => {
    if (!file) {
      setPreview(null);
      return;
    }

    const imageUrl = URL.createObjectURL(file);
    setPreview(imageUrl);

    return () => URL.revokeObjectURL(imageUrl);
  }, [file]);

  // 사진 선택
  function handleFileChange(event) {
    const selectedFile = event.target.files[0];

    if (!selectedFile) return;

    if (!selectedFile.type.startsWith("image/")) {
      setError("이미지 파일만 선택할 수 있습니다.");
      return;
    }

    setFile(selectedFile);
    setResult(null);
    setError("");

    // 같은 파일을 다시 선택할 수 있도록 초기화
    event.target.value = "";
  }

  // 판정 요청
  async function handleJudge() {
    if (!file) {
      setError("먼저 사진을 선택해 주세요.");
      return;
    }

    try {
      setLoading(true);
      setError("");

      const data = await judgeImage(
        file,
        attempt,
        mockStatus
      );

      setResult(data);
    } catch (err) {
      setError(err.message || "오류가 발생했습니다.");
    } finally {
      setLoading(false);
    }
  }

  // 재촬영
  function handleRetake() {
    if (attempt >= 3) return;

    setAttempt((prev) => prev + 1);
    setFile(null);
    setPreview(null);
    setResult(null);
    setError("");
  }

  return (
    <div className="app">
      <h1>AI 분리배출 판정</h1>

      <p>재활용품 사진을 업로드해 주세요.</p>

      <div className="upload-area">
        <input
          type="file"
          accept="image/*"
          onChange={handleFileChange}
        />

        {preview && (
          <div className="preview">
            <img src={preview} alt="업로드한 사진" />
          </div>
        )}
      </div>

      <p>촬영 횟수: {attempt} / 3</p>

      <button
        onClick={handleJudge}
        disabled={!file || loading}
      >
        {loading ? "판정 중..." : "판정하기"}
      </button>

      {error && <p className="error">{error}</p>}

      {/* Mock 테스트용 */}
      <div className="mock-test">
        <h3>판정 결과 테스트</h3>

        <select
          value={mockStatus}
          onChange={(event) => setMockStatus(event.target.value)}
        >
          <option value="pass">pass</option>
          <option value="need_action">need_action</option>
          <option value="retake">retake</option>
          <option value="question">question</option>
          <option value="fallback">fallback</option>
          <option value="unsupported">unsupported</option>
        </select>

        <p>선택한 Mock 응답: {mockStatus}</p>
      </div>

      <JudgeResult
        result={result}
        onRetake={handleRetake}
        attempt={attempt}
      />
    </div>
  );
}

export default App;
