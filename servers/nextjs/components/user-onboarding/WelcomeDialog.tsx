"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { FileUp, Images, Presentation } from "lucide-react";
import { useTranslations } from "next-intl";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { formatRub } from "@/app/(presentation-generator)/services/api/billing";
import { markOnboarding, useOnboarding } from "./useOnboarding";

const PATHS = [
  { id: "presentation", href: "/upload", icon: Presentation },
  { id: "studio", href: "/studio", icon: Images },
  { id: "template", href: "/custom-template", icon: FileUp },
] as const;

type PathId = (typeof PATHS)[number]["id"];

/** The first sign-in: the start bonus and three ways to begin. */
export default function WelcomeDialog() {
  const t = useTranslations("onboarding.welcome");
  const router = useRouter();
  const onboarding = useOnboarding();
  const [path, setPath] = useState<PathId>("presentation");
  const [closing, setClosing] = useState(false);
  const open = Boolean(onboarding?.show.welcome) && !closing;

  const finish = async (also: "tour" | null, href?: string) => {
    setClosing(true);
    await markOnboarding("welcome");
    if (also) await markOnboarding(also);
    if (href) router.push(href);
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !next && void finish(null)}>
      <DialogContent
        hideDefaultClose
        className="max-w-[560px] gap-5 rounded-2xl border-[#EDEEEF] bg-white p-6 font-syne"
      >
        <div className="space-y-2">
          <DialogTitle className="text-[22px] font-semibold leading-tight text-[#101323]">
            {t("title")}
          </DialogTitle>
          <DialogDescription className="text-sm leading-6 text-[#475467]">
            {onboarding?.welcome_text || t("text")}
          </DialogDescription>
        </div>

        {onboarding && onboarding.bonus > 0 ? (
          <div className="flex items-center gap-3 rounded-xl border border-[#B8EFC0] bg-[#ECFBEE] px-4 py-3 text-sm text-[#027A0E]">
            <strong className="shrink-0 text-lg font-semibold">{formatRub(onboarding.bonus)}</strong>
            <span>{t("bonus")}</span>
          </div>
        ) : null}

        <div role="radiogroup" aria-label={t("pathsLabel")} className="grid gap-2 sm:grid-cols-3">
          {PATHS.map(({ id, icon: Icon }) => {
            const picked = path === id;
            return (
              <button
                key={id}
                type="button"
                role="radio"
                aria-checked={picked}
                onClick={() => setPath(id)}
                className={`flex flex-col items-start gap-1.5 rounded-xl border p-3 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#03B015]/40 ${
                  picked ? "border-[#03B015] shadow-[0_0_0_1px_#03B015]" : "border-[#EDEEEF] hover:border-[#B8EFC0]"
                }`}
              >
                <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-[#B8EFC0] bg-[#ECFBEE] text-[#02940F]">
                  <Icon className="h-4 w-4" aria-hidden="true" />
                </span>
                <span className="text-sm font-semibold text-[#101323]">{t(`paths.${id}.title`)}</span>
                <span className="text-xs leading-5 text-[#667085]">{t(`paths.${id}.text`)}</span>
              </button>
            );
          })}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <button
            type="button"
            onClick={() => void finish("tour")}
            className="text-xs font-medium text-[#667085] hover:text-[#101323]"
          >
            {t("skip")}
          </button>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void finish(null)}
              className="h-10 rounded-full border border-[#EDEEEF] px-4 text-xs font-semibold text-[#101323] hover:border-[#B8EFC0]"
            >
              {t("lookAround")}
            </button>
            <button
              type="button"
              onClick={() => void finish(null, PATHS.find((item) => item.id === path)?.href)}
              className="h-10 rounded-full bg-[#03B015] px-5 text-xs font-semibold text-white hover:bg-[#02940F]"
            >
              {t("start")}
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
