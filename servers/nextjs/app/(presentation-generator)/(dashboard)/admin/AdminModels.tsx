"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronDown, Images, Loader2, RefreshCw, Search } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { errorMessage } from "@/components/studio/controls";
import { formatRub } from "../../services/api/billing";
import type { StudioModelMode } from "../../services/api/studio";
import {
  StudioAdminApi,
  type AdminStudioModel,
  type AdminStudioModels,
  type StudioModelSettings,
} from "../../services/api/studioAdmin";

const inputClass =
  "h-10 rounded-lg border border-[#EDEEEF] bg-white px-3 text-sm text-[#101323] outline-none focus:border-[#03B015]";
const smallInput =
  "h-8 w-20 rounded-md border border-[#EDEEEF] bg-white px-2 text-xs text-[#101323] outline-none focus:border-[#03B015]";

type Draft = Record<string, StudioModelSettings>;

function draftFrom(state: AdminStudioModels): Draft {
  const draft: Draft = {};
  for (const model of state.models) {
    draft[model.key] = {
      enabled: model.enabled,
      title: model.title,
      order: model.order,
      modes: model.modes,
      tags: model.tags,
      ...(model.markup ? { markup: model.markup } : {}),
      ...(Object.keys(model.manual_costs).length ? { costs: model.manual_costs } : {}),
    };
  }
  return draft;
}

