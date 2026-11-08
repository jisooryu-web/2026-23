
import responses from "./responses.json";

// true: Mock 데이터 사용
// false: 실제 백엔드 연결
const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";

// 백엔드 배포 후 실제 주소로 변경
const API_URL = import.meta.env.VITE_API_BASE_URL || "/api";

export async function judgeImage(image, attempt, mockStatus = "pass") {
  // 1. Mock 데이터 사용
  if (USE_MOCK) {
    console.log("Mock 판정 요청");
    console.log("촬영 횟수:", attempt);

    // 테스트를 위해 선택한 상태의 응답 반환
    return responses[mockStatus];
  }

  // 2. 실제 백엔드 연결
  const formData = new FormData();

  formData.append("image", image);
  formData.append("attempt", String(attempt));
  if (prevImage) formData.append("prev_image", prevImage);
  if (prevItem) formData.append("prev_item", prevItem);

  const response = await fetch(`${API_URL}/judge`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error("판정 요청에 실패했습니다.");
  }

  return await response.json();
}
