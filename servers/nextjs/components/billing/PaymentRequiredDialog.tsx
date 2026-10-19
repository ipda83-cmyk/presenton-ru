"use client";

import { useEffect, useState } from "react";
import { Wallet } from "lucide-react";
import { useTranslations } from "next-intl";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { onPaymentRequired } from "@/utils/billingEvents";

/** Opens on any 402 answer: the server's message ("N ₽ needed, M ₽ on the
 * balance") and a top-up link. The billing page opens in a new tab so the
 * work in progress (attached files, an open editor) stays where it is. */
export default function PaymentRequiredDialog() {
  const t = useTranslations("billing.required");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => onPaymentRequired((text) => setMessage(text || t("fallback"))), [t]);

  return (
    <Dialog open={message !== null} onOpenChange={(open) => !open && setMessage(null)}>
      <DialogContent
        data-inline-edit-ignore="true"
        className="z-[10031] max-w-md rounded-2xl font-syne"
        overlayClassName="z-[10030]"
      >
        <div className="flex h-11 w-11 items-center justify-center rounded-full bg-[#F4FEF5]">
          <Wallet className="h-5 w-5 text-[#02940F]" aria-hidden="true" />
        </div>
        <DialogTitle className="text-lg font-medium text-[#101323]">{t("title")}</DialogTitle>
        <DialogDescription className="text-sm leading-6 text-[#4C5554]">{message}</DialogDescription>
        <p className="text-xs leading-5 text-[#667085]">{t("hint")}</p>
        <div className="flex flex-wrap justify-end gap-2">
          <button
            type="button"
            onClick={() => setMessage(null)}
            className="min-h-10 rounded-full px-4 text-sm text-[#101323] hover:bg-[#F6F6F9] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#03B015]"
          >
            {t("close")}
          </button>
          <a
            href="/billing#topup"
            target="_blank"
            rel="noopener"
            onClick={() => setMessage(null)}
            className="inline-flex min-h-10 items-center rounded-full bg-[linear-gradient(90deg,#F1FADF_0%,#E1FBE3_100%)] px-5 text-sm font-semibold text-[#01530A] hover:brightness-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#03B015]"
          >
            {t("topUp")}
          </a>
        </div>
      </DialogContent>
    </Dialog>
  );
}