/** Administrators: which Studio image models users see, names, modes and prices. */
export default function AdminModels() {
  const t = useTranslations("adminModels");
  const tq = useTranslations("studio.quality");
  const format = useFormatter();
  const [state, setState] = useState<AdminStudioModels | null>(null);
  const [draft, setDraft] = useState<Draft>({});
  const [defaultModel, setDefaultModel] = useState("");
  const [markup, setMarkup] = useState("1.45");
  const [slideModel, setSlideModel] = useState("");
  const [people, setPeople] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState<"load" | "save" | "catalog" | string | null>("load");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const apply = useCallback((value: AdminStudioModels) => {
    setState(value);
    setDraft(draftFrom(value));
    setDefaultModel(value.default_model);
    setMarkup(String(value.markup));
    setSlideModel(value.slide_image_model);
    setPeople(value.people_appearance);
  }, []);

  const run = useCallback(
    async (kind: string, action: () => Promise<AdminStudioModels | void>, fallback: string) => {
      setBusy(kind);
      setError(null);
      setSaved(false);
      try {
        const result = await action();
        if (result) apply(result);
        return true;
      } catch (reason) {
        setError(errorMessage(reason, fallback));
        return false;
      } finally {
        setBusy(null);
      }
    },
    [apply],
  );

  useEffect(() => {
    void run("load", () => StudioAdminApi.models(), t("loadFailed"));
  }, [run, t]);

  const enabledKeys = useMemo(
    () => Object.entries(draft).filter(([, item]) => item.enabled).map(([key]) => key),
    [draft],
  );
  const models = useMemo(() => {
    const words = query.trim().toLowerCase();
    return (state?.models ?? []).filter((model) => {
      if (!showAll && !draft[model.key]?.enabled) return false;
      if (!words) return true;
      return `${model.key} ${draft[model.key]?.title ?? ""} ${model.provider ?? ""}`.toLowerCase().includes(words);
    });
  }, [state, draft, showAll, query]);

  const update = (key: string, change: Partial<StudioModelSettings>) =>
    setDraft((current) => ({ ...current, [key]: { ...current[key], ...change } }));

  const toggleMode = (model: AdminStudioModel, mode: StudioModelMode) => {
    const modes = draft[model.key]?.modes ?? [];
    update(model.key, {
      modes: modes.includes(mode) ? modes.filter((item) => item !== mode) : [...modes, mode],
    });
  };

  const setManualCost = (key: string, option: string, value: string) => {
    const costs = { ...(draft[key]?.costs ?? {}) };
    const number = Number(value.replace(",", "."));
    if (value.trim() === "" || !(number > 0)) delete costs[option];
    else costs[option] = number;
    update(key, { costs });
  };

  const save = async () => {
    const value = Number(markup.replace(",", "."));
    if (!(value > 0)) {
      setError(t("markupInvalid"));
      return;
    }
    const ok = await run(
      "save",
      () =>
        StudioAdminApi.save({
          default_model: defaultModel,
          markup: value,
          slide_image_model: slideModel,
          people_appearance: people.trim(),
          models: draft,
        }),
      t("saveFailed"),
    );
    if (ok) setSaved(true);
  };

  const estimate = async (key: string) => {
    await run(
      `estimate:${key}`,
      async () => {
        const row = await StudioAdminApi.estimate(key);
        setState((current) =>
          current ? { ...current, models: current.models.map((model) => (model.key === key ? row : model)) } : current,
        );
      },
      t("estimateFailed"),
    );
  };

  const optionLabel = (resolution: string | null, quality: string | null) =>
    [resolution, quality ? (tq.has(quality) ? tq(quality) : quality) : null].filter(Boolean).join(", ") || t("anyOption");

  if (!state) {
    return (
      <section className="rounded-[12px] border border-[#EDEEEF] bg-white p-6 text-sm text-[#667085]">
        {busy === "load" ? <Loader2 className="h-4 w-4 animate-spin" aria-label={t("loading")} /> : error}
      </section>
    );
  }

  const titleOf = (key: string) => draft[key]?.title || key;

  return (
    <div className="space-y-5">
      <section className="rounded-[12px] border border-[#EDEEEF] bg-white p-6">
        <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#F4FEF5]">
              <Images className="h-4 w-4 text-[#02940F]" aria-hidden="true" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-[#101323]">{t("title")}</h2>
              <p className="mt-0.5 text-xs text-[#667085]">
                {state.catalog.source === "arckep" && state.catalog.fetched_at
                  ? t("catalogFrom", {
                      count: state.catalog.count,
                      date: format.dateTime(new Date(state.catalog.fetched_at * 1000), { dateStyle: "medium", timeStyle: "short" }),
                    })
                  : t("catalogSnapshot", { count: state.catalog.count })}
              </p>
              {state.catalog.error && <p className="mt-0.5 text-xs text-[#B42318]">{t("catalogError", { error: state.catalog.error })}</p>}
            </div>
          </div>
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => void run("catalog", () => StudioAdminApi.refreshCatalog(), t("catalogFailed"))}
            className="inline-flex h-9 items-center gap-2 rounded-full border border-[#EDEEEF] px-4 text-xs font-semibold text-[#344054] hover:bg-[#F9FAFB] disabled:opacity-60"
          >
            <RefreshCw className={`h-4 w-4 ${busy === "catalog" ? "animate-spin" : ""}`} aria-hidden="true" />
            {t("refreshCatalog")}
          </button>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <label className="flex flex-col gap-1.5 text-xs font-medium text-[#344054]">
            {t("defaultModel")}
            <select className={inputClass} value={defaultModel} onChange={(event) => setDefaultModel(event.target.value)}>
              {enabledKeys.map((key) => (
                <option key={key} value={key}>{titleOf(key)}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1.5 text-xs font-medium text-[#344054]">
            {t("markup")}
            <input className={inputClass} inputMode="decimal" value={markup} onChange={(event) => setMarkup(event.target.value)} />
            <span className="font-normal text-[#667085]">{t("markupHint")}</span>
          </label>
          <label className="flex flex-col gap-1.5 text-xs font-medium text-[#344054]">
            {t("slideModel")}
            <select className={inputClass} value={slideModel} onChange={(event) => setSlideModel(event.target.value)}>
              <option value="">{t("slideModelProvider")}</option>
              {state.models
                .filter((model) => model.supported_modes.includes("generate"))
                .map((model) => (
                  <option key={model.key} value={model.key}>{titleOf(model.key)}</option>
                ))}
            </select>
            <span className="font-normal text-[#667085]">{t("slideModelHint")}</span>
          </label>
          <label className="flex flex-col gap-1.5 text-xs font-medium text-[#344054] md:col-span-3">
            {t("people")}
            <input
              className={inputClass}
              maxLength={300}
              value={people}
              placeholder={t("peoplePlaceholder")}
              onChange={(event) => setPeople(event.target.value)}
            />
            <span className="font-normal text-[#667085]">{t("peopleHint")}</span>
          </label>
        </div>
      </section>

      <section className="overflow-hidden rounded-[12px] border border-[#EDEEEF] bg-white">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#EDEEEF] px-6 py-4">
          <div>
            <h2 className="text-sm font-semibold text-[#101323]">{t("listTitle", { enabled: enabledKeys.length, total: state.models.length })}</h2>
            <p className="mt-0.5 text-xs text-[#667085]">{t("listHint")}</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <label className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#98A2B3]" aria-hidden="true" />
              <input
                className={`${inputClass} h-9 w-48 pl-8 text-xs`}
                placeholder={t("search")}
                aria-label={t("search")}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
            <label className="flex items-center gap-2 text-xs text-[#344054]">
              <input type="checkbox" checked={showAll} onChange={(event) => setShowAll(event.target.checked)} />
              {t("showAll")}
            </label>
          </div>
        </div>

        <ul className="divide-y divide-[#EDEEEF]">
          {models.map((model) => {
            const item = draft[model.key];
            const expanded = open === model.key;
            const costs = Object.entries(model.costs);
            const prices = costs.map(([, cost]) => cost.price).filter((value): value is number => value != null);
            return (
              <li key={model.key} className="px-6 py-4">
                <div className="flex flex-wrap items-center gap-3">
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={item?.enabled ?? false}
                      onChange={(event) => update(model.key, { enabled: event.target.checked })}
                      aria-label={t("visible", { model: model.key })}
                    />
                  </label>
                  <input
                    className={`${inputClass} h-9 w-56`}
                    aria-label={t("displayName")}
                    value={item?.title ?? ""}
                    maxLength={80}
                    onChange={(event) => update(model.key, { title: event.target.value })}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-mono text-xs text-[#344054]">{model.key}</p>
                    <p className="truncate text-xs text-[#667085]">{model.provider} · {model.description}</p>
                  </div>
                  <span className="text-xs text-[#344054]">
                    {prices.length
                      ? t("priceFrom", { price: formatRub(Math.min(...prices)) })
                      : t("priceUnknown")}
                  </span>
                  <button
                    type="button"
                    aria-expanded={expanded}
                    onClick={() => setOpen(expanded ? null : model.key)}
                    className="inline-flex h-8 items-center gap-1 rounded-full border border-[#EDEEEF] px-3 text-xs font-semibold text-[#344054] hover:bg-[#F9FAFB]"
                  >
                    {t("details")}
                    <ChevronDown className={`h-3.5 w-3.5 transition ${expanded ? "rotate-180" : ""}`} aria-hidden="true" />
                  </button>
                </div>

                <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 pl-7 text-xs text-[#344054]">
                  {state.modes.map((mode) => {
                    const supported = model.supported_modes.includes(mode);
                    return (
                      <label key={mode} className={`flex items-center gap-1.5 ${supported ? "" : "opacity-40"}`} title={supported ? undefined : t("modeUnsupported")}>
                        <input
                          type="checkbox"
                          disabled={!supported}
                          checked={supported && (item?.modes ?? []).includes(mode)}
                          onChange={() => toggleMode(model, mode)}
                        />
                        {t(`modes.${mode}`)}
                      </label>
                    );
                  })}
                  <label className="flex items-center gap-1.5">
                    {t("order")}
                    <input
                      className={smallInput}
                      type="number"
                      value={item?.order ?? 0}
                      onChange={(event) => update(model.key, { order: Number(event.target.value) || 0 })}
                    />
                  </label>
                </div>

                {expanded && (
                  <div className="mt-4 space-y-3 rounded-[12px] bg-[#F8F8FA] p-4 text-xs text-[#344054]">
                    <div className="flex flex-wrap items-center gap-4">
                      <span>
                        {t("capabilities", {
                          aspects: model.aspect_ratios.join(", "),
                          count: model.max_count,
                          refs: model.max_references ?? "—",
                        })}
                      </span>
                      <label className="flex items-center gap-1.5">
                        {t("ownMarkup")}
                        <input
                          className={smallInput}
                          inputMode="decimal"
                          placeholder={markup}
                          value={item?.markup ?? ""}
                          onChange={(event) => {
                            const value = Number(event.target.value.replace(",", "."));
                            update(model.key, { markup: event.target.value.trim() && value > 0 ? value : undefined });
                          }}
                        />
                      </label>
                      <button
                        type="button"
                        disabled={busy !== null}
                        onClick={() => void estimate(model.key)}
                        className="inline-flex h-8 items-center gap-1.5 rounded-full border border-[#EDEEEF] bg-white px-3 font-semibold hover:bg-[#F9FAFB] disabled:opacity-60"
                      >
                        {busy === `estimate:${model.key}` && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />}
                        {t("askPrice")}
                      </button>
                    </div>
                    <table className="w-full text-left">
                      <thead className="text-[#667085]">
                        <tr>
                          <th className="py-1 font-medium">{t("option")}</th>
                          <th className="py-1 font-medium">{t("cost")}</th>
                          <th className="py-1 font-medium">{t("manualCost")}</th>
                          <th className="py-1 font-medium">{t("price")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {costs.map(([option, cost]) => (
                          <tr key={option} className="border-t border-[#EDEEEF]">
                            <td className="py-1.5">{optionLabel(cost.resolution, cost.quality)}</td>
                            <td className="py-1.5">
                              {cost.cost != null ? `${cost.cost} ₽` : "—"}
                              <span className="ml-1 text-[#98A2B3]">{t(`sources.${cost.source}`)}</span>
                            </td>
                            <td className="py-1.5">
                              <input
                                className={smallInput}
                                inputMode="decimal"
                                aria-label={t("manualCost")}
                                value={item?.costs?.[option] ?? ""}
                                onChange={(event) => setManualCost(model.key, option, event.target.value)}
                              />
                            </td>
                            <td className="py-1.5 font-semibold">{cost.price != null ? formatRub(cost.price) : "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <p className="text-[#667085]">{t("pricesHint")}</p>
                  </div>
                )}
              </li>
            );
          })}
          {models.length === 0 && <li className="px-6 py-6 text-sm text-[#667085]">{t("empty")}</li>}
        </ul>
      </section>

      <div className="sticky bottom-4 flex items-center justify-end gap-3 rounded-full border border-[#EDEEEF] bg-white/95 px-4 py-2 shadow-sm backdrop-blur">
        {error && <p role="alert" className="mr-auto text-sm text-[#B42318]">{error}</p>}
        {saved && !error && <p role="status" className="mr-auto text-sm text-[#067647]">{t("saved")}</p>}
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => void save()}
          className="inline-flex h-10 items-center justify-center gap-2 rounded-full bg-[#02940F] px-6 text-xs font-semibold text-white transition hover:bg-[#027A0E] disabled:opacity-60"
        >
          {busy === "save" && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
          {t("save")}
        </button>
      </div>
    </div>
  );
}
