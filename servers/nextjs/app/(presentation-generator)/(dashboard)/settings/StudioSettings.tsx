"use client";

import React, { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { useTranslations } from "next-intl";
import { LLMConfig } from "@/types/llm_config";
import StudioMark from "@/components/studio/StudioMark";

// arckep access for AI Image Studio (administrators only, like all provider
// settings). An empty key falls back to the web search key on the same host.
const StudioSettings = ({
  llmConfig,
  setLlmConfig,
}: {
  llmConfig: LLMConfig;
  setLlmConfig: React.Dispatch<React.SetStateAction<LLMConfig>>;
}) => {
  const t = useTranslations("settings.studio");
  const [showKey, setShowKey] = useState(false);
  const update = (field: "STUDIO_BASE_URL" | "STUDIO_API_KEY", value: string) =>
    setLlmConfig((current) => ({ ...current, [field]: value }));

  return (
    <div className="space-y-6 rounded-[12px] bg-[#F9F8F8] p-7">
      <div className="mb-4 rounded-[12px] bg-white p-10 pt-8">
        <div className="flex flex-col items-start justify-between gap-8 lg:flex-row lg:gap-10">
          <div className="max-w-[320px]">
            <StudioMark size={60} className="mb-4" />
            <h3 className="font-syne text-xl font-normal text-[#191919]">{t("title")}</h3>
            <p className="mt-2 text-sm leading-6 text-[#808080]">{t("desc")}</p>
          </div>
          <div className="w-full max-w-[720px] space-y-6">
            <div>
              <label htmlFor="studio-base-url" className="mb-2 block text-sm font-medium text-[#4C5554]">
                {t("baseUrl")}
              </label>
              <input
                id="studio-base-url"
                type="url"
                className="h-12 w-full rounded-lg border border-gray-300 px-4 text-sm text-[#191919] outline-none transition-colors focus:border-blue-500"
                placeholder="https://arckep.ru/api/v1"
                value={llmConfig.STUDIO_BASE_URL || ""}
                onChange={(event) => update("STUDIO_BASE_URL", event.target.value)}
              />
              <p className="mt-1.5 text-xs leading-5 text-gray-500">{t("baseUrlHint")}</p>
            </div>
            <div>
              <label htmlFor="studio-api-key" className="mb-2 block text-sm font-medium text-[#4C5554]">
                {t("apiKey")}
              </label>
              <div className="relative">
                <input
                  id="studio-api-key"
                  type={showKey ? "text" : "password"}
                  autoComplete="off"
                  className="h-12 w-full rounded-lg border border-gray-300 px-4 pr-12 text-sm text-[#191919] outline-none transition-colors focus:border-blue-500"
                  value={llmConfig.STUDIO_API_KEY || ""}
                  onChange={(event) => update("STUDIO_API_KEY", event.target.value)}
                />
                <button
                  type="button"
                  className="absolute inset-y-0 right-0 flex w-12 items-center justify-center rounded-r-lg text-gray-500 hover:text-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500"
                  onClick={() => setShowKey((value) => !value)}
                  aria-label={showKey ? t("hideKey") : t("showKey")}
                  aria-pressed={showKey}
                >
                  {showKey ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
                </button>
              </div>
              <p className="mt-1.5 text-xs leading-5 text-gray-500">{t("apiKeyHint")}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default StudioSettings;
