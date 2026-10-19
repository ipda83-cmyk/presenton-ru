"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Brush, Clapperboard, Download, ImagePlus, Sparkles } from "lucide-react";
import { useTranslations } from "next-intl";
import { withPrice } from "@/components/studio/price";
import { StudioApi, type StudioImage, type StudioQuality } from "../../../services/api/studio";
import StudioHeader from "./StudioHeader";
import StudioHistory from "./StudioHistory";
import StudioNotice from "./StudioNotice";
import { useStudio } from "./useStudio";
import {
  BusyOverlay,
  ChipGroup,
  ErrorBox,
  FormCard,
  GradientButton,
  ModelSelect,
  PromptField,
  errorMessage,
  imageSrc,
} from "@/components/studio/controls";

const COUNTS = [1, 2, 3, 4] as const;
const PREFERRED_ASPECT = "16:9"; // slides are wide

const ratio = (aspect: string) => {
  const [width, height] = aspect.split(":").map(Number);
  return width && height ? width / height : 1;
};

/** The supported aspect ratio closest in shape to the wanted one. */
function closestAspect(wanted: string, options: string[]): string {
  return options.reduce((best, option) =>
    Math.abs(Math.log(ratio(option) / ratio(wanted))) < Math.abs(Math.log(ratio(best) / ratio(wanted))) ? option : best,
  );
}

const linkAction =
  "inline-flex min-h-9 items-center gap-1.5 rounded-full border border-[#DBDBE1] bg-white px-3.5 font-syne text-[13px] font-medium text-[#2C2B37] transition-colors hover:border-[#CDF8D1] hover:bg-[#FBFEFB] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#03B015]";

