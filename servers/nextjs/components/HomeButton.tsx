"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { useTranslations } from "next-intl";
import BrandLogo from "@/components/brand/BrandLogo";
import ToolTip from "@/components/ToolTip";

/**
 * «← Главная» and the logo for headers of full-screen pages (editor, outline):
 * both lead to the dashboard. On narrow screens only the arrow is left.
 */
export default function HomeButton({ logoHeight = 24 }: { logoHeight?: number }) {
  const t = useTranslations("common");
  return (
    <div className="flex shrink-0 items-center gap-3">
      <Link
        href="/dashboard"
        aria-label={t("goHome")}
        title={t("goHome")}
        className="inline-flex h-8 items-center gap-1.5 rounded-full border border-[#B8EFC0] px-2.5 text-xs font-semibold text-[#027A0E] transition-colors hover:bg-[#ECFBEE] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#03B015]/30 sm:px-3"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        <span className="hidden sm:inline">{t("home")}</span>
      </Link>
      <span className="h-5 w-px bg-[#EDEEEF]" aria-hidden="true" />
      <ToolTip content={t("goHome")}>
        <Link
          href="/dashboard"
          aria-label={t("goHome")}
          className="block shrink-0 rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#03B015]/30"
        >
          <BrandLogo variant="mark" height={logoHeight} />
        </Link>
      </ToolTip>
    </div>
  );
}
