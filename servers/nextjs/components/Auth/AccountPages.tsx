"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import AuthCard, { authButtonClass, authInputClass, authLinkClass } from "./AuthCard";
import { AccountApi, AccountError } from "@/utils/accountApi";
import { formatRub } from "@/app/(presentation-generator)/services/api/billing";

function Message({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  const Icon = ok ? CheckCircle2 : XCircle;
  return (
    <p role={ok ? "status" : "alert"} className={`flex items-start gap-2 rounded-lg border px-4 py-3 text-sm ${ok ? "border-[#B8EFC0] bg-[#ECFBEE] text-[#027A0E]" : "border-[#FECDCA] bg-[#FEF3F2] text-[#B42318]"}`}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <span>{children}</span>
    </p>
  );
}

/** /verify-email?token=… — confirms the address once, then the bonus. */
export function VerifyEmail() {
  const t = useTranslations("account");
  const token = useSearchParams().get("token") ?? "";
  const [state, setState] = useState<{ ok: boolean; bonus: number; error?: string } | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    if (!token) {
      setState({ ok: false, bonus: 0, error: t("verify.noToken") });
      return;
    }
    AccountApi.verify(token)
      .then((result) => setState({ ok: true, bonus: result.bonus }))
      .catch((reason) => setState({ ok: false, bonus: 0, error: reason instanceof AccountError ? reason.message : t("failed") }));
  }, [t, token]);

  return (
    <AuthCard title={t("verify.title")}>
      {state === null ? (
        <p className="flex items-center gap-2 text-sm text-[#6B7280]">
          <Loader2 className="h-4 w-4 animate-spin" /> {t("verify.checking")}
        </p>
      ) : state.ok ? (
        <div className="space-y-5">
          <Message ok>{state.bonus > 0 ? t("verify.doneBonus", { bonus: formatRub(state.bonus) }) : t("verify.done")}</Message>
          <Link href="/dashboard" className={`${authButtonClass} block text-center`}>
            {t("toDashboard")}
          </Link>
        </div>
      ) : (
        <div className="space-y-5">
          <Message ok={false}>{state.error}</Message>
          <p className="text-xs text-[#6B7280]">{t("verify.askAgain")}</p>
          <Link href="/dashboard" className={`${authButtonClass} block text-center`}>
            {t("toDashboard")}
          </Link>
        </div>
      )}
    </AuthCard>
  );
}

/** /forgot-password — the same answer whether the address exists or not. */
export function ForgotPassword() {
  const t = useTranslations("account");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await AccountApi.forgot(email.trim());
      setSent(true);
    } catch (reason) {
      setError(reason instanceof AccountError ? reason.message : t("failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthCard
      title={t("forgot.title")}
      intro={t("forgot.intro")}
      footer={
        <Link href="/" className={authLinkClass}>
          {t("toSignIn")}
        </Link>
      }
    >
      {sent ? (
        <Message ok>{t("forgot.sent")}</Message>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <label className="block space-y-2">
            <span className="block text-sm font-medium text-[#374151]">{t("email")}</span>
            <input id="forgot-email" type="email" autoComplete="email" required maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} className={authInputClass} disabled={busy} />
          </label>
          <p className="text-xs leading-5 text-[#6B7280]">{t("forgot.oldAccounts")}</p>
          {error ? <Message ok={false}>{error}</Message> : null}
          <button type="submit" disabled={busy} className={authButtonClass}>
            {busy ? t("forgot.sending") : t("forgot.submit")}
          </button>
        </form>
      )}
    </AuthCard>
  );
}

/** /reset-password?token=… — a new password; signs in on success. */
export function ResetPassword() {
  const t = useTranslations("account");
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const min = 8;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (password.length < min) return setError(t("passwordShort", { min }));
    if (password !== confirm) return setError(t("passwordsDiffer"));
    setBusy(true);
    try {
      await AccountApi.reset(token, password);
      router.replace("/dashboard");
    } catch (reason) {
      setError(reason instanceof AccountError ? reason.message : t("failed"));
      setBusy(false);
    }
  };

  if (!token) {
    return (
      <AuthCard title={t("reset.title")}>
        <div className="space-y-5">
          <Message ok={false}>{t("verify.noToken")}</Message>
          <Link href="/forgot-password" className={`${authButtonClass} block text-center`}>
            {t("reset.again")}
          </Link>
        </div>
      </AuthCard>
    );
  }

  return (
    <AuthCard title={t("reset.title")} intro={t("reset.intro")}>
      <form onSubmit={submit} className="space-y-4">
        <label className="block space-y-2">
          <span className="block text-sm font-medium text-[#374151]">{t("newPassword")}</span>
          <input id="reset-password" type="password" autoComplete="new-password" required minLength={min} maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} placeholder={t("passwordHint", { min })} className={authInputClass} disabled={busy} />
        </label>
        <label className="block space-y-2">
          <span className="block text-sm font-medium text-[#374151]">{t("passwordAgain")}</span>
          <input id="reset-confirm" type="password" autoComplete="new-password" required maxLength={128} value={confirm} onChange={(event) => setConfirm(event.target.value)} className={authInputClass} disabled={busy} />
        </label>
        {error ? (
          <>
            <Message ok={false}>{error}</Message>
            <Link href="/forgot-password" className={`${authLinkClass} block text-xs`}>
              {t("reset.again")}
            </Link>
          </>
        ) : null}
        <button type="submit" disabled={busy} className={authButtonClass}>
          {busy ? t("reset.saving") : t("reset.submit")}
        </button>
      </form>
    </AuthCard>
  );
}
