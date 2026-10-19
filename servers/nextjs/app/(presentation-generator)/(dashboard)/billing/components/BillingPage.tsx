"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { CheckCircle2, CreditCard, Loader2, Wallet, XCircle, Clock } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import { ErrorBox, GradientButton, SoftButton, errorMessage } from "@/components/studio/controls";
import { isPaying, useBilling } from "@/components/billing/useBilling";
import {
  BillingApi,
  formatRub,
  studioMinPrice,
  type BillingEntry,
  type BillingMe,
  type BillingPayment,
} from "../../../services/api/billing";
import { StudioApi, type StudioModel } from "../../../services/api/studio";
import { notifyBillingChanged } from "@/utils/billingEvents";

const card = "rounded-[20px] border border-[#E7E9F2] bg-white p-5 md:p-6";
const h2 = "font-syne text-base font-semibold text-[#191919]";
const input =
  "h-11 w-full rounded-lg border border-gray-300 px-3 text-sm text-[#191919] outline-none transition-colors focus:border-[#03B015]";

type ReturnState = { invoice: string; status: "checking" | "completed" | "failed" | "pending"; amount?: number };

export default function BillingPage() {
  const t = useTranslations("billing");
  const { me, loading, refresh, setMe } = useBilling();
  const [models, setModels] = useState<StudioModel[]>([]);
  const [history, setHistory] = useState<{ entries: BillingEntry[]; payments: BillingPayment[] } | null>(null);
  const [returned, setReturned] = useState<ReturnState | null>(null);

  const loadHistory = useCallback(() => {
    BillingApi.history()
      .then(setHistory)
      .catch(() => setHistory({ entries: [], payments: [] }));
  }, []);

  useEffect(() => {
    StudioApi.config()
      .then((config) => setModels(config.models))
      .catch(() => setModels([]));
  }, []);

  useEffect(() => {
    if (isPaying(me)) loadHistory();
  }, [me?.enabled, me?.free, me?.balance, loadHistory]); // eslint-disable-line react-hooks/exhaustive-deps

  // Back from the YooKassa page: ?payment=<invoice>. The webhook may lag, so ask a few times.
  useEffect(() => {
    const invoice = new URLSearchParams(window.location.search).get("payment");
    if (!invoice) return;
    let alive = true;
    setReturned({ invoice, status: "checking" });
    (async () => {
      for (let attempt = 0; attempt < 10 && alive; attempt += 1) {
        try {
          const result = await BillingApi.checkPayment(invoice);
          if (result.status !== "pending") {
            if (!alive) return;
            setReturned({ invoice, status: result.status, amount: result.amount });
            notifyBillingChanged();
            break;
          }
        } catch {
          break;
        }
        await new Promise((resolve) => setTimeout(resolve, 2000));
        if (attempt === 9 && alive) setReturned({ invoice, status: "pending" });
      }
      const url = new URL(window.location.href);
      url.searchParams.delete("payment");
      window.history.replaceState({}, "", url.toString());
    })();
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="min-h-screen bg-white font-syne">
      <header className="mx-4 flex flex-wrap items-center justify-between gap-3 border-b border-[#EDEEEF] px-1 py-4 md:ml-7 md:mr-[9px] md:min-h-[105px]">
        <h1 className="text-[22px] font-medium tracking-[-0.66px] text-[#101323]">{t("title")}</h1>
        <LanguageSwitcher size="md" />
      </header>

      <main className="mx-4 flex flex-col gap-5 py-6 md:ml-7 md:mr-[9px]">
        {returned && <ReturnBanner state={returned} />}
        {loading && !me ? (
          <p className="flex items-center gap-2 text-sm text-[#667085]">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            {t("loading")}
          </p>
        ) : !me?.enabled ? (
          <p className={`${card} text-sm text-[#4C5554]`}>{t("disabled")}</p>
        ) : (
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_400px]">
            <div className="flex min-w-0 flex-col gap-5">
              <BalanceCard me={me} />
              {!me.free && <TopupCard me={me} />}
              {!me.free && <AutoTopupCard me={me} onSaved={(next) => setMe({ ...me, ...next })} onChanged={refresh} />}
              {!me.free && <HistoryCard history={history} models={models} />}
            </div>
            <PricesCard me={me} models={models} />
          </div>
        )}
      </main>
    </div>
  );
}

