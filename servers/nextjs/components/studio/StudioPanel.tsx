"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { Brush, Eraser, Loader2, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { withPrice } from "@/components/studio/price";
import StudioMark from "@/components/studio/StudioMark";
import { MaskCanvas, type BrushTool, type MaskCanvasHandle } from "@/components/studio/MaskCanvas";
import {
  BusyOverlay,
  ChipGroup,
  ErrorBox,
  GradientButton,
  ModelSelect,
  SoftButton,
  errorMessage,
  imageSrc,
} from "@/components/studio/controls";
import {
  StudioApi,
  type StudioConfig,
  type StudioOperation,
} from "@/app/(presentation-generator)/services/api/studio";

export type StudioPanelItem = {
  id: string;
  name: string;
  /** data:, blob: or /app_data/... URL of the picture as it is now. */
  src: string;
};

type Mode = "describe" | "brush" | StudioOperation;
const MODES: Mode[] = ["describe", "brush", "upscale", "remove_bg"];

type ItemState = {
  /** The picture the item started from in this session. */
  original: string;
  /** Results of "Apply", oldest first; the last one is shown. */
  results: string[];
};

let configCache: Promise<StudioConfig> | null = null;
const loadConfig = () => {
  configCache = configCache ?? StudioApi.config().catch((error) => {
    configCache = null;
    throw error;
  });
  return configCache;
};

/** Whether the Studio has an arckep key (buttons that open it stay hidden otherwise). */
export function useStudioAvailable(enabled = true): boolean {
  const [available, setAvailable] = useState(false);
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    loadConfig()
      .then((config) => alive && setAvailable(config.configured))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [enabled]);
  return available;
}

