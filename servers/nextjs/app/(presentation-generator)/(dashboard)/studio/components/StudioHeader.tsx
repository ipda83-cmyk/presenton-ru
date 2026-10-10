"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import LanguageSwitcher from "@/components/LanguageSwitcher";

const pill = "inline-flex min-h-[34px] items-center gap-1.5 rounded-full px-3.5 text-sm";

// Studio top bar: page title, Studio sections, language. Balance and
// "Top up" join it with payments (step 3.8).
export default function StudioHeader({ title, isAdmin }: { title: string; isAdmin: boolean }) {
  const t = useTranslations("studio.nav");

  return (
    <header className="sticky top-0 z-40 ml-7 mr-[9px] flex min-h-[105px] flex-wrap items-center justify-between gap-4 border-b border-[#EDEEEF] bg-white px-1 py-4 font-syne">
      <h1 className="text-[22px] font-medium tracking-[-0.66px] text-[#101323]">{title}</h1>
      <div className="flex flex-wrap items-center gap-3">
        <nav
          aria-label={t("aria")}
          className="flex min-h-[42px] items-center gap-1 rounded-[32px] border border-[#EDEEEF] bg-white px-1.5 py-1"
        >
          <Link href="/studio" aria-current="page" className={`${pill} bg-[#F4F3FF] font-medium text-[#5141E5]`}>
            {t("studio")}
          </Link>
          <span aria-disabled="true" title={t("soonHint")} className={`${pill} cursor-default text-[#98A2B3]`}>
            Storyboard
            <span className="rounded-full bg-[#F2F4F7] px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[#667085]">
              {t("soon")}
            </span>
          </span>
          {isAdmin && (
            <Link href="/admin" className={`${pill} font-semibold text-[#5141E5] hover:bg-[#F4F3FF]`}>
              {t("admin")}
            </Link>
          )}
        </nav>
        <LanguageSwitcher size="md" />
      </div>
    </header>
  );
}