function ReturnBanner({ state }: { state: ReturnState }) {
  const t = useTranslations("billing.return");
  const view = {
    checking: { icon: Loader2, tone: "border-[#E7E9F2] bg-[#F8F8FA] text-[#4C5554]", text: t("checking"), spin: true },
    completed: { icon: CheckCircle2, tone: "border-[#ABEFC6] bg-[#ECFDF3] text-[#067647]", text: t("completed", { amount: formatRub(state.amount ?? 0) }), spin: false },
    failed: { icon: XCircle, tone: "border-[#FECDCA] bg-[#FEF3F2] text-[#B42318]", text: t("failed"), spin: false },
    pending: { icon: Clock, tone: "border-[#FEDF89] bg-[#FFFAEB] text-[#B54708]", text: t("pending"), spin: false },
  }[state.status];
  const Icon = view.icon;
  return (
    <p role="status" className={`flex items-center gap-2 rounded-[14px] border px-4 py-3 text-sm ${view.tone}`}>
      <Icon className={`h-4 w-4 shrink-0 ${view.spin ? "animate-spin" : ""}`} aria-hidden="true" />
      {view.text}
    </p>
  );
}

function BalanceCard({ me }: { me: BillingMe }) {
  const t = useTranslations("billing");
  return (
    <section className={`${card} flex items-center gap-4`} aria-label={t("balance")}>
      <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-[#F4FEF5]">
        <Wallet className="h-6 w-6 text-[#02940F]" aria-hidden="true" />
      </span>
      <div>
        <p className="text-sm text-[#667085]">{t("balance")}</p>
        {me.free ? (
          <p className="text-lg font-medium text-[#101323]">{t("freeForAdmins")}</p>
        ) : (
          <p className="text-[32px] font-semibold leading-tight tracking-[-0.5px] text-[#101323]">{formatRub(me.balance ?? 0)}</p>
        )}
      </div>
    </section>
  );
}

function TopupCard({ me }: { me: BillingMe }) {
  const t = useTranslations("billing.topup");
  const [amount, setAmount] = useState(me.topup_amounts[1] ?? me.topup_amounts[0]);
  const [email, setEmail] = useState(me.receipt_email ?? "");
  const [saveCard, setSaveCard] = useState(false);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The cheapest image of the first model users see.
  const perImage = Object.keys(me.prices.studio)
    .map((key) => studioMinPrice(me.prices.studio, key))
    .find((value) => value != null) ?? undefined;

  const pay = async () => {
    setError(null);
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(email.trim())) {
      setError(t("emailInvalid"));
      return;
    }
    if (saveCard && !consent) {
      setError(t("consentRequired"));
      return;
    }
    setBusy(true);
    try {
      const created = await BillingApi.topup({ amount, email: email.trim(), save_card: saveCard, consent });
      window.location.assign(created.confirmation_url);
    } catch (reason) {
      setError(errorMessage(reason, t("failed")));
      setBusy(false);
    }
  };

  return (
    <section id="topup" className={`${card} scroll-mt-6`} aria-labelledby="topup-title">
      <h2 id="topup-title" className={h2}>{t("title")}</h2>
      {!me.payments_available ? (
        <p className="mt-3 text-sm leading-6 text-[#4C5554]">{t("unavailable")}</p>
      ) : (
        <div className="mt-4 flex flex-col gap-4">
          <div role="radiogroup" aria-label={t("amount")} className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {me.topup_amounts.map((value) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={amount === value}
                onClick={() => setAmount(value)}
                className={[
                  "flex flex-col items-start rounded-[14px] border px-3 py-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#03B015]",
                  amount === value ? "border-[#03B015] bg-[#F4FEF5]" : "border-[#E7E9F2] hover:bg-[#F8F8FA]",
                ].join(" ")}
              >
                <span className="text-base font-semibold text-[#101323]">{formatRub(value)}</span>
                <span className="mt-0.5 text-[11px] leading-4 text-[#667085]">
                  {me.prices.per_slide > 0 && t("slides", { count: Math.floor(value / me.prices.per_slide) })}
                  {perImage ? <><br />{t("images", { count: Math.floor(value / perImage) })}</> : null}
                </span>
              </button>
            ))}
          </div>
          <div>
            <label htmlFor="receipt-email" className="mb-1.5 block text-sm font-medium text-[#4C5554]">{t("email")}</label>
            <input
              id="receipt-email"
              type="email"
              autoComplete="email"
              className={input}
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="name@example.com"
            />
            <p className="mt-1 text-xs text-[#667085]">{t("emailHint")}</p>
          </div>
          <label className="flex items-start gap-2 text-sm text-[#191919]">
            <input type="checkbox" className="mt-1 h-4 w-4 accent-[#03B015]" checked={saveCard} onChange={(event) => setSaveCard(event.target.checked)} />
            <span>{t("saveCard")}</span>
          </label>
          {saveCard && (
            <label className="flex items-start gap-2 rounded-[12px] bg-[#F8F8FA] p-3 text-xs leading-5 text-[#4C5554]">
              <input type="checkbox" className="mt-0.5 h-4 w-4 accent-[#03B015]" checked={consent} onChange={(event) => setConsent(event.target.checked)} />
              <span>
                {t("consent")}{" "}
                {me.offer_url && (
                  <a href={me.offer_url} target="_blank" rel="noopener noreferrer" className="font-medium text-[#02940F] underline">
                    {t("offer")}
                  </a>
                )}
              </span>
            </label>
          )}
          <ErrorBox error={error} />
          <div className="sm:max-w-[320px]">
            <GradientButton busy={busy} onClick={() => void pay()}>
              {t("pay", { amount: formatRub(amount) })}
            </GradientButton>
          </div>
          <p className="text-xs text-[#667085]">{t("yookassaHint")}</p>
        </div>
      )}
    </section>
  );
}

