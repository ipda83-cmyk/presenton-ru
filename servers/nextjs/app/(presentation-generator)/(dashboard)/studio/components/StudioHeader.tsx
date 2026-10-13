"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import LanguageSwitcher from "@/components/LanguageSwitcher";

const pill = "inline-flex min-h-[34px] items-center gap-1.5 rounded-full px-3.5 text-sm";

// Studio top bar: page title, Studio sections, language. Balance and
// "Top up" join it with payments (step 3.8).
export default function StudioHeader({
  title,
  isAdmin,
  active = "studio",
}: {
  title: string;
  isAdmin: boolean;
  active?: "studio" | "storyboard";
}) {
  const t = useTranslations("studio.nav");

  return (
    <header className="mx-4 flex flex-wrap items-center justify-between gap-3 border-b border-[#EDEEEF] bg-white px-1 py-4 font-syne md:sticky md:top-0 md:z-40 md:ml-7 md:mr-[9px] md:min-h-[105px] md:gap-4">
      <h1 className="text-[22px] font-medium tracking-[-0.66px] text-[#101323]">{title}</h1>
      <div className="flex flex-wrap items-center gap-3">
        <nav
          aria-label={t("aria")}
          className="flex min-h-[42px] items-center gap-1 rounded-[32px] border border-[#EDEEEF] bg-white px-1.5 py-1"
        >
          {(["studio", "storyboard"] as const).map((tab) => (
            <Link
              key={tab}
              href={tab === "studio" ? "/studio" : "/studio/storyboard"}
              aria-current={active === tab ? "page" : undefined}
              className={`${pill} ${active === tab ? "bg-[#F4F3FF] font-medium text-[#5141E5]" : "text-[#191919] hover:bg-[#F6F6F9]"}`}
            >
              {tab === "studio" ? t("studio") : "Storyboard"}
            </Link>
          ))}
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