export default function StudioGenerate({ isAdmin }: { isAdmin: boolean }) {
  const t = useTranslations("studio");
  const { config, configError, history, historyLoading, addImages, removeImage } = useStudio();

  const [prompt, setPrompt] = useState("");
  const [modelKey, setModelKey] = useState("");
  const [aspect, setAspect] = useState(PREFERRED_ASPECT);
  const [resolution, setResolution] = useState("1K");
  const [quality, setQuality] = useState<StudioQuality>("medium");
  const [count, setCount] = useState<number>(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<StudioImage[]>([]);
  const [selected, setSelected] = useState<StudioImage | null>(null);

  const models = useMemo(() => (config?.models ?? []).filter((item) => item.modes.includes("generate")), [config]);
  const model = models.find((item) => item.key === modelKey) ?? models[0];

  useEffect(() => {
    if (config && !modelKey) setModelKey(config.default_model);
  }, [config, modelKey]);

  // Keep the options valid for the chosen model.
  useEffect(() => {
    if (!model) return;
    if (!model.aspect_ratios.includes(aspect)) setAspect(closestAspect(aspect, model.aspect_ratios));
    if (model.resolutions.length && !model.resolutions.includes(resolution))
      setResolution(model.resolutions.includes("1K") ? "1K" : model.resolutions[0]);
    if (model.quality_levels.length && !model.quality_levels.includes(quality))
      setQuality(model.quality_levels.includes("medium") ? "medium" : model.quality_levels[0]);
    if (count > model.max_count) setCount(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [model?.key]);

  async function generate() {
    if (!model) return;
    if (!prompt.trim()) {
      setError(t("errors.promptRequired"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const images = await StudioApi.generate({
        prompt: prompt.trim(),
        model: model.key,
        aspect_ratio: aspect,
        ...(model.resolutions.length ? { resolution } : {}),
        ...(model.quality_levels.length ? { quality } : {}),
        count: Math.min(count, model.max_count),
      });
      setResults(images);
      setSelected(images[0] ?? null);
      addImages(images);
    } catch (reason) {
      setError(errorMessage(reason, t("errors.requestFailed")));
    } finally {
      setBusy(false);
    }
  }

  const title = t("pages.generate");
  if (configError || (config && !config.configured)) {
    return (
      <div className="min-h-screen font-syne">
        <StudioHeader title={title} isAdmin={isAdmin} />
        <StudioNotice isAdmin={isAdmin} error={configError} />
      </div>
    );
  }

  const encoded = selected ? encodeURIComponent(selected.file_url) : "";

  return (
    <div className="min-h-screen">
      <StudioHeader title={title} isAdmin={isAdmin} />
      <main className="mx-4 md:ml-7 md:mr-[9px] flex flex-col-reverse gap-6 px-1 pb-10 pt-7 lg:flex-row lg:items-start">
        <div className="flex min-w-0 flex-1 flex-col gap-5">
          <section aria-label={t("result.aria")} className="flex flex-col gap-3">
            <div className="relative flex min-h-[240px] items-center justify-center overflow-hidden rounded-2xl border border-[#EDEEEF] bg-[#F9F8FB] p-2 sm:min-h-[420px] sm:p-4 lg:min-h-[520px]">
              {selected ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={imageSrc(selected.file_url)}
                  alt={selected.extras.prompt || t("result.alt")}
                  className="max-h-[68vh] max-w-full rounded-xl object-contain"
                />
              ) : (
                <div className="flex flex-col items-center gap-3.5 text-center">
                  <span className="flex h-14 w-14 items-center justify-center rounded-2xl border border-[#EDEEEF] bg-white shadow-[0_8px_18px_rgba(3,176,21,0.12)]">
                    <Sparkles className="h-6 w-6 text-[#03B015]" aria-hidden="true" />
                  </span>
                  <p className="font-syne text-base font-medium text-[#101323]">{t("result.emptyTitle")}</p>
                  <p className="text-[13px] text-[#667085]">{t("result.emptyHint")}</p>
                </div>
              )}
              <BusyOverlay active={busy} label={t("busy.generating")} />
            </div>

            {results.length > 1 && (
              <div role="group" aria-label={t("result.variants")} className="flex flex-wrap gap-2">
                {results.map((image, index) => (
                  <button
                    key={image.id}
                    type="button"
                    aria-pressed={selected?.id === image.id}
                    aria-label={t("result.variant", { number: index + 1 })}
                    onClick={() => setSelected(image)}
                    className={[
                      "h-16 w-16 overflow-hidden rounded-lg border-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#03B015]",
                      selected?.id === image.id ? "border-[#03B015]" : "border-transparent",
                    ].join(" ")}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={imageSrc(image.file_url)} alt="" className="h-full w-full object-cover" />
                  </button>
                ))}
              </div>
            )}

            {selected && (
              <div className="flex flex-wrap items-center gap-2">
                <a href={imageSrc(selected.file_url)} download className={linkAction}>
                  <Download className="h-4 w-4" aria-hidden="true" />
                  {t("actions.download")}
                </a>
                <Link href={`/studio/brush?image=${encoded}`} className={linkAction}>
                  <Brush className="h-4 w-4" aria-hidden="true" />
                  {t("actions.toBrush")}
                </Link>
                <Link href={`/studio/reference?image=${encoded}`} className={linkAction}>
                  <ImagePlus className="h-4 w-4" aria-hidden="true" />
                  {t("actions.toReference")}
                </Link>
                <Link href={`/studio/storyboard?image=${encoded}`} className={linkAction}>
                  <Clapperboard className="h-4 w-4" aria-hidden="true" />
                  {t("actions.toStoryboard")}
                </Link>
              </div>
            )}
          </section>

          <StudioHistory
            items={history}
            loading={historyLoading}
            selectedUrl={selected?.file_url}
            onPick={(image) => {
              setSelected(image);
              setResults([]);
              window.scrollTo({ top: 0, behavior: "smooth" });
            }}
            onRemove={async (image) => {
              await removeImage(image.id);
              if (selected?.id === image.id) setSelected(null);
              setResults((current) => current.filter((item) => item.id !== image.id));
            }}
          />
        </div>

        <FormCard title={t("generate.title")} subtitle={t("generate.subtitle")}>
          <PromptField
            id="studio-generate-prompt"
            label={t("fields.prompt")}
            value={prompt}
            onChange={setPrompt}
            placeholder={t("generate.placeholder")}
          />
          {model ? (
            <div className="flex flex-col gap-4 px-[22px] pb-[22px] pt-[18px]">
              <ModelSelect id="studio-generate-model" models={models} value={model.key} onChange={setModelKey} />
              <ChipGroup label={t("fields.aspect")} options={model.aspect_ratios} value={aspect} onChange={setAspect} />
              {model.resolutions.length > 1 && (
                <ChipGroup
                  label={t("fields.resolution")}
                  options={model.resolutions}
                  value={resolution}
                  onChange={setResolution}
                />
              )}
              {model.quality_levels.length > 1 && (
                <ChipGroup
                  label={t("fields.quality")}
                  options={model.quality_levels}
                  value={quality}
                  onChange={setQuality}
                  format={(level) => (t.has(`quality.${level}`) ? t(`quality.${level}`) : level)}
                />
              )}
              {model.max_count > 1 && (
                <ChipGroup
                  label={t("fields.count")}
                  options={COUNTS.filter((value) => value <= model.max_count)}
                  value={count}
                  onChange={setCount}
                />
              )}
              <ErrorBox error={error} />
              <GradientButton busy={busy} onClick={generate}>
                {busy
                  ? t("busy.generating")
                  : withPrice(t("generate.submit"), config, model, { resolution, quality, count: Math.min(count, model.max_count) })}
              </GradientButton>
            </div>
          ) : (
            <p className="px-[22px] py-6 text-sm text-[#667085]">{t("loading")}</p>
          )}
        </FormCard>
      </main>
    </div>
  );
}
