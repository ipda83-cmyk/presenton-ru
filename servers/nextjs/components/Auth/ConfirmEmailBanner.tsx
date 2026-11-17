"use client";

import { useEffect, useState } from "react";
import { MailCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import { getApiUrl } from "@/utils/api";
import { AccountApi, AccountError } from "@/utils/accountApi";
import { formatRub } from "@/app/(presentation-generator)/services/api/billing";

/** For a self-registered user who has not confirmed the e-mail yet. */
export default function ConfirmEmailBanner() {
  const t = useTranslations("account.banner");
  const [email, setEmail] = useState<string | null>(null);
  const [bonus, setBonus] = useState(0);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch(getApiUrl("/api/v1/auth/status"), { credentials: "include", cache: "no-store" })
      .then((response) => (response.ok ? response.json() : null))
      .then((status) => {
        if (status?.authenticated && status.verified === false) {
          setEmail(status.username);
          AccountApi.info().then((info) => setBonus(info.bonus)).catch(() => undefined);
        }
      })
      .catch(() => undefined);
  }, []);

  if (!email) return null;

  const resend = async () => {
    setBusy(true);
    try {
      const result = await AccountApi.resend();
      setNote(result.verified ? { ok: true, text: t("already") } : { ok: true, text: t("sent", { email }) });
    } catch (reason) {
      setNote({ ok: false, text: reason instanceof AccountError ? reason.message : t("failed") });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div role="status" className="mx-3 mt-3 flex flex-wrap items-center gap-3 rounded-xl border border-[#F5D48A] bg-[#FFF8E6] px-4 py-3 font-syne text-sm text-[#7A4F00] sm:mx-6">
      <MailCheck className="h-5 w-5 shrink-0" aria-hidden="true" />
      <p className="min-w-0 flex-1">
        {bonus > 0 ? t("textBonus", { email, bonus: formatRub(bonus) }) : t("text", { email })}
        {note ? <span className={`block text-xs ${note.ok ? "text-[#027A0E]" : "text-[#B42318]"}`}>{note.text}</span> : null}
      </p>
      <button
        type="button"
        disabled={busy}
        onClick={() => void resend()}
        className="shrink-0 rounded-full border border-[#E8B957] bg-white px-4 py-1.5 text-xs font-semibold text-[#7A4F00] hover:bg-[#FFF3D1] disabled:opacity-60"
      >
        {t("resend")}
      </button>
    </div>
  );
}
