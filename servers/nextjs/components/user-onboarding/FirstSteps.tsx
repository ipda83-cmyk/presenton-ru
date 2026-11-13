"use client";

import Link from "next/link";
import { Check } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ChecklistItem } from "@/app/(presentation-generator)/services/api/onboarding";
import { markOnboarding, useOnboarding } from "./useOnboarding";

function linkFor(item: ChecklistItem, latest: string | null): string {
  switch (item) {
    case "presentation":
      return "/upload";
    case "edited":
    case "exported":
      return latest ? `/presentation?id=${latest}` : "/upload";
    case "studio":
      return "/studio";
    case "topup":
      return "/billing";
    case "template":
      return "/custom-template";
  }
}

/** «Первые шаги» on the dashboard: ticked by what the user has really done. */
export default function FirstSteps() {
  const t = useTranslations("onboarding.checklist");
  const onboarding = useOnboarding({ fresh: true });
  if (!onboarding?.show.checklist) return null;
  const items = onboarding.checklist;
  const done = items.filter((item) => item.done).length;
  const next = items.find((item) => !item.done)?.id;

  return (
    <section
      aria-labelledby="first-steps-title"
      className="w-full max-w-[340px] shrink-0 rounded-xl border border-[#B8EFC0] bg-white p-4 font-syne"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="first-steps-title" className="text-sm font-semibold text-[#101323]">
          {t("title")}
        </h2>
        <span className="text-[11px] text-[#667085]" style={{ fontVariantNumeric: "tabular-nums" }}>
          {t("progress", { done, total: items.length })}
        </span>
      </div>
      <div
        className="mt-2 h-1.5 overflow-hidden rounded-full bg-[#EDEEEF]"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={items.length}
        aria-valuenow={done}
        aria-label={t("title")}
      >
        <div className="h-full rounded-full bg-[#03B015] transition-all" style={{ width: `${(done / Math.max(1, items.length)) * 100}%` }} />
      </div>
      <ul className="mt-3 space-y-2.5">
        {items.map((item) => (
          <li key={item.id} className="grid grid-cols-[18px_minmax(0,1fr)] gap-2 text-xs leading-5">
            <span
              aria-hidden="true"
              className={`mt-0.5 flex h-4 w-4 items-center justify-center rounded-[5px] border ${
                item.done ? "border-[#03B015] bg-[#03B015] text-white" : "border-[#D0D5DD] bg-white"
              }`}
            >
              {item.done ? <Check className="h-3 w-3" strokeWidth={3} /> : null}
            </span>
            <span>
              <span className={item.done ? "text-[#98A2B3] line-through" : "text-[#101323]"}>
                {t(`items.${item.id}`)}
                <span className="sr-only">{item.done ? ` — ${t("doneLabel")}` : ""}</span>
              </span>
              {item.id === next ? (
                <Link href={linkFor(item.id, onboarding.latest_presentation)} className="block text-[11px] font-medium text-[#027A0E] hover:underline">
                  {t(`go.${item.id}`)} →
                </Link>
              ) : null}
            </span>
          </li>
        ))}
      </ul>
      <button
        type="button"
        onClick={() => void markOnboarding("checklist")}
        className="mt-3 text-[11px] font-medium text-[#667085] hover:text-[#101323]"
      >
        {t("hide")}
      </button>
    </section>
  );
}
