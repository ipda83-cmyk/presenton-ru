import { getApiUrl } from "@/utils/api";

// Web pages the outline was researched from (servers/fastapi/utils/web_sources.py).
export type WebSourceStatus =
  | "ok"
  | "empty"
  | "failed"
  | "native"
  | "unavailable"
  | "disabled"
  | "none";

export interface WebSource {
  title: string;
  url: string;
  domain: string;
  snippet: string;
}

export interface WebSourcesRecord {
  status: WebSourceStatus;
  provider: string | null;
  query: string | null;
  sources: WebSource[];
  updated_at?: string;
}

const STATUSES: readonly WebSourceStatus[] = [
  "ok",
  "empty",
  "failed",
  "native",
  "unavailable",
  "disabled",
  "none",
];

const isHttpUrl = (value: unknown): value is string =>
  typeof value === "string" && /^https?:\/\//i.test(value);

/** Accepts only well-formed records; links must be http(s) web pages. */
export function normalizeWebSourcesRecord(value: unknown): WebSourcesRecord | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const status = STATUSES.includes(record.status as WebSourceStatus)
    ? (record.status as WebSourceStatus)
    : "failed";
  const sources = Array.isArray(record.sources)
    ? record.sources.flatMap((item): WebSource[] => {
        if (!item || typeof item !== "object") return [];
        const source = item as Record<string, unknown>;
        if (!isHttpUrl(source.url)) return [];
        return [
          {
            url: source.url,
            title: String(source.title ?? ""),
            domain: String(source.domain ?? ""),
            snippet: String(source.snippet ?? ""),
          },
        ];
      })
    : [];
  return {
    status,
    provider: typeof record.provider === "string" ? record.provider : null,
    query: typeof record.query === "string" ? record.query : null,
    sources,
    updated_at: typeof record.updated_at === "string" ? record.updated_at : undefined,
  };
}

export async function fetchWebSources(
  presentationId: string
): Promise<WebSourcesRecord | null> {
  const response = await fetch(
    getApiUrl(`/api/v1/ppt/outlines/${encodeURIComponent(presentationId)}/sources`),
    { credentials: "include", cache: "no-store" }
  );
  if (!response.ok) return null;
  return normalizeWebSourcesRecord(await response.json());
}
