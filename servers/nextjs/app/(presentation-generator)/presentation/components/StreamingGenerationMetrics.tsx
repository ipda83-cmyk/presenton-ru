"use client";

import type { GenerationMetrics } from "@/store/slices/presentationGeneration";
import { useFormatter, useTranslations } from "next-intl";


export default function StreamingGenerationMetrics({
  metrics,
}: {
  metrics: GenerationMetrics;
}) {
  const t = useTranslations("editor");
  const format = useFormatter();
  const formatTokens = (value: number | null, estimated = false) => {
    if (value === null || !Number.isFinite(value)) return "—";
    return `${estimated ? "~" : ""}${format.number(Math.round(value), {
      maximumFractionDigits: 0,
    })}`;
  };
  const thinkingPending =
    metrics.supports_thinking &&
    metrics.thinking_tokens_estimated &&
    (metrics.thinking_tokens ?? 0) === 0;

  return (
    <div
      aria-live="polite"
      className="hidden h-[38px] shrink-0 items-center rounded-[80px] border border-[#E4E2EB] bg-[#F6F6F9] px-3 font-syne sm:flex"
      title={
        metrics.estimated
          ? t("metricEstimatedTitle")
          : t("metricFinalTitle", { model: metrics.model || t("metricSelectedModel") })
      }
    >
      <div className="flex items-center gap-2 text-[11px] font-semibold text-[#555766]">
        <span
          aria-hidden="true"
          className={`h-1.5 w-1.5 rounded-full ${
            metrics.estimated ? "animate-pulse bg-[#02940F]" : "bg-emerald-500"
          }`}
        />
        <span className="whitespace-nowrap">
          {t("metricIn")} {formatTokens(metrics.input_tokens, metrics.estimated)}
        </span>
        <span className="h-3.5 w-px bg-[#D8D8DF]" aria-hidden="true" />
        <span className="whitespace-nowrap">
          {t("metricOut")} {formatTokens(metrics.output_tokens, metrics.estimated)}
        </span>
        {metrics.supports_thinking ? (
          <>
            <span className="h-3.5 w-px bg-[#D8D8DF]" aria-hidden="true" />
            <span
              className={`whitespace-nowrap ${
                thinkingPending ? "animate-pulse text-[#02940F]" : ""
              }`}
              title={
                thinkingPending
                  ? t("metricThinkingPending")
                  : undefined
              }
            >
              {t("metricThink")}{" "}
              {formatTokens(
                metrics.thinking_tokens,
                metrics.thinking_tokens_estimated
              )}
            </span>
          </>
        ) : null}
        <span className="h-3.5 w-px bg-[#D8D8DF]" aria-hidden="true" />
        <span className="whitespace-nowrap">
          {t("metricTps", {
            value: format.number(metrics.tokens_per_second, {
              minimumFractionDigits: 1,
              maximumFractionDigits: 1,
            }),
          })}
        </span>
      </div>
    </div>
  );
}