function AutoTopupCard({
  me,
  onSaved,
  onChanged,
}: {
  me: BillingMe;
  onSaved: (next: Partial<BillingMe>) => void;
  onChanged: () => void;
}) {
  const t = useTranslations("billing.auto");
  const auto = me.auto_topup;
  const [enabled, setEnabled] = useState(auto?.enabled ?? false);
  const [threshold, setThreshold] = useState(auto?.threshold ?? 50);
  const [amount, setAmount] = useState(auto?.amount ?? 500);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setEnabled(auto?.enabled ?? false);
  }, [auto?.enabled]);

  if (!auto) return null;
  const [tMin, tMax] = auto.threshold_range;
  const [aMin, aMax] = auto.amount_range;

  const save = async () => {
    setError(null);
    setSaved(false);
    if (threshold < tMin || threshold > tMax || amount < aMin || amount > aMax) {
      setError(t("outOfRange", { tMin, tMax, aMin, aMax }));
      return;
    }
    setBusy(true);
    try {
      onSaved(await BillingApi.setAutoTopup({ enabled, threshold, amount }));
      setSaved(true);
    } catch (reason) {
      setError(errorMessage(reason, t("failed")));
    } finally {
      setBusy(false);
    }
  };

  const forget = async () => {
    setBusy(true);
    try {
      await BillingApi.forgetCard();
      onChanged();
    } catch (reason) {
      setError(errorMessage(reason, t("failed")));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className={card} aria-labelledby="auto-title">
      <h2 id="auto-title" className={h2}>{t("title")}</h2>
      {!me.card ? (
        <p className="mt-3 text-sm leading-6 text-[#4C5554]">{t("noCard")}</p>
      ) : (
        <div className="mt-4 flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-[12px] bg-[#F8F8FA] px-4 py-3">
            <span className="flex items-center gap-2 text-sm text-[#191919]">
              <CreditCard className="h-4 w-4 text-[#02940F]" aria-hidden="true" />
              {t("card", { type: me.card.type || t("cardGeneric"), last4: me.card.last4 || "••••" })}
            </span>
            <button type="button" onClick={() => void forget()} disabled={busy} className="text-sm font-medium text-[#B42318] hover:underline disabled:opacity-60">
              {t("forget")}
            </button>
          </div>
          <label className="flex items-center gap-2 text-sm text-[#191919]">
            <input type="checkbox" className="h-4 w-4 accent-[#03B015]" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
            {t("enable")}
          </label>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label htmlFor="auto-threshold" className="mb-1.5 block text-sm font-medium text-[#4C5554]">{t("threshold")}</label>
              <input id="auto-threshold" type="number" inputMode="numeric" min={tMin} max={tMax} className={input} value={threshold} onChange={(event) => setThreshold(Number(event.target.value))} />
              <p className="mt-1 text-xs text-[#667085]">{t("range", { min: formatRub(tMin), max: formatRub(tMax) })}</p>
            </div>
            <div>
              <label htmlFor="auto-amount" className="mb-1.5 block text-sm font-medium text-[#4C5554]">{t("amount")}</label>
              <input id="auto-amount" type="number" inputMode="numeric" min={aMin} max={aMax} className={input} value={amount} onChange={(event) => setAmount(Number(event.target.value))} />
              <p className="mt-1 text-xs text-[#667085]">{t("range", { min: formatRub(aMin), max: formatRub(aMax) })}</p>
            </div>
          </div>
          <p className="text-xs leading-5 text-[#667085]">{t("rules")}</p>
          <ErrorBox error={error} />
          {saved && <p role="status" className="text-sm text-[#067647]">{t("saved")}</p>}
          <div className="sm:max-w-[240px]">
            <SoftButton busy={busy} onClick={() => void save()}>{t("save")}</SoftButton>
          </div>
        </div>
      )}
    </section>
  );
}

