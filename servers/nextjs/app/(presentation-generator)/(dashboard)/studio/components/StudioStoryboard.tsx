"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Brush, Download, Loader2, RotateCcw, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { withPrice } from "@/components/studio/price";
import { ImagesApi } from "../../../services/api/images";
import { StudioApi, type StoryboardView, type StudioImage } from "../../../services/api/studio";
import StudioHeader from "./StudioHeader";
import StudioHistory from "./StudioHistory";
import StudioNotice from "./StudioNotice";
import ImageDropZone, { useImageFile, usePastedImage } from "./ImageDropZone";
import { useStudio } from "./useStudio";
import {
  ChipGroup,
  ErrorBox,
  FieldLabel,
  FormCard,
  GradientButton,
  ModelSelect,
  PromptField,
  errorMessage,
  imageSrc,
} from "@/components/studio/controls";

// arckep runs up to 5 jobs per key; leave room for the rest of the Studio.
const PARALLEL_VIEWS = 3;
const GROUPS: StoryboardView["group"][] = ["portrait", "full_body", "special"];

type ViewResult =
  | { status: "queued" | "running" }
  | { status: "done"; image: StudioImage }
  | { status: "failed"; error: string };

async function dataUrlToFile(dataUrl: string, name: string): Promise<File> {
  const blob = await (await fetch(dataUrl)).blob();
  const type = blob.type || "image/png";
  return new File([blob], `${name}.${type.split("/")[1] || "png"}`, { type });
}

