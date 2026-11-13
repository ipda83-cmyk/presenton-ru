"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { errorMessage } from "@/components/studio/controls";
import { markOnboarding } from "@/components/user-onboarding/useOnboarding";
import {
  OnboardingApi,
  type AdminOnboarding as AdminOnboardingState,
  type OnboardingSettings,
} from "../../services/api/onboarding";

const PARTS = ["welcome", "tour", "checklist", "tips"] as const;

/** Administrators: which onboarding parts users see, the welcome text, results. */
export default function AdminOnboarding() {
  const t = useTranslations("adminOnboarding");
  const tw = useTranslations("onboarding.welcome");
  const router = useRouter();
  const [state, setState] = useState<AdminOnboardingState | null>(null);
  const [draft, setDraft] = useState<OnboardingSettings | null>(null);
  const [busy, setBusy] = useState<string | null>("load");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmAgain, setConfirmAgain] = useState(false);

  const run = useCallback(
    async (kind: string, action: () => Promise<AdminOnboardingState | void>, done?: string) => {
      setBusy(kind);
      setError(null);
      setNotice(null);
      try {
        const result = await action();
        if (result) {
          setState(result);
          setDraft(result.settings);
        }
        if (done) setNotice(done);
      } catch (reason) {
        setError(errorMessage(reason, t("requestFailed")));
      } finally {
        setBusy(null);
      }
    },
    [t],
  );

  useEffect(() => {
    void run("load", OnboardingApi.admin);
  }, [run]);

  if (!state || !draft) {
    return (
      <div className="flex items-center gap-2 py-10 text-sm text-[#667085]">
        {error ?? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" /> {t("loading")}
          </>
        )}
      </div>
    );
  }

  const stats = state.stats;
  const tiles = [
    { label: t("stats.users", { days: stats.days }), value: stats.users },
    { label: t("stats.presentation"), value: stats.presentation },
    { label: t("stats.exported"), value: stats.exported },
    { label: t("stats.studio"), value: stats.studio },
  ];

  return (
    <div className="space-y-5">
      <section className="rounded-[12px] border border-[#EDEEEF] bg-white p-6">
        <h2 className="text-sm font-semibold text-[#101323]">{t("title")}</h2>
        <p className="mt-1 max-w-2xl text-xs leading-relaxed text-[#667085]">{t("desc")}</p>
        <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {tiles.map((tile) => (
            <div key={tile.label} className="rounded-lg bg-[#F9FAFB] px-4 py-3">
              <p className="font-syne text-xl font-semibold text-[#101323]" style={{ fontVariantNumeric: "tabular-nums" }}>
                {tile.value}
              </p>
              <p className="text-xs text-[#667085]">{tile.label}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-[12px] border border-[#EDEEEF] bg-white p-6">
        <div className="divide-y divide-[#EDEEEF]">
          {PARTS.map((part) => (
            <label key={part} className="flex cursor-pointer items-center justify-between gap-4 py-3">
              <span>
                <span className="block text-sm font-medium text-[#101323]">{t(`parts.${part}.title`)}</span>
                <span className="block text-xs text-[#667085]">{t(`parts.${part}.text`)}</span>
              </span>
              <input
                type="checkbox"
                className="h-5 w-9 shrink-0 cursor-pointer accent-[#03B015]"
                checked={draft[part]}
                onChange={(event) => setDraft({ ...draft, [part]: event.target.checked })}
              />
            </label>
          ))}
        </div>

        <label className="mt-4 block">
          <span className="mb-1.5 block text-xs font-medium text-[#344054]">{t("welcomeText")}</span>
          <textarea
            className="min-h-[84px] w-full rounded-lg border border-[#EDEEEF] bg-white px-3 py-2.5 text-sm text-[#101323] outline-none focus:border-[#03B015]"
            maxLength={400}
            placeholder={tw("text")}
            value={draft.welcome_text}
            onChange={(event) => setDraft({ ...draft, welcome_text: event.target.value })}
          />
          <span className="mt-1 block text-xs text-[#667085]">{t("welcomeTextHint")}</span>
        </label>

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => void run("save", () => OnboardingApi.save(draft), t("saved"))}
            className="inline-flex h-10 items-center gap-2 rounded-full bg-[#03B015] px-5 text-xs font-semibold text-white hover:bg-[#02940F] disabled:opacity-60"
          >
            {busy === "save" ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            {t("save")}
          </button>
          {confirmAgain ? (
            <span className="flex flex-wrap items-center gap-2 text-xs text-[#344054]">
              {t("showAgainConfirm")}
              <button
                type="button"
                disabled={busy !== null}
                onClick={() =>
                  void run("again", async () => {
                    const result = await OnboardingApi.showAgain();
                    setConfirmAgain(false);
                    return result;
                  }, t("shownAgain"))
                }
                className="h-8 rounded-full border border-[#EDEEEF] px-3 font-semibold text-[#101323] hover:border-[#B8EFC0]"
              >
                {t("showAgainYes")}
              </button>
              <button type="button" onClick={() => setConfirmAgain(false)} className="h-8 rounded-full px-3 text-[#667085]">
                {t("cancel")}
              </button>
            </span>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmAgain(true)}
              className="h-10 rounded-full border border-[#EDEEEF] px-4 text-xs font-semibold text-[#101323] hover:border-[#B8EFC0]"
            >
              {t("showAgain")}
            </button>
          )}
          <button
            type="button"
            disabled={busy !== null}
            onClick={() =>
              void run("preview", async () => {
                await markOnboarding("preview");
                router.push("/dashboard");
              })
            }
            className="h-10 rounded-full px-4 text-xs font-semibold text-[#027A0E] hover:bg-[#ECFBEE]"
          >
            {t("previewMe")}
          </button>
          <span role="status" className="text-xs">
            {error ? <span className="text-[#B42318]">{error}</span> : <span className="text-[#667085]">{notice}</span>}
          </span>
        </div>
      </section>
    </div>
  );
}