function useEntryLabel(models: StudioModel[]) {
  const t = useTranslations("billing.history");
  const titles = useMemo(() => Object.fromEntries(models.map((model) => [model.key, model.title])), [models]);
  return (entry: BillingEntry): string => {
    const details = entry.details || {};
    const model = details.model ? titles[details.model] || details.model : "";
    const what = (reason: string) => {
      switch (reason) {
        case "presentation":
          return t("presentation", { count: Number(details.slides) || 0 });
        case "studio.generate":
          return t("studioGenerate", { model });
        case "studio.edit":
          return t("studioEdit", { model });
        case "studio.storyboard":
          return t("studioStoryboard", { model });
        default:
          return reason;
      }
    };
    switch (entry.kind) {
      case "bonus":
        return t("bonus");
      case "topup":
        return t("topup");
      case "auto_topup":
        return t("autoTopup");
      case "admin":
        return details.note ? t("adminNote", { note: details.note }) : t("admin");
      case "refund":
        return t("refund", { what: what(entry.reason) });
      default:
        return what(entry.reason);
    }
  };
}

function HistoryCard({
  history,
  models,
}: {
  history: { entries: BillingEntry[]; payments: BillingPayment[] } | null;
  models: StudioModel[];
}) {
  const t = useTranslations("billing.history");
  const format = useFormatter();
  const label = useEntryLabel(models);
  const pending = history?.payments.filter((payment) => payment.status === "pending") ?? [];

  return (
    <section className={card} aria-labelledby="history-title">
      <h2 id="history-title" className={h2}>{t("title")}</h2>
      {pending.length > 0 && (
        <ul className="mt-3 flex flex-col gap-1">
          {pending.map((payment) => (
            <li key={payment.invoice_id} className="flex items-center gap-2 text-xs text-[#B54708]">
              <Clock className="h-3.5 w-3.5" aria-hidden="true" />
              {t("paymentPending", { amount: formatRub(payment.amount) })}
            </li>
          ))}
        </ul>
      )}
      {!history ? (
        <p className="mt-3 text-sm text-[#667085]">{t("loading")}</p>
      ) : history.entries.length === 0 ? (
        <p className="mt-3 text-sm text-[#667085]">{t("empty")}</p>
      ) : (
        <ul className="mt-3 divide-y divide-[#F2F4F7]">
          {history.entries.map((entry) => (
            <li key={entry.id} className="flex items-start justify-between gap-3 py-2.5">
              <div className="min-w-0">
                <p className="text-sm text-[#191919]">{label(entry)}</p>
                <p className="text-xs text-[#667085]">
                  {format.dateTime(new Date(entry.created_at), { dateStyle: "medium", timeStyle: "short" })}
                  {entry.pending && <> · {t("pending")}</>}
                  {entry.refunded && <> · {t("refunded")}</>}
                </p>
              </div>
              <div className="shrink-0 text-right">
                <p className={`text-sm font-semibold ${entry.amount >= 0 ? "text-[#067647]" : "text-[#101323]"}`}>
                  {entry.amount >= 0 ? "+" : "−"}
                  {formatRub(Math.abs(entry.amount))}
                </p>
                <p className="text-xs text-[#667085]">{t("after", { amount: formatRub(entry.balance_after) })}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function PricesCard({ me, models }: { me: BillingMe; models: StudioModel[] }) {
  const t = useTranslations("billing.prices");
  const tq = useTranslations("studio.quality");
  return (
    <section className={`${card} h-fit lg:sticky lg:top-6`} aria-labelledby="prices-title">
      <h2 id="prices-title" className={h2}>{t("title")}</h2>
      {me.free && <p className="mt-2 text-xs text-[#667085]">{t("freeNote")}</p>}
      <dl className="mt-4 flex flex-col gap-3 text-sm">
        <div className="rounded-[12px] bg-[#F8F8FA] p-3">
          <dt className="font-medium text-[#191919]">{t("presentation")}</dt>
          <dd className="mt-0.5 text-[#4C5554]">{t("perSlide", { amount: formatRub(me.prices.per_slide) })}</dd>
        </div>
        {models.map((model) => {
          const units = me.prices.studio[model.key]?.units;
          if (!units || !Object.keys(units).length) return null;
          const items = Object.entries(units).map(([option, unit]) => {
            const [resolution, quality] = option.split("|");
            const qualityLabel = quality ? (tq.has(quality) ? tq(quality) : quality) : "";
            const label = [resolution, qualityLabel].filter(Boolean).join(", ") || t("perImage");
            return `${label} — ${formatRub(Math.max(1, Math.ceil(unit)))}`;
          });
          return (
            <div key={model.key} className="rounded-[12px] bg-[#F8F8FA] p-3">
              <dt className="font-medium text-[#191919]">{model.title}</dt>
              <dd className="mt-0.5 text-[#4C5554]">{items.join(" · ")}</dd>
            </div>
          );
        })}
      </dl>
      <p className="mt-3 text-xs leading-5 text-[#667085]">{t("note")}</p>
    </section>
  );
}
