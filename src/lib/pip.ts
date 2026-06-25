// PiP(Picture-in-Picture) 유틸 — 표준 API + iOS Safari webkit 폴백.
// standalone PWA Chrome 등 양쪽 다 안 되면 버튼 숨김 처리.

/* eslint-disable @typescript-eslint/no-explicit-any */

export function isPipSupported(video: HTMLVideoElement | null): boolean {
  if (!video) return false
  if (typeof document !== "undefined" && document.pictureInPictureEnabled) return true
  if (typeof (video as any).webkitSupportsPresentationMode === "function") {
    return (video as any).webkitSupportsPresentationMode("picture-in-picture")
  }
  return false
}

export async function togglePip(video: HTMLVideoElement): Promise<void> {
  try {
    if (document.pictureInPictureElement) {
      await document.exitPictureInPicture()
    } else if (document.pictureInPictureEnabled) {
      await video.requestPictureInPicture()
    } else if (
      typeof (video as any).webkitSupportsPresentationMode === "function" &&
      (video as any).webkitSupportsPresentationMode("picture-in-picture")
    ) {
      ;(video as any).webkitSetPresentationMode(
        (video as any).webkitPresentationMode === "picture-in-picture"
          ? "inline"
          : "picture-in-picture",
      )
    }
  } catch {
    /* 미지원/제스처 문제 → 무시 */
  }
}
