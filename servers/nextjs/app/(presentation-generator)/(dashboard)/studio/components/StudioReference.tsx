"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { X } from "lucide-react";
import { useTranslations } from "next-intl";
import { withPrice } from "@/components/studio/price";
import type { MaskCanvasHandle } from "@/components/studio/MaskCanvas";
import { StudioApi } from "../../../services/api/studio";
import StudioHeader from "./StudioHeader";
import StudioHistory from "./StudioHistory";
import StudioNotice from "./StudioNotice";
import MaskWorkspace from "./MaskWorkspace";
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

export default function StudioReference({ isAdmin, initialImage }: { isAdmin: boolean; initialImage: string | null }) {
  const t = useTranslations("studio");
  const { config, configError, history, historyLoading, addImages, removeImage } = useStudio();
  const canvasRef = useRef<MaskCanvasHandle>(null);

  const [image, setImage] = useState<string | null>(initialImage);
  const [before, setBefore] = useState<string | null>(null);
  const [reference, setReference] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [modelKey, setModelKey] = useState("");
  const [resolution, setResolution] = useState("1K");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Models the administrator allowed for object insertion (Gemini by default).
  const models = useMemo(() => (config?.models ?? []).filter((item) => item.modes.includes("reference")), [config]);
  const model = models.find((item) => item.key === modelKey) ?? models[0];

  useEffect(() => {
    if (config && !modelKey && models.length) {
      setModelKey(models.some((item) => item.key === config.default_model) ? config.default_model : models[0].key);
    }
  }, [config, modelKey, models]);

  useEffect(() => {
    if (model?.resolutions.length && !model.resolutions.includes(resolution)) setResolution(model.resolutions[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [model?.key]);

  const loadImage = useImageFile(
    (dataUrl) => {
      setImage(dataUrl);
      setBefore(null);
      setError(null);
    },
    setError,
  );
  const loadReference = useImageFile(
    (dataUrl) => {
      setReference(dataUrl);
      setError(null);
    },
    setError,
  );
  // A pasted picture fills the empty slot: first the scene, then the object.
  usePastedImage((file) => (image ? loadReference(file) : loadImage(file)), !busy && !(image && reference));

  async function insert() {
    if (!image || !model) return;
    if (!reference) return setError(t("errors.referenceRequired"));
    const mask = canvasRef.current?.exportMask();
    if (!mask) return setError(t("errors.placeRequired"));
    setBusy(true);
    setError(null);
    try {
      const result = await StudioApi.edit({
        image,
        reference,
        mask,
        prompt: prompt.trim(),
        model: model.key,
        ...(model.resolutions.includes(resolution) ? { resolution } : {}),
      });
      setBefore(image);
      setImage(result.file_url);
      addImages([result]);
      canvasRef.current?.clearMask();
    } catch (reason) {
      setError(errorMessage(reason, t("errors.requestFailed")));
    } finally {
      setBusy(false);
    }
  }

  const title = t("pages.reference");
  if (configError || (config && !config.configured)) {
    return (
      <div className="min-h-screen font-syne">
        <StudioHeader title={title} isAdmin={isAdmin} />
        <StudioNotice isAdmin={isAdmin} error={configError} />
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <StudioHeader title={title} isAdmin={isAdmin} />
      <main className="mx-4 md:ml-7 md:mr-[9px] flex flex-col gap-6 px-1 pb-10 pt-7 lg:flex-row lg:items-start">
        <div className="flex min-w-0 flex-1 flex-col gap-6">
          <MaskWorkspace
            image={image}
            before={before}
            canvasRef={canvasRef}
            busy={busy}
            busyLabel={t("busy.inserting")}
            dropTitle={t("reference.dropTitle")}
            dropHint={t("upload.hint")}
            onFile={loadImage}
            onClear={() => {
              setImage(null);
              setBefore(null);
              setError(null);
            }}
          />
          <StudioHistory
            items={history}
            loading={historyLoading}
            selectedUrl={image}
            onPick={(item) => {
              setImage(item.file_url);
              setBefore(null);
              setError(null);
              window.scrollTo({ top: 0, behavior: "smooth" });
            }}
            onRemove={async (item) => {
              await removeImage(item.id);
              if (image === item.file_url) setImage(null);
              if (before === item.file_url) setBefore(null);
            }}
          />
        </div>

        <FormCard title={t("reference.title")} subtitle={t("reference.subtitle")}>
          <div className="flex flex-col gap-2.5 px-[22px] pt-[18px]">
            <FieldLabel>{t("reference.objectLabel")}</FieldLabel>
            {reference ? (
              <div className="flex items-center gap-3 rounded-xl border border-[#DBDBE1] bg-white p-2">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={imageSrc(reference)} alt={t("reference.objectAlt")} className="h-14 w-14 rounded-lg border border-[#EDEEEF] object-contain" />
                <p className="min-w-0 flex-1 text-xs leading-5 text-[#667085]">{t("reference.objectReady")}</p>
                <button
                  type="button"
                  onClick={() => setReference(null)}
                  aria-label={t("reference.removeObject")}
                  title={t("reference.removeObject")}
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[#667085] transition-colors hover:bg-red-50 hover:text-red-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#03B015]"
                >
                  <X className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
            ) : (
              <ImageDropZone compact title={t("reference.objectDrop")} hint={t("reference.objectHint")} onFile={loadReference} />
            )}
          </div>
          <div className="mt-[18px]">
            <PromptField
              id="studio-reference-prompt"
              label={t("reference.promptLabel")}
              optional={t("fields.optional")}
              value={prompt}
              onChange={setPrompt}
              placeholder={t("reference.placeholder")}
              rows={3}
            />
          </div>
          {model ? (
            <div className="flex flex-col gap-4 px-[22px] pb-[22px] pt-[18px]">
              <ModelSelect id="studio-reference-model" models={models} value={model.key} onChange={setModelKey} />
              {model.resolutions.length > 1 && (
                <ChipGroup label={t("fields.resultSize")} options={model.resolutions} value={resolution} onChange={setResolution} />
              )}
              <p className="text-xs leading-5 text-[#667085]">{t("reference.howTo")}</p>
              <ErrorBox error={error} />
              <GradientButton busy={busy} disabled={!image} onClick={insert}>
                {busy ? t("busy.inserting") : withPrice(t("reference.submit"), config, model, { resolution })}
              </GradientButton>
              {!image && <p className="text-center text-xs text-[#667085]">{t("reference.needImage")}</p>}
            </div>
          ) : (
            <p className="px-[22px] py-6 text-sm text-[#667085]">{t("loading")}</p>
          )}
        </FormCard>
      </main>
    </div>
  );
}
