import { getApiUrl } from "@/utils/api";
import { tr } from "@/utils/clientI18n";
import { ApiResponseHandler } from "./api-error-handler";
import { getHeader, getHeaderForFormData } from "./header";

// The Help page the administrator edits (servers/fastapi/api/v1/help/router.py).

export interface HelpFile {
  name: string;
  /** /app_data/help/… (signed-in users only). */
  url: string;
  size: number;
}

export interface HelpVideo {
  url: string;
  title: string;
  /** Player address (YouTube, Rutube, VK Video); null = shown as a link. */
  embed?: string | null;
}

export interface HelpSection {
  id: string;
  title: string;
  /** Markdown. */
  body: string;
  files: HelpFile[];
  videos: HelpVideo[];
}

export interface HelpContent {
  /** false = the built-in help (translated texts). */
  custom: boolean;
  sections: HelpSection[];
  updated_at: string | null;
}

const failed = () => tr("adminHelp.errors.requestFailed", "The request failed");

async function call<T>(path: string, init: RequestInit = {}, formData = false): Promise<T> {
  const response = await fetch(getApiUrl(path), {
    credentials: "include",
    cache: "no-store",
    ...init,
    headers: { ...(formData ? getHeaderForFormData() : getHeader()), ...(init.headers || {}) },
  });
  return ApiResponseHandler.handleResponse(response, failed());
}

export const HelpApi = {
  read: () => call<HelpContent>("/api/v1/help"),
  save: (sections: HelpSection[]) =>
    call<HelpContent>("/api/v1/admin/help", { method: "PUT", body: JSON.stringify({ sections }) }),
  reset: () => call<HelpContent>("/api/v1/admin/help", { method: "DELETE" }),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return call<HelpFile>("/api/v1/admin/help/files", { method: "POST", body: form }, true);
  },
};

export function formatFileSize(bytes: number, locale: string): string {
  const units = locale.startsWith("ru") ? ["Б", "КБ", "МБ"] : ["B", "KB", "MB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toLocaleString(locale, { maximumFractionDigits: unit ? 1 : 0 })} ${units[unit]}`;
}
