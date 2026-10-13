"use client";

import LanguageSwitcher from "@/components/LanguageSwitcher";
import StudioTopNav from "@/components/studio/StudioTopNav";

// Studio top bar: page title, Studio sections, balance with "Top up", language.
export default function StudioHeader({
  title,
  isAdmin,
  active = "studio",
}: {
  title: string;
  isAdmin: boolean;
  active?: "studio" | "storyboard";
}) {
  return (
    <header className="mx-4 flex flex-wrap items-center justify-between gap-3 border-b border-[#EDEEEF] bg-white px-1 py-4 font-syne md:sticky md:top-0 md:z-40 md:ml-7 md:mr-[9px] md:min-h-[105px] md:gap-4">
      <h1 className="text-[22px] font-medium tracking-[-0.66px] text-[#101323]">{title}</h1>
      <div className="flex flex-wrap items-center gap-3">
        <StudioTopNav isAdmin={isAdmin} active={active} />
        <LanguageSwitcher size="md" />
      </div>
    </header>
  );
}
