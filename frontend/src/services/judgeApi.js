import responses from "./responses.json";

// VITE_USE_MOCK=false 로 두면 실제 백엔드에 연결
const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";

// 개발 중: "/api" → vite.config.js 프록시가 http://127.0.0.1:5001 로 전달
// 배포 후: VITE_API_BASE_URL=https://백엔드주소
const API_URL = import.meta.env.VITE_API_BASE_URL || "/api";

export const isMock = USE_MOCK;

export async function judgeImage({ image, attempt, prevImage = null, prevItem = null, answers = {}, mockStatus = "pass" }) {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 400)); // 로딩 화면 확인용
    const mock = structuredClone(Object.keys(answers).length ? responses.pass : responses[mockStatus]);
    mock.judgement.attempt = attempt;
    return mock;
  }

  const formData = new FormData();
  formData.append("image", image);
  formData.append("attempt", String(attempt));
  if (prevImage) formData.append("prev_image", prevImage);
  if (prevItem) formData.append("prev_item", prevItem);
  if (Object.keys(answers).length) formData.append("answers", JSON.stringify(answers));

  let response;
  try {
    response = await fetch(`${API_URL}/judge`, { method: "POST", body: formData });
  } catch {
    throw new Error("서버에 연결할 수 없어요. 백엔드가 켜져 있는지 확인해 주세요.");
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    // 백엔드 오류 형식: {"error": {"code": "...", "message": "..."}}
    throw new Error(data?.error?.message || "판정 요청에 실패했어요.");
  }
  return data;
}
