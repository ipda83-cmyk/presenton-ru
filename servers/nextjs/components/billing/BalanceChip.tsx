"use client";

import Link from "next/link";
import { Wallet } from "lucide-react";
import { useTranslations } from "next-intl";
import { formatRub } from "@/app/(presentation-generator)/services/api/billing";
import { isPaying, useBilling } from "./useBilling";

const pill = "inline-flex min-h-[34px] items-center gap-1.5 rounded-full px-3.5 text-sm";

/** Balance and "Top up" for the Studio top bar; nothing for administrators. */
export default function BalanceChip() {
  const t = useTranslations("billing.chip");
  const { me } = useBilling();
  if (!isPaying(me)) return null;

  return (
    <div className="flex min-h-[42px] items-center gap-1 rounded-[32px] border border-[#EDEEEF] bg-white px-1.5 py-1">
      <Link
        href="/billing"
        className={`${pill} font-medium text-[#101323] hover:bg-[#F6F6F9]`}
        aria-label={t("aria", { amount: formatRub(me.balance) })}
      >
        <Wallet className="h-4 w-4 text-[#5141E5]" aria-hidden="true" />
        {formatRub(me.balance)}
      </Link>
      <Link
        href="/billing#topup"
        className={`${pill} bg-[linear-gradient(90deg,#FCE7D4_0%,#E5DDFF_100%)] font-semibold text-[#3A2A8C] hover:brightness-95`}
      >
        {t("topUp")}
      </Link>
    </div>
  );
}
