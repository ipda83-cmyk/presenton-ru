"use client";

import { useEffect, useRef, useState } from "react";
import { ImageUp } from "lucide-react";
import { useTranslations } from "next-intl";
import { MAX_UPLOAD_BYTES, readImageFile } from "@/components/studio/controls";

/** Validates and reads a picked/dropped/pasted file; reports problems as text. */
export function useImageFile(onImage: (dataUrl: string) => void, onError: (message: string) => void) {
  const t = useTranslations("studio.upload");
  return async (file: File | null | undefined) => {
    if (!file) return;
    if (!file.type.startsWith("image/")) return onError(t("notImage"));
    if (file.size > MAX_UPLOAD_BYTES) return onError(t("tooLarge", { mb: MAX_UPLOAD_BYTES / 1024 / 1024 }));
    try {
      onImage(await readImageFile(file));
    } catch {
      onError(t("readFailed"));
    }
  };
}

/** Ctrl+V of an image anywhere on the page (skipped while typing in a field). */
export function usePastedImage(handle: (file: File) => void, enabled = true) {
  const handler = useRef(handle);
  handler.current = handle;
  useEffect(() => {
    if (!enabled) return;
    const onPaste = (event: ClipboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, [contenteditable='true']")) return;
      const item = Array.from(event.clipboardData?.items ?? []).find((entry) => entry.type.startsWith("image/"));
      const file = item?.getAsFile();
      if (file) {
        event.preventDefault();
        handler.current(file);
      }
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [enabled]);
}

export default function ImageDropZone({
  title,
  hint,
  onFile,
  compact = false,
}: {
  title: string;
  hint: string;
  onFile: (file: File | undefined) => void;
  compact?: boolean;
}) {
  const t = useTranslations("studio.upload");
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        onFile(event.dataTransfer.files?.[0]);
      }}
      className={[
        "flex w-full flex-col items-center justify-center rounded-2xl border-2 border-dashed text-center transition-colors",
        compact ? "gap-1.5 px-4 py-5" : "gap-3 px-8 py-14",
        dragging ? "border-[#7A5AF8] bg-[#F4F3FF]" : "border-[#DBDBE1] bg-white",
      ].join(" ")}
    >
      {!compact && <ImageUp className="h-9 w-9 text-[#7A5AF8]" aria-hidden="true" />}
      <p className={`font-syne font-medium text-[#101323] ${compact ? "text-sm" : "text-base"}`}>{title}</p>
      <p className="text-[13px] text-[#667085]">{hint}</p>
      <button
        type="button"
        onClick={() => input.current?.click()}
        className="mt-1 inline-flex min-h-9 items-center rounded-full border border-[#CEC6FF] bg-[#F4F3FF] px-4 font-syne text-[13px] font-semibold text-[#5141E5] transition-colors hover:bg-[#ECE9FF] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7A5AF8]"
      >
        {t("choose")}
      </button>
      <input
        ref={input}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        className="hidden"
        onChange={(event) => {
          onFile(event.target.files?.[0]);
          event.target.value = "";
        }}
      />
    </div>
  );
}
