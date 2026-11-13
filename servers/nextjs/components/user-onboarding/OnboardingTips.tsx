"use client";

import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslations } from "next-intl";
import type { OnboardingTip } from "@/app/(presentation-generator)/services/api/onboarding";
import { markOnboarding, useOnboarding } from "./useOnboarding";

// One tip at a time, next to its element (data-onboarding="…"), on the
// first visit of the outline, the editor and the Studio brush.
const TIPS: OnboardingTip[] = ["outline-plan", "editor-export", "editor-ai", "studio-brush"];
const WIDTH = 260;
const LOOK_EVERY_MS = 1000;

type Place = { top: number; left: number; arrow: number; below: boolean };

function anchor(tip: OnboardingTip): HTMLElement | null {
  const element = document.querySelector<HTMLElement>(`[data-onboarding="${tip}"]`);
  if (!element) return null;
  const rect = element.getBoundingClientRect();
  const onScreen = rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.top < window.innerHeight;
  return onScreen ? element : null;
}

function placeFor(element: HTMLElement): Place {
  const rect = element.getBoundingClientRect();
  const centre = rect.left + rect.width / 2;
  const left = Math.max(12, Math.min(centre - WIDTH / 2, window.innerWidth - WIDTH - 12));
  const below = rect.bottom + 160 < window.innerHeight || rect.top < 180;
  const top = below ? Math.min(rect.bottom + 12, window.innerHeight - 150) : rect.top - 12;
  return { top, left, arrow: Math.max(16, Math.min(centre - left, WIDTH - 16)), below };
}

export default function OnboardingTips() {
  const t = useTranslations("onboarding.tips");
  const onboarding = useOnboarding();
  const [tip, setTip] = useState<OnboardingTip | null>(null);
  const [place, setPlace] = useState<Place | null>(null);
  const [closed, setClosed] = useState<OnboardingTip[]>([]);
  const enabled = Boolean(onboarding?.show.tips) && !onboarding?.show.welcome;

  const look = useCallback(() => {
    if (!enabled || !onboarding) {
      setTip(null);
      return;
    }
    const seen = new Set<OnboardingTip>([...onboarding.tips_seen, ...closed]);
    for (const candidate of TIPS) {
      if (seen.has(candidate)) continue;
      const element = anchor(candidate);
      if (element) {
        setTip(candidate);
        setPlace(placeFor(element));
        return;
      }
    }
    setTip(null);
  }, [closed, enabled, onboarding]);

  useEffect(() => {
    if (!enabled) return;
    look();
    const timer = window.setInterval(look, LOOK_EVERY_MS);
    window.addEventListener("resize", look);
    window.addEventListener("scroll", look, true);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("resize", look);
      window.removeEventListener("scroll", look, true);
    };
  }, [enabled, look]);

  if (!tip || !place) return null;

  const dismiss = () => {
    setClosed((current) => [...current, tip]);
    setTip(null);
    void markOnboarding(`tip:${tip}`);
  };

  return createPortal(
    <div
      role="status"
      className="fixed z-[65] flex flex-col gap-1.5 rounded-xl bg-[#101323] p-3.5 font-syne text-white shadow-[0_12px_32px_rgba(16,24,40,0.3)]"
      style={{
        top: place.top,
        left: place.left,
        width: WIDTH,
        transform: place.below ? undefined : "translateY(-100%)",
      }}
    >
      <span
        aria-hidden="true"
        className="absolute h-3 w-3 rotate-45 bg-[#101323]"
        style={{ left: place.arrow - 6, ...(place.below ? { top: -6 } : { bottom: -6 }) }}
      />
      <p className="text-[13px] font-semibold">{t(`${tip}.title`)}</p>
      <p className="text-xs leading-5 text-white/80">{t(`${tip}.text`)}</p>
      <button
        type="button"
        onClick={dismiss}
        className="mt-1 self-start rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-[#B8EFC0] hover:bg-white/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B8EFC0]"
      >
        {t("gotIt")}
      </button>
    </div>,
    document.body,
  );
}
