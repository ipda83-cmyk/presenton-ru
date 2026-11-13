"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Compass, Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { markOnboarding } from "./useOnboarding";

/** Help → the dashboard tour once more. */
export default function RestartTourButton() {
  const t = useTranslations("onboarding.tour");
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  return (
    <button
      type="button"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        await markOnboarding("tour_restart");
        router.push("/dashboard");
      }}
      className="inline-flex items-center gap-1.5 rounded-full border border-[#B8EFC0] px-3 py-1.5 text-xs font-semibold text-[#027A0E] hover:bg-[#ECFBEE] disabled:opacity-60"
    >
      {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Compass className="h-3.5 w-3.5" aria-hidden="true" />}
      {t("restart")}
    </button>
  );
}
