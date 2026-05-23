"use client"

import { Dialog } from "radix-ui"
import { X } from "lucide-react"

// 캐릭터 이미지 확대 라이트박스.
// Esc 키 / 바깥 영역 클릭은 Radix Dialog가 기본 처리하고,
// 우상단 X 버튼으로도 닫는다. components/ui/* 는 건드리지 않고
// 기존 디자인 토큰만 사용한다.
export function ImageLightbox({
  src,
  alt,
  onClose,
}: {
  src: string | null
  alt?: string
  onClose: () => void
}) {
  return (
    <Dialog.Root
      open={!!src}
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex max-h-[92vh] max-w-[92vw] -translate-x-1/2 -translate-y-1/2 items-center justify-center outline-none">
          <Dialog.Title className="sr-only">{alt ?? "캐릭터 이미지"}</Dialog.Title>
          <Dialog.Description className="sr-only">
            확대된 캐릭터 이미지입니다. Esc 키나 바깥 영역 클릭으로 닫을 수 있어요.
          </Dialog.Description>
          {src && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={src}
              alt={alt ?? ""}
              className="max-h-[92vh] max-w-[92vw] rounded-xl object-contain shadow-2xl"
            />
          )}
          <Dialog.Close
            aria-label="닫기"
            className="absolute -right-3 -top-3 flex h-9 w-9 items-center justify-center rounded-full bg-card text-foreground shadow-md ring-1 ring-border transition-colors hover:bg-secondary focus:outline-none focus:ring-2 focus:ring-primary/40"
          >
            <X className="h-4 w-4" />
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
