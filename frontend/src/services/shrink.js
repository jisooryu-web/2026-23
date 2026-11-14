// 사진을 올리기 전에 긴 변 1024px JPEG로 줄인다.
// 서버도 어차피 1024px로 줄이므로 화질 손해는 없고, 업로드는 대략 10분의 1이 된다.
// 브라우저가 읽지 못하는 형식(예: Chrome의 HEIC)이면 원본을 그대로 돌려준다 → 서버가 처리.
export async function shrinkImage(file, maxSide = 1024) {
  try {
    // imageOrientation: 휴대폰 사진의 회전 정보(EXIF)를 반영해서 그린다
    const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
    return blob ? new File([blob], "photo.jpg", { type: "image/jpeg" }) : file;
  } catch {
    return file;
  }
}
