"use client";

import { ExternalLink, Globe, Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import { WEB_SEARCH_PROVIDERS } from "@/utils/providerConstants";
import type { WebSourcesRecord } from "../../services/api/web-sources";

// Where the outline's facts came from: site + the start of the page text.
// `record === null` while a new outline stream is searching.
const WebSourcesPanel = ({
  record,
  isSearching,
  className,
}: {
  record: WebSourcesRecord | null;
  isSearching: boolean;
  className?: string;
}) => {
  const t = useTranslations("outline.sources");
  const sources = record?.sources ?? [];
  const providerLabel =
    record?.provider && record.provider !== "model-native"
      ? WEB_SEARCH_PROVIDERS[record.provider]?.label ?? record.provider
      : null;
  const pending = isSearching && (!record || record.status === "none");

  const emptyMessage = (() => {
    if (pending) return null;
    switch (record?.status) {
      case "ok":
      case "empty":
        return sources.length ? null : t("empty");
      case "failed":
        return t("failed");
      case "native":
        return t("native");
      case "unavailable":
        return t("unavailable");
      case "disabled":
        return t("disabled");
      default:
        return t("none");
    }
  })();

  return (
    <section
      aria-labelledby="outline-web-sources-title"
      className={cn("flex min-h-0 flex-col bg-white font-syne", className)}
      data-testid="outline-web-sources"
    >
      <header className="border-b border-[#EDEEEF] px-5 py-4">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#F4F3FF]">
            <Globe className="h-3.5 w-3.5 text-[#7A5AF8]" aria-hidden="true" />
          </span>
          <h2
            id="outline-web-sources-title"
            className="text-sm font-semibold text-[#101323]"
          >
            {t("title")}
          </h2>
          {sources.length > 0 ? (
            <span className="ml-auto rounded-full bg-[#F4F3FF] px-2 py-0.5 text-[11px] font-medium text-[#5141E5]">
              {t("count", { count: sources.length })}
            </span>
          ) : null}
        </div>
        <p className="mt-1.5 text-xs leading-5 text-[#667085]">{t("subtitle")}</p>
        {providerLabel || record?.query ? (
          <p className="mt-1 text-[11px] leading-4 text-[#98A2B3]">
            {providerLabel ? t("via", { provider: providerLabel }) : null}
            {providerLabel && record?.query ? " · " : null}
            {record?.query ? t("query", { query: record.query }) : null}
          </p>
        ) : null}
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {pending ? (
          <p
            className="flex items-center gap-2 rounded-[12px] bg-[#F9F8FB] px-3.5 py-3 text-xs text-[#667085]"
            role="status"
          >
            <Loader2 className="h-3.5 w-3.5 animate-spin text-[#7A5AF8]" aria-hidden="true" />
            {t("searching")}
          </p>
        ) : emptyMessage ? (
          <p className="rounded-[12px] bg-[#F9F8FB] px-3.5 py-3 text-xs leading-5 text-[#667085]">
            {emptyMessage}
          </p>
        ) : (
          <ol className="space-y-3">
            {sources.map((source) => (
              <li key={source.url}>
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={t("open", { site: source.domain || source.url })}
                  className="group block rounded-[12px] border border-[#EDEEEF] bg-white p-3.5 transition-colors hover:border-[#D9D6FE] hover:bg-[#FCFBFF] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7A5AF8]"
                >
                  <span className="flex items-center gap-2 text-[11px] font-medium text-[#7A5AF8]">
                    <span
                      className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#F4F3FF] text-[10px] font-semibold uppercase"
                      aria-hidden="true"
                    >
                      {(source.domain || "?").charAt(0)}
                    </span>
                    <span className="truncate">{source.domain}</span>
                    <ExternalLink
                      className="ml-auto h-3 w-3 shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
                      aria-hidden="true"
                    />
                  </span>
                  {source.title ? (
                    <span className="mt-1.5 line-clamp-2 block text-sm font-medium leading-5 text-[#101323] group-hover:text-[#5141E5]">
                      {source.title}
                    </span>
                  ) : null}
                  {source.snippet ? (
                    <span className="mt-1 line-clamp-4 block text-xs leading-5 text-[#667085]">
                      {source.snippet}
                    </span>
                  ) : null}
                </a>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
};

export default WebSourcesPanel;
