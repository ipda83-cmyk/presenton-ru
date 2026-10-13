"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { CreditCard, Loader2, RefreshCw, Wallet } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import {
  BillingApi,
  formatRub,
  type AdminBillingAccount,
  type BillingEntry,
} from "../../services/api/billing";
import { errorMessage } from "@/components/studio/controls";

const inputClass =
  "h-10 rounded-lg border border-[#EDEEEF] bg-white px-3 text-sm text-[#101323] outline-none focus:border-[#7A5AF8]";

/** Administrators: everyone's balance, manual credits and the operations log. */
export default function AdminBilling() {
  const t = useTranslations("billing.admin");
  const format = useFormatter();
  const [accounts, setAccounts] = useState<AdminBillingAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [userId, setUserId] = useState("");
  const [amount, setAmount] = useState("");
  const [mode, setMode] = useState<"add" | "set">("add");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<{ user: string; entries: BillingEntry[] } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await BillingApi.adminAccounts();
      setAccounts(result.accounts);
      setError(null);
    } catch (reason) {
      setError(errorMessage(reason, t("loadFailed")));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const value = Number(amount);
    if (!userId || !Number.isInteger(value)) return;
    setBusy(true);
    try {
      await BillingApi.adminAdjust({ user_id: userId, amount: value, mode, note: note.trim() });
      setAmount("");
      setNote("");
      await load();
      if (history?.user === userId) await openHistory(userId);
    } catch (reason) {
      setError(errorMessage(reason, t("adjustFailed")));
    } finally {
      setBusy(false);
    }
  };

  const openHistory = async (id: string) => {
    try {
      const result = await BillingApi.adminHistory(id);
      setHistory({ user: id, entries: result.entries });
    } catch (reason) {
      setError(errorMessage(reason, t("loadFailed")));
    }
  };

  const nameOf = (id: string) => accounts.find((account) => account.user_id === id)?.username ?? "";

  return (
    <div className="space-y-5">
      <section className="rounded-[12px] border border-[#EDEEEF] bg-white p-6">
        <div className="mb-5 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#F4F3FF]">
            <Wallet className="h-4 w-4 text-[#5146E5]" aria-hidden="true" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-[#101323]">{t("adjustTitle")}</h2>
            <p className="mt-0.5 text-xs text-[#667085]">{t("adjustDesc")}</p>
          </div>
        </div>
        <form onSubmit={submit} className="grid gap-3 lg:grid-cols-[1fr_140px_120px_1fr_auto]">
          <select aria-label={t("user")} className={inputClass} value={userId} onChange={(event) => setUserId(event.target.value)} required>
            <option value="" disabled>{t("selectUser")}</option>
            {accounts.map((account) => (
              <option key={account.user_id} value={account.user_id}>
                {account.username}
              </option>
            ))}
          </select>
          <select aria-label={t("mode")} className={inputClass} value={mode} onChange={(event) => setMode(event.target.value as "add" | "set")}>
            <option value="add">{t("modeAdd")}</option>
            <option value="set">{t("modeSet")}</option>
          </select>
          <input
            aria-label={t("amount")}
            className={inputClass}
            type="number"
            inputMode="numeric"
            step={1}
            placeholder={mode === "add" ? "+100 / −50" : "500"}
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            required
          />
          <input aria-label={t("note")} className={inputClass} maxLength={200} placeholder={t("notePh")} value={note} onChange={(event) => setNote(event.target.value)} />
          <button
            type="submit"
            disabled={busy || !userId || amount === ""}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-full bg-[#5146E5] px-5 text-xs font-semibold text-white transition hover:bg-[#4338CA] disabled:opacity-60"
          >
            {busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {t("apply")}
          </button>
        </form>
        {error && <p role="alert" className="mt-3 text-sm text-[#B42318]">{error}</p>}
      </section>

      <section className="overflow-hidden rounded-[12px] border border-[#EDEEEF] bg-white">
        <div className="flex items-center justify-between border-b border-[#EDEEEF] px-6 py-5">
          <h2 className="text-sm font-semibold text-[#101323]">{t("balances")}</h2>
          <button
            type="button"
            aria-label={t("refresh")}
            className="flex h-9 w-9 items-center justify-center rounded-full border border-[#EDEEEF] text-[#667085] transition hover:bg-[#F9FAFB] hover:text-[#5146E5]"
            onClick={() => void load()}
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} aria-hidden="true" />
          </button>
        </div>
        <div className="divide-y divide-[#EDEEEF]">
          {accounts.map((account) => (
            <div key={account.user_id} className="flex flex-wrap items-center justify-between gap-3 px-6 py-3.5">
              <div>
                <p className="text-sm font-semibold text-[#101323]">{account.username}</p>
                <p className="mt-0.5 flex items-center gap-1.5 text-xs text-[#667085]">
                  {account.admin ? t("adminFree") : account.balance === null ? t("noAccount") : null}
                  {account.card && (
                    <span className="inline-flex items-center gap-1">
                      <CreditCard className="h-3 w-3" aria-hidden="true" />
                      {account.auto_topup ? t("autoOn") : t("cardSaved")}
                    </span>
                  )}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-sm font-semibold text-[#101323]">
                  {account.balance === null ? "—" : formatRub(account.balance)}
                </span>
                <button
                  type="button"
                  className="h-8 rounded-full border border-[#EDEEEF] px-3 text-xs font-semibold text-[#344054] hover:bg-[#F9FAFB]"
                  onClick={() => void openHistory(account.user_id)}
                >
                  {t("history")}
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      {history && (
        <section className="overflow-hidden rounded-[12px] border border-[#EDEEEF] bg-white" aria-label={t("historyOf", { user: nameOf(history.user) })}>
          <h2 className="border-b border-[#EDEEEF] px-6 py-4 text-sm font-semibold text-[#101323]">
            {t("historyOf", { user: nameOf(history.user) })}
          </h2>
          {history.entries.length === 0 ? (
            <p className="px-6 py-6 text-sm text-[#667085]">{t("historyEmpty")}</p>
          ) : (
            <ul className="divide-y divide-[#F2F4F7]">
              {history.entries.map((entry) => (
                <li key={entry.id} className="flex items-start justify-between gap-3 px-6 py-2.5 text-sm">
                  <div className="min-w-0">
                    <p className="text-[#191919]">
                      {t(`kinds.${entry.kind}`)}
                      {entry.reason && !["signup", "admin", "yookassa"].includes(entry.reason) ? ` · ${entry.reason}` : ""}
                      {entry.details?.note ? ` · ${entry.details.note}` : ""}
                    </p>
                    <p className="text-xs text-[#667085]">
                      {format.dateTime(new Date(entry.created_at), { dateStyle: "medium", timeStyle: "short" })}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className={`font-semibold ${entry.amount >= 0 ? "text-[#067647]" : "text-[#101323]"}`}>
                      {entry.amount >= 0 ? "+" : "−"}
                      {formatRub(Math.abs(entry.amount))}
                    </p>
                    <p className="text-xs text-[#667085]">{formatRub(entry.balance_after)}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
