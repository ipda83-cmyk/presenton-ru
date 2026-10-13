"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import BalanceChip from "@/components/billing/BalanceChip";

const pill = "inline-flex min-h-[34px] items-center gap-1.5 rounded-full px-3.5 text-sm";

/** The Studio top bar's sections (Studio, Storyboard, Admin) and the balance with
 * "Top up": in the Studio header and on the main page. */
export default function StudioTopNav({
  isAdmin,
  active,
}: {
  isAdmin: boolean;
  /** The current Studio section; none outside the Studio. */
  active?: "studio" | "storyboard";
}) {
  const t = useTranslations("studio.nav");

  return (
    <>
      <nav
        aria-label={t("aria")}
        className="flex min-h-[42px] shrink-0 items-center gap-1 rounded-[32px] border border-[#EDEEEF] bg-white px-1.5 py-1 font-syne"
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
      <BalanceChip />
    </>
  );
}
