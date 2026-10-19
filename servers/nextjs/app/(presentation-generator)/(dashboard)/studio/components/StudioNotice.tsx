"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import StudioMark from "@/components/studio/StudioMark";

// Shown instead of the tools while the arckep key is missing.
export default function StudioNotice({ isAdmin, error }: { isAdmin: boolean; error?: string | null }) {
  const t = useTranslations("studio.notConfigured");
  return (
    <div className="mx-4 mt-10 flex max-w-lg sm:mx-auto flex-col items-center gap-3 rounded-2xl border border-[#EDEEEF] bg-[#F9F8FB] px-8 py-10 text-center">
      <StudioMark size={48} />
      <h2 className="font-syne text-lg font-medium text-[#101323]">{error ? t("errorTitle") : t("title")}</h2>
      <p className="text-sm leading-6 text-[#475467]">{error ?? (isAdmin ? t("admin") : t("user"))}</p>
      {isAdmin && !error && (
        <Link href="/settings?section=studio" className="mt-1 font-syne text-sm font-semibold text-[#02940F] hover:text-[#027A0E]">
          {t("openSettings")}
        </Link>
      )}
    </div>
  );
}
