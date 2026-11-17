"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import { AccountError, AdminRegistrationApi, type AdminRegistration as State } from "@/utils/accountApi";

function Status({ ok, label, detail }: { ok: boolean; label: string; detail?: string }) {
  const Icon = ok ? CheckCircle2 : XCircle;
  return (
    <div className="flex items-start gap-2 rounded-lg bg-[#F9FAFB] px-4 py-3">
      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${ok ? "text-[#03B015]" : "text-[#B42318]"}`} aria-hidden="true" />
      <div className="min-w-0">
        <p className="text-sm font-medium text-[#101323]">{label}</p>
        {detail ? <p className="break-words text-xs text-[#667085]">{detail}</p> : null}
      </div>
    </div>
  );
}

/** Administrators: open or close sign-up, limits, blocked domains, mail and captcha status. */
export default function AdminRegistration() {
  const t = useTranslations("adminRegistration");
  const [state, setState] = useState<State | null>(null);
  const [open, setOpen] = useState(false);
  const [limit, setLimit] = useState("3");
  const [domains, setDomains] = useState("");
  const [testTo, setTestTo] = useState("");
  const [busy, setBusy] = useState<string | null>("load");
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);

  const apply = useCallback((value: State) => {
    setState(value);
    setOpen(value.settings.open);
    setLimit(String(value.settings.ip_daily_limit));
    setDomains(value.settings.blocked_domains.join("\n"));
  }, []);

  const run = useCallback(async (kind: string, action: () => Promise<void>) => {
    setBusy(kind);
    setNote(null);
    try {
      await action();
    } catch (reason) {
      setNote({ ok: false, text: reason instanceof AccountError ? reason.message : t("failed") });
    } finally {
      setBusy(null);
    }
  }, [t]);

  useEffect(() => {
    void run("load", async () => apply(await AdminRegistrationApi.read()));
  }, [apply, run]);

  if (!state) {
    return (
      <div className="flex items-center gap-2 py-10 text-sm text-[#667085]">
        {note ? note.text : (<><Loader2 className="h-4 w-4 animate-spin" /> {t("loading")}</>)}
      </div>
    );
  }

  const save = () =>
    void run("save", async () => {
      apply(
        await AdminRegistrationApi.save({
          open,
          ip_daily_limit: Math.max(1, Math.min(1000, Number.parseInt(limit, 10) || 3)),
          blocked_domains: domains.split(/[\s,;]+/).map((item) => item.trim()).filter(Boolean),
        }),
      );
      setNote({ ok: true, text: t("saved") });
    });

  return (
    <div className="space-y-5">
      <section className="rounded-[12px] border border-[#EDEEEF] bg-white p-6">
        <h2 className="text-sm font-semibold text-[#101323]">{t("title")}</h2>
        <p className="mt-1 max-w-2xl text-xs leading-relaxed text-[#667085]">{t("desc")}</p>
        <div className="mt-4 grid gap-2 md:grid-cols-2">
          <Status
            ok={state.mail.configured}
            label={state.mail.configured ? t("mailReady") : t("mailMissing")}
            detail={state.mail.configured ? undefined : t("mailMissingVars", { vars: state.mail.missing.join(", ") })}
          />
          <Status
            ok={state.captcha.configured}
            label={state.captcha.configured ? t("captchaReady") : t("captchaMissing")}
            detail={state.captcha.configured ? undefined : t("captchaMissingVars")}
          />
        </div>
      </section>

      <section className="space-y-4 rounded-[12px] border border-[#EDEEEF] bg-white p-6">
        <label className="flex cursor-pointer items-center justify-between gap-4">
          <span>
            <span className="block text-sm font-medium text-[#101323]">{t("open")}</span>
            <span className="block text-xs text-[#667085]">{t("openHint")}</span>
          </span>
          <input
            id="registration-open"
            type="checkbox"
            className="h-5 w-9 shrink-0 cursor-pointer accent-[#03B015]"
            checked={open}
            disabled={!state.mail.configured && !open}
            onChange={(event) => setOpen(event.target.checked)}
          />
        </label>

        <label className="block">
          <span className="mb-1.5 block text-xs font-medium text-[#344054]">{t("ipLimit")}</span>
          <input
            id="registration-ip-limit"
            type="number"
            min={1}
            max={1000}
            value={limit}
            onChange={(event) => setLimit(event.target.value)}
            className="h-10 w-32 rounded-lg border border-[#EDEEEF] px-3 text-sm outline-none focus:border-[#03B015]"
          />
        </label>

        <label className="block">
          <span className="mb-1.5 block text-xs font-medium text-[#344054]">{t("domains")}</span>
          <textarea
            id="registration-domains"
            value={domains}
            onChange={(event) => setDomains(event.target.value)}
            placeholder="example-temp-mail.ru"
            className="min-h-[96px] w-full rounded-lg border border-[#EDEEEF] px-3 py-2.5 font-mono text-[13px] outline-none focus:border-[#03B015]"
          />
          <span className="mt-1 block text-xs text-[#667085]">{t("domainsHint", { count: state.builtin_blocked_domains })}</span>
        </label>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            disabled={busy !== null}
            onClick={save}
            className="inline-flex h-10 items-center gap-2 rounded-full bg-[#03B015] px-5 text-xs font-semibold text-white hover:bg-[#02940F] disabled:opacity-60"
          >
            {busy === "save" ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            {t("save")}
          </button>
        </div>
      </section>

      <section className="space-y-3 rounded-[12px] border border-[#EDEEEF] bg-white p-6">
        <h3 className="text-sm font-semibold text-[#101323]">{t("testTitle")}</h3>
        <p className="text-xs text-[#667085]">{t("testHint")}</p>
        <div className="flex flex-wrap gap-2">
          <input
            id="registration-test-to"
            type="email"
            value={testTo}
            onChange={(event) => setTestTo(event.target.value)}
            placeholder={t("testPlaceholder")}
            className="h-10 min-w-0 flex-1 rounded-lg border border-[#EDEEEF] px-3 text-sm outline-none focus:border-[#03B015]"
          />
          <button
            type="button"
            disabled={busy !== null || !state.mail.configured}
            onClick={() =>
              void run("test", async () => {
                const result = await AdminRegistrationApi.testEmail(testTo.trim() || undefined);
                setNote({ ok: true, text: t("testSent", { to: result.to }) });
              })
            }
            className="inline-flex h-10 items-center gap-2 rounded-full border border-[#EDEEEF] px-4 text-xs font-semibold text-[#101323] hover:border-[#B8EFC0] disabled:opacity-60"
          >
            {busy === "test" ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            {t("testSend")}
          </button>
        </div>
      </section>

      {note ? (
        <p role="status" className={`text-xs ${note.ok ? "text-[#027A0E]" : "text-[#B42318]"}`}>
          {note.text}
        </p>
      ) : null}
    </div>
  );
}