export default function StudioStoryboard({ isAdmin, initialImage }: { isAdmin: boolean; initialImage: string | null }) {
  const t = useTranslations("studio");
  const { config, configError, history, historyLoading, addImages, removeImage } = useStudio();

  const [reference, setReference] = useState<string | null>(initialImage);
  const [selected, setSelected] = useState<string[]>(["front", "three_quarter_left", "profile_left", "back"]);
  const [modelKey, setModelKey] = useState("");
  const [resolution, setResolution] = useState("1K");
  const [details, setDetails] = useState("");
  const [results, setResults] = useState<Record<string, ViewResult>>({});
  const [order, setOrder] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const uploadedRef = useRef<{ dataUrl: string; path: string } | null>(null);

  const views = useMemo(() => config?.storyboard_views ?? [], [config]);
  // As in the standalone Studio: Gemini keeps the subject's identity across views.
  const models = useMemo(() => (config?.models ?? []).filter((item) => item.family === "gemini"), [config]);
  const model = models.find((item) => item.key === modelKey) ?? models[0];

  useEffect(() => {
    if (config && !modelKey && models.length) {
      const preferred = models.find((item) => item.tags.includes("best")) ?? models[0];
      setModelKey(preferred.key);
    }
  }, [config, modelKey, models]);

  useEffect(() => {
    if (model?.resolutions.length && !model.resolutions.includes(resolution)) setResolution(model.resolutions[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [model?.key]);

  const loadReference = useImageFile(
    (dataUrl) => {
      setReference(dataUrl);
      setError(null);
    },
    setError,
  );
  usePastedImage((file) => loadReference(file), !running);

  /** The views call the server once per view: send a stored picture, not the file each time. */
  const referencePath = useCallback(async (): Promise<string> => {
    if (!reference) throw new Error(t("errors.storyboardReferenceRequired"));
    if (!reference.startsWith("data:")) return reference;
    if (uploadedRef.current?.dataUrl === reference) return uploadedRef.current.path;
    const asset = await ImagesApi.uploadImage(await dataUrlToFile(reference, "storyboard-reference"));
    if (!asset?.file_url) throw new Error(t("errors.requestFailed"));
    uploadedRef.current = { dataUrl: reference, path: asset.file_url };
    return asset.file_url;
  }, [reference, t]);

  const runViews = useCallback(
    async (viewIds: string[]) => {
      if (!model || !viewIds.length) return;
      setRunning(true);
      setError(null);
      let image: string;
      try {
        image = await referencePath();
      } catch (reason) {
        setError(errorMessage(reason, t("errors.requestFailed")));
        setRunning(false);
        return;
      }
      setResults((current) => {
        const next = { ...current };
        for (const id of viewIds) next[id] = { status: "queued" };
        return next;
      });
      setOrder((current) => [...current.filter((id) => !viewIds.includes(id)), ...viewIds]);

      const queue = [...viewIds];
      const worker = async () => {
        for (let id = queue.shift(); id; id = queue.shift()) {
          const view = id;
          setResults((current) => ({ ...current, [view]: { status: "running" } }));
          try {
            const result = await StudioApi.storyboard({
              image,
              view,
              model: model.key,
              ...(model.resolutions.includes(resolution) ? { resolution } : {}),
              ...(details.trim() ? { details: details.trim() } : {}),
            });
            setResults((current) => ({ ...current, [view]: { status: "done", image: result } }));
            addImages([result]);
          } catch (reason) {
            setResults((current) => ({
              ...current,
              [view]: { status: "failed", error: errorMessage(reason, t("errors.requestFailed")) },
            }));
          }
        }
      };
      await Promise.all(Array.from({ length: Math.min(PARALLEL_VIEWS, viewIds.length) }, worker));
      setRunning(false);
    },
    [addImages, details, model, referencePath, resolution, t],
  );

  const toggle = (id: string) =>
    setSelected((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));

  const title = t("pages.storyboard");
  if (configError || (config && !config.configured)) {
    return (
      <div className="min-h-screen font-syne">
        <StudioHeader title={title} isAdmin={isAdmin} active="storyboard" />
        <StudioNotice isAdmin={isAdmin} error={configError} />
      </div>
    );
  }

  const ordered = views.filter((view) => selected.includes(view.id)).map((view) => view.id);
  const shown = order.filter((id) => results[id]);
  const doneCount = shown.filter((id) => results[id]?.status === "done").length;

  return (
    <div className="min-h-screen">
      <StudioHeader title={title} isAdmin={isAdmin} active="storyboard" />
      <main className="mx-4 flex flex-col gap-6 px-1 pb-10 pt-7 md:ml-7 md:mr-[9px] lg:flex-row lg:items-start">
        <div className="flex min-w-0 flex-1 flex-col gap-6">
          <section aria-labelledby="storyboard-reference" className="flex flex-col gap-3">
            <h2 id="storyboard-reference" className="font-syne text-[15px] font-medium text-[#191919]">
              {t("storyboard.referenceTitle")}
            </h2>
            {reference ? (
              <div className="flex flex-wrap items-start gap-4 rounded-2xl border border-[#EDEEEF] bg-[#F9F8FB] p-4">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={imageSrc(reference)}
                  alt={t("storyboard.referenceAlt")}
                  className="max-h-64 max-w-full rounded-xl border border-[#EDEEEF] bg-white object-contain"
                />
                <div className="flex min-w-[180px] flex-1 flex-col gap-2 text-sm leading-6 text-[#475467]">
                  <p>{t("storyboard.referenceHint")}</p>
                  <button
                    type="button"
                    onClick={() => setReference(null)}
                    disabled={running}
                    className="inline-flex min-h-9 w-fit items-center gap-1.5 rounded-full border border-[#EDEEEF] bg-white px-3.5 font-syne text-[13px] text-[#2C2B37] hover:text-red-600 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7A5AF8]"
                  >
                    <X className="h-3.5 w-3.5" aria-hidden="true" />
                    {t("storyboard.removeReference")}
                  </button>
                </div>
              </div>
            ) : (
              <ImageDropZone title={t("storyboard.dropTitle")} hint={t("storyboard.dropHint")} onFile={loadReference} />
            )}
          </section>

          {shown.length > 0 && (
            <section aria-labelledby="storyboard-results" className="flex flex-col gap-3">
              <h2 id="storyboard-results" className="font-syne text-[15px] font-medium text-[#191919]">
                {t("storyboard.resultsTitle")}
                <span className="ml-1.5 text-[#98A2B3]">
                  {doneCount}/{shown.length}
                </span>
              </h2>
              <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                {shown.map((id) => {
                  const result = results[id];
                  const label = t(`views.${id}`);
                  return (
                    <li key={id} className="flex flex-col overflow-hidden rounded-xl border border-[#EDEEEF] bg-white">
                      <div className="flex aspect-square items-center justify-center bg-[#F6F6F9]">
                        {result.status === "done" ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={imageSrc(result.image.file_url)} alt={label} className="h-full w-full object-contain" />
                        ) : result.status === "failed" ? (
                          <p role="alert" className="px-3 text-center text-xs leading-5 text-red-700">
                            {result.error}
                          </p>
                        ) : (
                          <span className="flex flex-col items-center gap-2 text-xs text-[#667085]" role="status">
                            <Loader2 className={`h-5 w-5 text-[#7A5AF8] ${result.status === "running" ? "animate-spin" : ""}`} aria-hidden="true" />
                            {result.status === "running" ? t("storyboard.running") : t("storyboard.queued")}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center justify-between gap-2 px-3 py-2">
                        <span className="truncate font-syne text-xs font-medium text-[#344054]">{label}</span>
                        <span className="flex shrink-0 items-center gap-1">
                          {result.status === "done" && (
                            <>
                              <a
                                href={imageSrc(result.image.file_url)}
                                download
                                aria-label={t("storyboard.downloadView", { view: label })}
                                title={t("actions.download")}
                                className="flex h-8 w-8 items-center justify-center rounded-full text-[#475467] hover:bg-[#F4F3FF] hover:text-[#5141E5] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7A5AF8]"
                              >
                                <Download className="h-4 w-4" aria-hidden="true" />
                              </a>
                              <Link
                                href={`/studio/brush?image=${encodeURIComponent(result.image.file_url)}`}
                                aria-label={t("storyboard.editView", { view: label })}
                                title={t("actions.toBrush")}
                                className="flex h-8 w-8 items-center justify-center rounded-full text-[#475467] hover:bg-[#F4F3FF] hover:text-[#5141E5] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7A5AF8]"
                              >
                                <Brush className="h-4 w-4" aria-hidden="true" />
                              </Link>
                            </>
                          )}
                          {result.status === "failed" && (
                            <button
                              type="button"
                              onClick={() => void runViews([id])}
                              disabled={running}
                              aria-label={t("storyboard.retryView", { view: label })}
                              title={t("storyboard.retry")}
                              className="flex h-8 w-8 items-center justify-center rounded-full text-[#475467] hover:bg-[#F4F3FF] hover:text-[#5141E5] disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7A5AF8]"
                            >
                              <RotateCcw className="h-4 w-4" aria-hidden="true" />
                            </button>
                          )}
                        </span>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>
          )}

          <StudioHistory
            items={history}
            loading={historyLoading}
            selectedUrl={reference}
            onPick={(item) => {
              setReference(item.file_url);
              setError(null);
              window.scrollTo({ top: 0, behavior: "smooth" });
            }}
            onRemove={async (item) => {
              await removeImage(item.id);
              if (reference === item.file_url) setReference(null);
            }}
          />
        </div>

        <FormCard title={t("storyboard.title")} subtitle={t("storyboard.subtitle")}>
          <div className="flex flex-col gap-4 px-[22px] pt-[18px]">
            {GROUPS.map((group) => {
              const groupViews = views.filter((view) => view.group === group);
              if (!groupViews.length) return null;
              return (
                <div key={group} className="flex flex-col gap-2">
                  <FieldLabel>{t(`viewGroups.${group}`)}</FieldLabel>
                  <div role="group" aria-label={t(`viewGroups.${group}`)} className="grid grid-cols-2 gap-2">
                    {groupViews.map((view) => {
                      const on = selected.includes(view.id);
                      return (
                        <button
                          key={view.id}
                          type="button"
                          aria-pressed={on}
                          onClick={() => toggle(view.id)}
                          disabled={running}
                          className={[
                            "min-h-9 rounded-xl border px-2.5 text-left font-syne text-[12px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7A5AF8] disabled:opacity-60",
                            on
                              ? "border-[#CEC6FF] bg-[#F4F3FF] font-semibold text-[#5141E5]"
                              : "border-[#DBDBE1] bg-white text-[#2C2B37] hover:border-[#CEC6FF]",
                          ].join(" ")}
                        >
                          {t(`views.${view.id}`)}
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
            <div className="flex flex-wrap gap-3 text-[13px]">
              <button
                type="button"
                onClick={() => setSelected(views.map((view) => view.id))}
                disabled={running}
                className="font-syne font-semibold text-[#5146E5] hover:text-[#3B2FC9] disabled:opacity-50"
              >
                {t("storyboard.selectAll")}
              </button>
              <button
                type="button"
                onClick={() => setSelected([])}
                disabled={running}
                className="font-syne font-semibold text-[#5146E5] hover:text-[#3B2FC9] disabled:opacity-50"
              >
                {t("storyboard.clearAll")}
              </button>
            </div>
          </div>
          <div className="mt-[18px]">
            <PromptField
              id="storyboard-details"
              label={t("storyboard.detailsLabel")}
              optional={t("fields.optional")}
              value={details}
              onChange={setDetails}
              placeholder={t("storyboard.detailsPlaceholder")}
              rows={2}
            />
          </div>
          {model ? (
            <div className="flex flex-col gap-4 px-[22px] pb-[22px] pt-[18px]">
              <ModelSelect id="storyboard-model" models={models} value={model.key} onChange={setModelKey} />
              {model.resolutions.length > 1 && (
                <ChipGroup label={t("fields.resolution")} options={model.resolutions} value={resolution} onChange={setResolution} />
              )}
              <ErrorBox error={error} />
              <GradientButton busy={running} disabled={!reference || !ordered.length} onClick={() => void runViews(ordered)}>
                {running
                  ? t("storyboard.generating")
                  : withPrice(t("storyboard.submit", { count: ordered.length }), config, model, { resolution, times: ordered.length })}
              </GradientButton>
              <p className="text-center text-xs leading-5 text-[#667085]">
                {!reference ? t("storyboard.needReference") : t("storyboard.oneRequestPerView")}
              </p>
            </div>
          ) : (
            <p className="px-[22px] py-6 text-sm text-[#667085]">{t("loading")}</p>
          )}
        </FormCard>
      </main>
    </div>
  );
}
