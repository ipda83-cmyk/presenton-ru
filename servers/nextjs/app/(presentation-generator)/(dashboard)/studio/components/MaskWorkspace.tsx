"use client";

import { useEffect, useState, type RefObject } from "react";
import { Brush, Download, Eraser, Eye, EyeOff, ImageUp, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { MaskCanvas, type BrushTool, type MaskCanvasHandle } from "@/components/studio/MaskCanvas";
import ImageDropZone from "./ImageDropZone";
import { BusyOverlay, imageSrc } from "./controls";

const toolButton =
  "inline-flex min-h-[34px] items-center gap-1.5 rounded-full border px-3 font-syne text-[13px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7A5AF8] disabled:cursor-not-allowed disabled:opacity-50";
const idle = "border-[#EDEEEF] bg-white font-medium text-[#2C2B37] hover:border-[#CEC6FF]";
const active = "border-[#CEC6FF] bg-[#F4F3FF] font-semibold text-[#5141E5]";

// The photo with the brush mask, its toolbar and the before/after switch;
// shared by the Magic brush and Reference pages.
export default function MaskWorkspace({
  image,
  before,
  canvasRef,
  busy,
  busyLabel,
  dropTitle,
  dropHint,
  onFile,
  onClear,
}: {
  image: string | null;
  before: string | null;
  canvasRef: RefObject<MaskCanvasHandle | null>;
  busy: boolean;
  busyLabel: string;
  dropTitle: string;
  dropHint: string;
  onFile: (file: File | undefined) => void;
  onClear: () => void;
}) {
  const t = useTranslations("studio.canvas");
  const [tool, setTool] = useState<BrushTool>("brush");
  const [size, setSize] = useState(48);
  const [showMask, setShowMask] = useState(true);
  const [showBefore, setShowBefore] = useState(false);
  const [broken, setBroken] = useState(false);

  useEffect(() => {
    setShowBefore(false);
    setBroken(false);
  }, [image]);

  if (!image) {
    return (
      <div className="flex min-h-[420px] items-center justify-center rounded-2xl border border-[#EDEEEF] bg-[#F9F8FB] p-6 lg:min-h-[520px]">
        <div className="w-full max-w-xl">
          <ImageDropZone title={dropTitle} hint={dropHint} onFile={onFile} />
        </div>
      </div>
    );
  }

  const comparing = showBefore && !!before;

  return (
    <div className="flex flex-col gap-3.5">
      <div
        role="toolbar"
        aria-label={t("toolbar")}
        className="flex flex-wrap items-center gap-2 self-start rounded-[24px] border border-[#EDEEEF] bg-[#F6F6F9] px-3 py-2"
      >
        <button type="button" aria-pressed={tool === "brush"} onClick={() => setTool("brush")} className={`${toolButton} ${tool === "brush" ? active : idle}`}>
          <Brush className="h-3.5 w-3.5" aria-hidden="true" />
          {t("brush")}
        </button>
        <button type="button" aria-pressed={tool === "eraser"} onClick={() => setTool("eraser")} className={`${toolButton} ${tool === "eraser" ? active : idle}`}>
          <Eraser className="h-3.5 w-3.5" aria-hidden="true" />
          {t("eraser")}
        </button>
        <label htmlFor="studio-brush-size" className="ml-1 font-syne text-[13px] text-[#475467]">
          {t("size")}
        </label>
        <input
          id="studio-brush-size"
          type="range"
          min={8}
          max={160}
          value={size}
          onChange={(event) => setSize(Number(event.target.value))}
          className="w-28 accent-[#7A5AF8]"
        />
        <button type="button" onClick={() => canvasRef.current?.clearMask()} className={`${toolButton} ${idle}`}>
          {t("clear")}
        </button>
        <button type="button" aria-pressed={showMask} onClick={() => setShowMask((value) => !value)} className={`${toolButton} ${idle}`}>
          {showMask ? <EyeOff className="h-3.5 w-3.5" aria-hidden="true" /> : <Eye className="h-3.5 w-3.5" aria-hidden="true" />}
          {showMask ? t("hideMask") : t("showMask")}
        </button>
        {before && before !== image && (
          <div role="group" aria-label={t("compare")} className="inline-flex overflow-hidden rounded-full border border-[#EDEEEF] bg-white">
            <button type="button" aria-pressed={comparing} onClick={() => setShowBefore(true)} className={`px-3 py-1.5 font-syne text-[13px] ${comparing ? "bg-[#F4F3FF] font-semibold text-[#5141E5]" : "text-[#2C2B37]"}`}>
              {t("before")}
            </button>
            <button type="button" aria-pressed={!comparing} onClick={() => setShowBefore(false)} className={`px-3 py-1.5 font-syne text-[13px] ${!comparing ? "bg-[#F4F3FF] font-semibold text-[#5141E5]" : "text-[#2C2B37]"}`}>
              {t("after")}
            </button>
          </div>
        )}
      </div>

      <div className="relative flex min-h-[420px] items-center justify-center overflow-hidden rounded-2xl border border-[#EDEEEF] bg-[#F9F8FB] p-4 lg:min-h-[520px]">
        {broken ? (
          <p role="alert" className="text-sm text-red-700">
            {t("loadFailed")}
          </p>
        ) : (
          <div className={comparing ? "hidden" : "contents"}>
            <MaskCanvas
              ref={canvasRef}
              src={imageSrc(image)}
              brushSize={size}
              showMask={showMask}
              tool={tool}
              label={t("canvasLabel")}
              onError={() => setBroken(true)}
            />
          </div>
        )}
        {comparing && before && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={imageSrc(before)} alt={t("before")} className="max-h-[70vh] max-w-full rounded-xl object-contain" />
        )}
        <BusyOverlay active={busy} label={busyLabel} />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <a href={imageSrc(image)} download className={`${toolButton} ${idle}`}>
          <Download className="h-3.5 w-3.5" aria-hidden="true" />
          {t("download")}
        </a>
        <label className={`${toolButton} ${idle} cursor-pointer focus-within:ring-2 focus-within:ring-[#7A5AF8]`}>
          <ImageUp className="h-3.5 w-3.5" aria-hidden="true" />
          {t("replace")}
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="sr-only"
            onChange={(event) => {
              onFile(event.target.files?.[0]);
              event.target.value = "";
            }}
          />
        </label>
        <button type="button" onClick={onClear} disabled={busy} className={`${toolButton} ${idle} hover:text-red-600`}>
          <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
          {t("remove")}
        </button>
      </div>
    </div>
  );
}
