"use client";

import { ArrowLeft } from "lucide-react";
import { useTranslations } from "next-intl";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import HomeButton from "@/components/HomeButton";

interface OutlineStandardHeaderProps {
  title: string;
  onBack: () => void;
}

const OutlineStandardHeader = ({
  title,
  onBack,
}: OutlineStandardHeaderProps) => {
  const t = useTranslations();
  return (
  <header className="sticky top-0 z-[60] h-[68px] w-full border-b border-[#EDEEEF] bg-white font-syne">
    <div className="flex h-full items-center justify-between px-6">
      <div className="flex min-w-0 items-center gap-3">
        <HomeButton logoHeight={22} />
        <h1 className="truncate text-base font-medium tracking-[0.16px] text-[#101323]">
          {title}
        </h1>
      </div>

      <div className="flex shrink-0 items-center gap-5">
        <button
          type="button"
          onClick={onBack}
          className="flex shrink-0 items-center gap-2 text-xs font-semibold uppercase tracking-[0.96px] text-[#333333] transition-colors hover:text-[#03B015] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#03B015]/30"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          {t("common.back")}
        </button>
        <LanguageSwitcher />
      </div>
    </div>
  </header>
  );
};

export default OutlineStandardHeader;
