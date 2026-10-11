"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import type { MaskCanvasHandle } from "@/components/studio/MaskCanvas";
import { StudioApi, type StudioImage, type StudioOperation } from "../../../services/api/studio";
import StudioHeader from "./StudioHeader";
import StudioHistory from "./StudioHistory";
import StudioNotice from "./StudioNotice";
import MaskWorkspace from "./MaskWorkspace";
import { useImageFile, usePastedImage } from "./ImageDropZone";
import { useStudio } from "./useStudio";
import {
  ChipGroup,
  ErrorBox,
  FormCard,
  GradientButton,
  ModelSelect,
  PromptField,
  SoftButton,
  errorMessage,
} from "./controls";

type Busy = null | "brush" | StudioOperation;

export default function StudioBrush({ isAdmin, initialImage }: { isAdmin: boolean; initialImage: string | null }) {
  const t = useTranslations("studio");
  const { config, configError, history, historyLoading, addImages, removeImage } = useStudio();
  const canvasRef = useRef<MaskCanvasHandle>(null);

  const [image, setImage] = useState<string | null>(initialImage);
  const [before, setBefore] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [modelKey, setModelKey] = useState("");
  const [opResolution, setOpResolution] = useState("1K");
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<string | null>(null);

  const models = useMemo(() => config?.models ?? [], [config]);
  const model = models.find((item) => item.key === modelKey) ?? models[0];
  // Upscale and background removal work best on the Gemini image models.
  const operationModel =
    model?.family === "gemini" ? model : models.find((item) => item.key === config?.default_model && item.family === "gemini") ?? models.find((item) => item.family === "gemini");

  useEffect(() => {
    if (config && !modelKey) setModelKey(config.default_model);
  }, [config, modelKey]);

  const loadFile = useImageFile(
    (dataUrl) => {
      setImage(dataUrl);
      setBefore(null);
      setError(null);
    },
    setError,
  );
  usePastedImage((file) => loadFile(file), !busy);

  function applied(result: StudioImage) {
    setBefore(image);
    setImage(result.file_url);
    addImages([result]);
    canvasRef.current?.clearMask();
  }

  async function applyBrush() {
    if (!image || !model) return;
    const mask = canvasRef.current?.exportMask();
    if (!mask) return setError(t("errors.maskRequired"));
    if (!prompt.trim()) return setError(t("errors.brushPromptRequired"));
    setBusy("brush");
    setError(null);
    try {
      applied(await StudioApi.edit({ image, mask, prompt: prompt.trim(), model: model.key }));
      setPrompt("");
    } catch (reason) {
      setError(errorMessage(reason, t("errors.requestFailed")));
    } finally {
      setBusy(null);
    }
  }

  async function runOperation(operation: StudioOperation) {
    if (!image || !operationModel) return;
    setBusy(operation);
    setError(null);
    try {
      applied(
        await StudioApi.edit({
          image,
          operation,
          model: operationModel.key,
          ...(operationModel.resolutions.includes(opResolution) ? { resolution: opResolution } : {}),
        }),
      );
    } catch (reason) {
      setError(errorMessage(reason, t("errors.requestFailed")));
    } finally {
      setBusy(null);
    }
  }

  const title = t("pages.brush");
  if (configError || (config && !config.configured)) {
    return (
      <div className="min-h-screen font-syne">
        <StudioHeader title={title} isAdmin={isAdmin} />
        <StudioNotice isAdmin={isAdmin} error={configError} />
      </div>
    );
  }

  const busyLabel = busy === "upscale" ? t("busy.upscale") : busy === "remove_bg" ? t("busy.removeBg") : t("busy.editing");

  return (
    <div className="min-h-screen">
      <StudioHeader title={title} isAdmin={isAdmin} />
      <main className="mx-4 md:ml-7 md:mr-[9px] flex flex-col gap-6 px-1 pb-10 pt-7 lg:flex-row lg:items-start">
        <div className="flex min-w-0 flex-1 flex-col gap-6">
          <MaskWorkspace
            image={image}
            before={before}
            canvasRef={canvasRef}
            busy={!!busy}
            busyLabel={busyLabel}
            dropTitle={t("brush.dropTitle")}
            dropHint={t("upload.hint")}
            onFile={loadFile}
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

        <FormCard title={t("brush.title")} subtitle={t("brush.subtitle")}>
          <PromptField
            id="studio-brush-prompt"
            label={t("brush.promptLabel")}
            value={prompt}
            onChange={setPrompt}
            placeholder={t("brush.placeholder")}
            rows={3}
          />
          {model ? (
            <div className="flex flex-col gap-4 px-[22px] pb-[22px] pt-[18px]">
              <ModelSelect id="studio-brush-model" models={models} value={model.key} onChange={setModelKey} />
              <ErrorBox error={error} />
              <GradientButton busy={busy === "brush"} disabled={!image || !!busy} onClick={applyBrush}>
                {t("brush.submit")}
              </GradientButton>
              {!image && <p className="text-center text-xs text-[#667085]">{t("brush.needImage")}</p>}

              <div className="flex items-center gap-2.5 text-xs text-[#98A2B3]" aria-hidden="true">
                <span className="h-px flex-1 bg-[#E1E1E5]" />
                {t("brush.wholeImage")}
                <span className="h-px flex-1 bg-[#E1E1E5]" />
              </div>
              {operationModel && operationModel.resolutions.length > 1 && (
                <ChipGroup
                  label={t("fields.resultSize")}
                  options={operationModel.resolutions}
                  value={opResolution}
                  onChange={setOpResolution}
                />
              )}
              <div className="grid grid-cols-2 gap-2.5">
                <SoftButton busy={busy === "upscale"} disabled={!image || !!busy || !operationModel} onClick={() => runOperation("upscale")}>
                  {t("brush.upscale")}
                </SoftButton>
                <SoftButton busy={busy === "remove_bg"} disabled={!image || !!busy || !operationModel} onClick={() => runOperation("remove_bg")}>
                  {t("brush.removeBg")}
                </SoftButton>
              </div>
              {operationModel && operationModel.key !== model.key && (
                <p className="text-[11px] leading-4 text-[#667085]">{t("brush.operationModel", { model: operationModel.title })}</p>
              )}
            </div>
          ) : (
            <p className="px-[22px] py-6 text-sm text-[#667085]">{t("loading")}</p>
          )}
        </FormCard>
      </main>
    </div>
  );
}
