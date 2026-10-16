import { getApiUrl } from "@/utils/api";
import { tr } from "@/utils/clientI18n";
import { ApiResponseHandler } from "./api-error-handler";
import { getHeader } from "./header";
import { notifyBillingChanged } from "@/utils/billingEvents";
import type { BillingPrices } from "./billing";

// AI Image Studio (servers/fastapi/api/v1/studio/router.py).
// Families and quality levels come from arckep's catalog (Admin → Models).
export type StudioModelFamily = string;
export type StudioQuality = string;
/** What the administrator allowed a model for. */
export type StudioModelMode = "generate" | "edit" | "reference" | "storyboard";
export type StudioOperation = "upscale" | "remove_bg";
export type StudioMode = "create" | "edit" | "brush" | "reference" | "storyboard" | StudioOperation;

export interface StudioModel {
  key: string;
  title: string;
  family: StudioModelFamily;
  aspect_ratios: string[];
  resolutions: string[];
  quality_levels: StudioQuality[];
  max_count: number;
  tags: string[];
  modes: StudioModelMode[];
}

/** Upscale / remove background: a Gemini model does it best, else the chosen editing model. */
export function operationModelFor(models: StudioModel[], preferredKey?: string): StudioModel | undefined {
  const preferred = models.find((item) => item.key === preferredKey);
  if (preferred?.family === "gemini") return preferred;
  return models.find((item) => item.family === "gemini") ?? preferred ?? models[0];
}


export interface StoryboardView {
  id: string;
  group: "portrait" | "full_body" | "special";
}

export interface StudioConfig {
  configured: boolean;
  default_model: string;
  models: StudioModel[];
  storyboard_views?: StoryboardView[];
  /** One request's price per model (see services/billing/pricing.py). */
  prices?: BillingPrices["studio"];
  /** False for administrators and when billing is off. */
  charged?: boolean;
}

export interface StudioStoryboardRequest {
  /** /app_data/... path of the reference picture (or a data URL). */
  image: string;
  view: string;
  model: string;
  resolution?: string;
  details?: string;
}

export interface StudioImage {
  id: string;
  created_at: string;
  file_url: string;
  extras: {
    source?: string;
    mode?: StudioMode;
    prompt?: string;
    model?: string;
    aspect_ratio?: string | null;
    resolution?: string | null;
    parent?: string | null;
    view?: string;
  };
}

export interface StudioGenerateRequest {
  prompt: string;
  model: string;
  aspect_ratio?: string;
  resolution?: string;
  quality?: StudioQuality;
  count?: number;
}

export interface StudioEditRequest {
  /** /app_data/... path of the user's image, or a data URL. */
  image: string;
  prompt?: string;
  model: string;
  /** PNG data URL: transparent pixels mark the area to change. */
  mask?: string;
  reference?: string;
  operation?: StudioOperation;
  resolution?: string;
  quality?: StudioQuality;
}

const failed = () => tr("studio.errors.requestFailed", "The Studio request failed");

async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(getApiUrl(path), {
    method: "POST",
    headers: getHeader(),
    credentials: "include",
    body: JSON.stringify(body),
  });
  const result = await ApiResponseHandler.handleResponse(response, failed());
  notifyBillingChanged(); // paid requests change the balance
  return result;
}

export const StudioApi = {
  async config(): Promise<StudioConfig> {
    const response = await fetch(getApiUrl("/api/v1/studio/config"), {
      credentials: "include",
      cache: "no-store",
    });
    return ApiResponseHandler.handleResponse(response, failed());
  },

  async generate(body: StudioGenerateRequest): Promise<StudioImage[]> {
    const result = await post<{ images: StudioImage[] }>("/api/v1/studio/generate", body);
    return result.images ?? [];
  },

  async edit(body: StudioEditRequest): Promise<StudioImage> {
    const result = await post<{ image: StudioImage }>("/api/v1/studio/edit", body);
    return result.image;
  },

  /** One storyboard view; the page asks for several in parallel. */
  async storyboard(body: StudioStoryboardRequest): Promise<StudioImage> {
    const result = await post<{ image: StudioImage }>("/api/v1/studio/storyboard", body);
    return result.image;
  },

  async history(limit = 60): Promise<StudioImage[]> {
    const response = await fetch(getApiUrl(`/api/v1/studio/history?limit=${limit}`), {
      credentials: "include",
      cache: "no-store",
    });
    const result = await ApiResponseHandler.handleResponse(response, failed());
    return Array.isArray(result?.images) ? result.images : [];
  },

  async remove(id: string): Promise<void> {
    const response = await fetch(getApiUrl(`/api/v1/studio/history/${encodeURIComponent(id)}`), {
      method: "DELETE",
      credentials: "include",
    });
    await ApiResponseHandler.handleResponse(response, failed());
  },
};

export { isStudioImagePath } from "./studio-paths";
