"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { useTranslations } from "next-intl";
import { markOnboarding, useOnboarding } from "./useOnboarding";

// Elements are found by data-tour; a missing one (no templates in this mode,
// no billing) is skipped.
const STEPS = ["create", "templates", "studio", "balance", "help"] as const;
const DESKTOP = 768;
const GAP = 14;
const BUBBLE = 320;

type Box = { top: number; left: number; width: number; height: number };

function visible(id: string): HTMLElement | null {
  const element = document.querySelector<HTMLElement>(`[data-tour="${id}"]`);
  if (!element) return null;
  const rect = element.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0 ? element : null;
}

/** A few hints over the dashboard, one element at a time. */
export default function Tour() {
  const t = useTranslations("onboarding.tour");
  const onboarding = useOnboarding();
  const [steps, setSteps] = useState<string[]>([]);
  const [index, setIndex] = useState(0);
  const [box, setBox] = useState<Box | null>(null);
  const [closed, setClosed] = useState(false);
  const bubbleRef = useRef<HTMLDivElement>(null);
  const active = Boolean(onboarding?.show.tour && !onboarding.show.welcome) && !closed;

  useEffect(() => {
    if (!active) return;
    // The page and the sidebar render first; the tour is for wide screens.
    const timer = window.setTimeout(() => {
      if (window.innerWidth < DESKTOP) return;
      setSteps(STEPS.filter((id) => visible(id)));
    }, 600);
    return () => window.clearTimeout(timer);
  }, [active]);

  const step = steps[index];

  const measure = useCallback(() => {
    const element = step ? visible(step) : null;
    if (!element) return setBox(null);
    const rect = element.getBoundingClientRect();
    setBox({ top: rect.top, left: rect.left, width: rect.width, height: rect.height });
  }, [step]);

  useLayoutEffect(() => {
    if (!step) return;
    visible(step)?.scrollIntoView({ block: "nearest" });
    measure();
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [measure, step]);

  useEffect(() => {
    if (box) bubbleRef.current?.focus();
  }, [box, index]);

  const close = useCallback(() => {
    setClosed(true);
    void markOnboarding("tour");
  }, []);

  useEffect(() => {
    if (!active || !steps.length) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
      if (event.key === "ArrowRight") setIndex((value) => Math.min(value + 1, steps.length - 1));
      if (event.key === "ArrowLeft") setIndex((value) => Math.max(value - 1, 0));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, close, steps.length]);

  const place = useMemo(() => {
    if (!box) return null;
    const right = box.left + box.width + GAP;
    if (right + BUBBLE < window.innerWidth - 16) {
      return { top: Math.max(16, Math.min(box.top, window.innerHeight - 220)), left: right, side: "right" as const };
    }
    return {
      top: Math.min(box.top + box.height + GAP, window.innerHeight - 220),
      left: Math.max(16, Math.min(box.left, window.innerWidth - BUBBLE - 16)),
      side: "below" as const,
    };
  }, [box]);

  if (!active || !step || !box || !place) return null;
  const last = index === steps.length - 1;

  return createPortal(
    <div className="fixed inset-0 z-[70]" aria-live="polite">
      <div className="absolute inset-0" onClick={close} aria-hidden="true" />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute rounded-xl outline outline-2 outline-[#03B015] transition-all duration-200 motion-reduce:transition-none"
        style={{
          top: box.top - 6,
          left: box.left - 6,
          width: box.width + 12,
          height: box.height + 12,
          boxShadow: "0 0 0 9999px rgba(16, 24, 40, 0.5)",
        }}
      />
      <div
        ref={bubbleRef}
        role="dialog"
        aria-label={t(`${step}.title`)}
        tabIndex={-1}
        className="absolute flex flex-col gap-2 rounded-xl bg-white p-4 font-syne shadow-[0_12px_36px_rgba(16,24,40,0.25)] outline-none"
        style={{ top: place.top, left: place.left, width: BUBBLE }}
      >
        <div className="flex items-start justify-between gap-3">
          <p className="text-sm font-semibold text-[#101323]">{t(`${step}.title`)}</p>
          <button type="button" onClick={close} aria-label={t("close")} className="-m-1 rounded p-1 text-[#667085] hover:text-[#101323]">
            <X className="h-4 w-4" />
          </button>
        </div>
        <p className="text-xs leading-5 text-[#475467]">{t(`${step}.text`)}</p>
        <div className="mt-1 flex items-center justify-between gap-3">
          <span className="text-[11px] text-[#98A2B3]" style={{ fontVariantNumeric: "tabular-nums" }}>
            {t("progress", { step: index + 1, total: steps.length })}
          </span>
          <div className="flex gap-2">
            {index > 0 ? (
              <button type="button" onClick={() => setIndex(index - 1)} className="h-8 rounded-full px-3 text-xs font-semibold text-[#667085] hover:text-[#101323]">
                {t("back")}
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => (last ? close() : setIndex(index + 1))}
              className="h-8 rounded-full bg-[#03B015] px-4 text-xs font-semibold text-white hover:bg-[#02940F]"
            >
              {last ? t("done") : t("next")}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
