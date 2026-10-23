import { getApiUrl } from "@/utils/api";
import { tr } from "@/utils/clientI18n";
import { ApiResponseHandler } from "./api-error-handler";
import { getHeader } from "./header";
import type { StudioModel, StudioModelMode } from "./studio";

// Admin → Models (servers/fastapi/api/v1/studio/admin_router.py).

export interface StudioModelCost {
  resolution: string | null;
  quality: string | null;
  /** arckep's cost of one image, rubles. */
  cost: number | null;
  source: "manual" | "estimate" | "known" | "none";
  /** What a user pays for one image. */
  price: number | null;
  estimated_at: number | null;
  estimate_raw: unknown;
}

export interface AdminStudioModel extends StudioModel {
  enabled: boolean;
  order: number;
  provider: string | null;
  description: string;
  supported_modes: StudioModelMode[];
  max_references: number | null;
  markup: number | null;
  manual_costs: Record<string, number>;
  costs: Record<string, StudioModelCost>;
}

export interface AdminStudioModels {
  catalog: { source: "arckep" | "snapshot"; fetched_at: number | null; error: string | null; count: number };
  modes: StudioModelMode[];
  default_model: string;
  markup: number;
  slide_image_model: string;
  /** Who the slide pictures show; empty = no instruction. */
  people_appearance: string;
  models: AdminStudioModel[];
}

export interface StudioModelSettings {
  enabled: boolean;
  title?: string;
  order: number;
  modes: StudioModelMode[];
  tags?: string[];
  markup?: number;
  costs?: Record<string, number>;
}

export interface StudioModelsSettings {
  default_model: string;
  markup: number;
  slide_image_model: string;
  people_appearance: string;
  models: Record<string, StudioModelSettings>;
}

const failed = () => tr("adminModels.errors.requestFailed", "The request failed");

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(getApiUrl(path), {
    credentials: "include",
    cache: "no-store",
    ...init,
    headers: { ...getHeader(), ...(init.headers || {}) },
  });
  return ApiResponseHandler.handleResponse(response, failed());
}

export const StudioAdminApi = {
  models: () => call<AdminStudioModels>("/api/v1/admin/studio/models"),
  save: (settings: StudioModelsSettings) =>
    call<AdminStudioModels>("/api/v1/admin/studio/models", { method: "PUT", body: JSON.stringify(settings) }),
  refreshCatalog: () => call<AdminStudioModels>("/api/v1/admin/studio/catalog/refresh", { method: "POST" }),
  estimate: (key: string) =>
    call<AdminStudioModel>(`/api/v1/admin/studio/models/${encodeURIComponent(key)}/estimate`, { method: "POST" }),
};