/** /studio/edit takes app_data paths and data URLs; blob: URLs are read first. */
async function sendable(src: string): Promise<string> {
  if (!src.startsWith("blob:")) return src;
  const blob = await (await fetch(src)).blob();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

/**
 * AI Image Studio beside a page (create page, slide editor): a strip of the
 * pictures, edit modes, and a button that hands the result back to the page.
 */
export default function StudioPanel({
  open,
  items,
  activeId,
  onActiveChange,
  onClose,
  onAdd,
  addLabel,
  addedNotice,
  isAdmin = false,
}: {
  open: boolean;
  items: StudioPanelItem[];
  activeId: string | null;
  onActiveChange: (id: string) => void;
  onClose: () => void;
  /** Hand the edited picture (an app_data path) back to the page. */
  onAdd: (item: StudioPanelItem, image: string) => Promise<void> | void;
  addLabel: string;
  /** Shown after the page took the picture. */
  addedNotice?: string;
  isAdmin?: boolean;
}) {
  const t = useTranslations("studioPanel");
  const ts = useTranslations("studio");
  const panelRef = useRef<HTMLElement>(null);
  const canvasRef = useRef<MaskCanvasHandle>(null);
  const [config, setConfig] = useState<StudioConfig | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [states, setStates] = useState<Record<string, ItemState>>({});
  const [mode, setMode] = useState<Mode>("describe");
  const [prompt, setPrompt] = useState("");
  const [modelKey, setModelKey] = useState("");
  const [resolution, setResolution] = useState("1K");
  const [tool, setTool] = useState<BrushTool>("brush");
  const [brushSize, setBrushSize] = useState(40);
  const [showOriginal, setShowOriginal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const index = Math.max(0, items.findIndex((item) => item.id === activeId));
  const item = items[index] ?? null;

  useEffect(() => {
    if (!open || config) return;
    loadConfig()
      .then((value) => {
        setConfig(value);
        setModelKey((current) => current || value.default_model);
      })
      .catch((reason: Error) => setConfigError(reason.message));
  }, [open, config]);

  // A picture replaced by the page (e.g. after "Add") starts a fresh history.
  useEffect(() => {
    setStates((current) => {
      const next: Record<string, ItemState> = {};
      let changed = Object.keys(current).length !== items.length;
      for (const entry of items) {
        const state = current[entry.id];
        next[entry.id] = state && state.original === entry.src ? state : { original: entry.src, results: [] };
        changed = changed || next[entry.id] !== state;
      }
      return changed ? next : current;
    });
  }, [items]);

  useEffect(() => {
    setShowOriginal(false);
    setError(null);
    setNotice(null);
  }, [activeId]);

  useEffect(() => {
    if (open) panelRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy, onClose]);

  const models = useMemo(() => config?.models ?? [], [config]);
  const model = models.find((entry) => entry.key === modelKey) ?? models[0];
  const operationModel = model?.family === "gemini" ? model : models.find((entry) => entry.family === "gemini");
  const state = item ? states[item.id] : undefined;
  const current = state ? state.results.at(-1) ?? state.original : item?.src ?? "";
  const edited = !!state?.results.length;
  const shown = showOriginal && state ? state.original : current;

  const apply = useCallback(async () => {
    if (!item || !model) return;
    const isOperation = mode === "upscale" || mode === "remove_bg";
    if (!isOperation && !prompt.trim()) {
      setError(mode === "brush" ? ts("errors.brushPromptRequired") : t("promptRequired"));
      return;
    }
    let mask: string | undefined;
    if (mode === "brush") {
      mask = canvasRef.current?.exportMask() ?? undefined;
      if (!mask) {
        setError(ts("errors.maskRequired"));
        return;
      }
    }
    const useModel = isOperation ? operationModel : model;
    if (!useModel) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await StudioApi.edit({
        image: await sendable(current),
        model: useModel.key,
        ...(isOperation
          ? {
              operation: mode as StudioOperation,
              ...(useModel.resolutions.includes(resolution) ? { resolution } : {}),
            }
          : { prompt: prompt.trim(), ...(mask ? { mask } : {}) }),
      });
      setStates((all) => {
        const entry = all[item.id] ?? { original: item.src, results: [] };
        return { ...all, [item.id]: { ...entry, results: [...entry.results, result.file_url] } };
      });
      setShowOriginal(false);
      canvasRef.current?.clearMask();
    } catch (reason) {
      setError(errorMessage(reason, ts("errors.requestFailed")));
    } finally {
      setBusy(false);
    }
  }, [current, item, mode, model, operationModel, prompt, resolution, t, ts]);

  const add = useCallback(async () => {
    if (!item || !edited) return;
    setAdding(true);
    setError(null);
    try {
      await onAdd(item, current);
      setNotice(addedNotice ?? t("added"));
    } catch (reason) {
      setError(errorMessage(reason, t("addFailed")));
    } finally {
      setAdding(false);
    }
  }, [addedNotice, current, edited, item, onAdd, t]);

  if (!open || typeof document === "undefined") return null;

  const notConfigured = !!configError || (config !== null && !config.configured);

  // Portal: pages like the slide editor scale their content with transforms.
  return createPortal(
    <aside
      ref={panelRef}
      tabIndex={-1}
      role="dialog"
      aria-modal="false"
      aria-labelledby="studio-panel-title"
      // The slide editor keeps the picture selected while the panel is used.
      data-inline-edit-ignore="true"
      className="fixed inset-y-0 right-0 z-[10010] flex w-full flex-col border-l border-[#EDEEEF] bg-white font-syne shadow-[-18px_0_40px_rgba(16,24,40,0.08)] outline-none sm:w-[480px]"
    >
      <div className="flex items-center justify-between gap-3 border-b border-[#EDEEEF] px-5 py-4">
        <div className="flex min-w-0 items-center gap-2.5">
          <StudioMark size={32} />
          <div className="min-w-0">
            <h2 id="studio-panel-title" className="text-base font-semibold text-[#101323]">
              AI Image Studio
            </h2>
            {item && (
              <p className="truncate text-xs text-[#667085]">
                {t("position", { number: index + 1, total: items.length, name: item.name })}
              </p>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          disabled={busy}
          aria-label={t("close")}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-[#EDEEEF] text-[#2C2B35] transition-colors hover:bg-[#F6F6F9] disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7A5AF8]"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      {notConfigured ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 px-8 text-center">
          <StudioMark size={44} />
          <p className="text-sm leading-6 text-[#475467]">
            {configError ?? (isAdmin ? ts("notConfigured.admin") : ts("notConfigured.user"))}
          </p>
          {isAdmin && !configError && (
            <Link href="/settings?section=studio" className="text-sm font-semibold text-[#5146E5] hover:text-[#3B2FC9]">
              {ts("notConfigured.openSettings")}
            </Link>
          )}
        </div>
      ) : !item || !config ? (
        <div className="flex flex-1 items-center justify-center text-sm text-[#667085]">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
          {ts("loading")}
        </div>
      ) : (
        <>
          <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-5 py-4">
            <div className="relative flex min-h-[220px] items-center justify-center overflow-hidden rounded-[14px] bg-[#F6F6F9] p-2">
              {mode === "brush" && !showOriginal ? (
                <MaskCanvas
                  ref={canvasRef}
                  src={imageSrc(current)}
                  brushSize={brushSize}
                  showMask
                  tool={tool}
                  label={ts("canvas.canvasLabel")}
                />
              ) : (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={imageSrc(shown)} alt={item.name} className="max-h-[42vh] max-w-full rounded-lg object-contain" />
              )}
              <BusyOverlay active={busy} label={t("working")} />
            </div>

            {(edited || mode === "brush") && (
              <div className="flex flex-wrap items-center gap-2">
                {mode === "brush" && !showOriginal && (
                  <>
                    <button
                      type="button"
                      aria-pressed={tool === "brush"}
                      onClick={() => setTool("brush")}
                      aria-label={ts("canvas.brush")}
                      className={`flex h-9 w-9 items-center justify-center rounded-full border ${tool === "brush" ? "border-[#CEC6FF] bg-[#F4F3FF] text-[#5141E5]" : "border-[#EDEEEF] text-[#2C2B37]"}`}
                    >
                      <Brush className="h-4 w-4" aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      aria-pressed={tool === "eraser"}
                      onClick={() => setTool("eraser")}
                      aria-label={ts("canvas.eraser")}
                      className={`flex h-9 w-9 items-center justify-center rounded-full border ${tool === "eraser" ? "border-[#CEC6FF] bg-[#F4F3FF] text-[#5141E5]" : "border-[#EDEEEF] text-[#2C2B37]"}`}
                    >
                      <Eraser className="h-4 w-4" aria-hidden="true" />
                    </button>
                    <label htmlFor="studio-panel-brush" className="sr-only">
                      {ts("canvas.size")}
                    </label>
                    <input
                      id="studio-panel-brush"
                      type="range"
                      min={8}
                      max={160}
                      value={brushSize}
                      onChange={(event) => setBrushSize(Number(event.target.value))}
                      className="w-24 accent-[#7A5AF8]"
                    />
                    <button
                      type="button"
                      onClick={() => canvasRef.current?.clearMask()}
                      className="min-h-9 rounded-full border border-[#EDEEEF] px-3 text-[13px] text-[#2C2B37] hover:border-[#CEC6FF]"
                    >
                      {ts("canvas.clear")}
                    </button>
                  </>
                )}
                {edited && (
                  <div role="group" aria-label={ts("canvas.compare")} className="ml-auto inline-flex overflow-hidden rounded-full border border-[#EDEEEF]">
                    <button
                      type="button"
                      aria-pressed={showOriginal}
                      onClick={() => setShowOriginal(true)}
                      className={`px-3 py-1.5 text-[13px] ${showOriginal ? "bg-[#F4F3FF] font-semibold text-[#5141E5]" : "text-[#2C2B37]"}`}
                    >
                      {ts("canvas.before")}
                    </button>
                    <button
                      type="button"
                      aria-pressed={!showOriginal}
                      onClick={() => setShowOriginal(false)}
                      className={`px-3 py-1.5 text-[13px] ${!showOriginal ? "bg-[#F4F3FF] font-semibold text-[#5141E5]" : "text-[#2C2B37]"}`}
                    >
                      {ts("canvas.after")}
                    </button>
                  </div>
                )}
              </div>
            )}

            {items.length > 1 && (
              <div role="group" aria-label={t("strip")} className="flex gap-2.5 overflow-x-auto pb-1">
                {items.map((entry, position) => {
                  const entryState = states[entry.id];
                  const thumb = entryState ? entryState.results.at(-1) ?? entryState.original : entry.src;
                  return (
                    <button
                      key={entry.id}
                      type="button"
                      aria-pressed={entry.id === item.id}
                      aria-label={t("photo", { number: position + 1, name: entry.name })}
                      onClick={() => onActiveChange(entry.id)}
                      disabled={busy}
                      className={`relative h-[54px] w-[74px] shrink-0 overflow-hidden rounded-[10px] border-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7A5AF8] ${entry.id === item.id ? "border-[#7A5AF8]" : "border-transparent"}`}
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={imageSrc(thumb)} alt="" className="h-full w-full object-cover" />
                      {entryState?.results.length ? (
                        <span className="absolute right-1 top-1 h-2.5 w-2.5 rounded-full border border-white bg-[#7A5AF8]" aria-hidden="true" />
                      ) : null}
                    </button>
                  );
                })}
              </div>
            )}

            <div role="group" aria-label={t("modes")} className="flex flex-wrap gap-1.5 rounded-[24px] bg-[#F6F6F9] p-1">
              {MODES.map((value) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={mode === value}
                  onClick={() => {
                    setMode(value);
                    setError(null);
                  }}
                  disabled={busy}
                  className={`min-h-[34px] rounded-full px-3 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7A5AF8] ${mode === value ? "bg-white font-semibold text-[#5141E5] shadow-[0_1px_3px_rgba(16,24,40,0.08)]" : "font-medium text-[#475467]"}`}
                >
                  {t(`mode.${value}`)}
                </button>
              ))}
            </div>

            {mode === "describe" || mode === "brush" ? (
              <>
                <div className="rounded-[14px] bg-[#ECE8F6] px-4 py-3.5">
                  <label htmlFor="studio-panel-prompt" className="block text-[13px] font-semibold text-[#1F1D2A]">
                    {mode === "brush" ? ts("brush.promptLabel") : t("promptLabel")}
                  </label>
                  <textarea
                    id="studio-panel-prompt"
                    rows={2}
                    maxLength={4000}
                    value={prompt}
                    onChange={(event) => setPrompt(event.target.value)}
                    placeholder={mode === "brush" ? ts("brush.placeholder") : t("placeholder")}
                    className="mt-1.5 w-full resize-y border-0 bg-transparent text-sm leading-[1.4] text-[#242430] outline-none placeholder:text-[#8A8798]"
                  />
                </div>
                {model && <ModelSelect id="studio-panel-model" models={models} value={model.key} onChange={setModelKey} />}
                {mode === "brush" && <p className="text-xs leading-5 text-[#667085]">{t("brushHint")}</p>}
              </>
            ) : (
              <>
                <p className="text-sm leading-6 text-[#475467]">{t(`about.${mode}`)}</p>
                {operationModel && operationModel.resolutions.length > 1 && (
                  <ChipGroup
                    label={ts("fields.resultSize")}
                    options={operationModel.resolutions}
                    value={resolution}
                    onChange={setResolution}
                  />
                )}
              </>
            )}

            <ErrorBox error={error} />
            {notice && (
              <p role="status" className="rounded-xl border border-[#D1FADF] bg-[#ECFDF3] px-3 py-2.5 text-sm text-[#05603A]">
                {notice}
              </p>
            )}
          </div>

          <div className="flex gap-2.5 border-t border-[#EDEEEF] px-5 pb-5 pt-4">
            <div className="flex-1 [&>button]:w-full [&>button]:rounded-[48px]">
              <SoftButton busy={busy} disabled={adding} onClick={apply}>
                {withPrice(t("apply"), config, mode === "upscale" || mode === "remove_bg" ? operationModel : model, {
                  resolution: mode === "upscale" || mode === "remove_bg" ? resolution : undefined,
                })}
              </SoftButton>
            </div>
            <div className="flex-[1.4]">
              <GradientButton busy={adding} disabled={!edited || busy} onClick={add}>
                {addLabel}
              </GradientButton>
            </div>
          </div>
        </>
      )}
    </aside>,
    document.body,
  );
}
