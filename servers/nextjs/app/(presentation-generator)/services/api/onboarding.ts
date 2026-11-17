import { getApiUrl } from "@/utils/api";
import { tr } from "@/utils/clientI18n";
import { ApiResponseHandler } from "./api-error-handler";
import { getHeader } from "./header";

// Onboarding (servers/fastapi/api/v1/onboarding/router.py).

export type OnboardingPart = "welcome" | "tour" | "checklist" | "tips";
export type OnboardingTip = "outline-plan" | "editor-export" | "editor-ai" | "studio-brush";
export type ChecklistItem = "presentation" | "edited" | "exported" | "studio" | "topup" | "template";

export interface Onboarding {
  show: Record<OnboardingPart, boolean>;
  checklist: { id: ChecklistItem; done: boolean }[];
  latest_presentation: string | null;
  tips_seen: OnboardingTip[];
  /** Empty: the built-in text. */
  welcome_text: string;
  /** Rubles every new account gets; 0 without billing. */
  bonus: number;
  /** False for a self-registered user who has not confirmed the e-mail yet. */
  verified: boolean;
}

export type OnboardingEvent =
  | "welcome"
  | "tour"
  | "checklist"
  | "edited"
  | "tour_restart"
  | "preview"
  | `tip:${OnboardingTip}`;

export interface OnboardingSettings {
  welcome: boolean;
  tour: boolean;
  checklist: boolean;
  tips: boolean;
  welcome_text: string;
  reset_at?: string | null;
}

export interface OnboardingStats {
  days: number;
  users: number;
  presentation: number;
  exported: number;
  studio: number;
}

export interface AdminOnboarding {
  settings: OnboardingSettings;
  stats: OnboardingStats;
}

const failed = () => tr("adminOnboarding.requestFailed", "The request failed");

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(getApiUrl(path), {
    credentials: "include",
    cache: "no-store",
    ...init,
    headers: { ...getHeader(), ...(init.headers || {}) },
  });
  return ApiResponseHandler.handleResponse(response, failed());
}

export const OnboardingApi = {
  read: () => call<Onboarding>("/api/v1/onboarding"),
  mark: (event: OnboardingEvent) =>
    call<Onboarding>("/api/v1/onboarding/events", { method: "POST", body: JSON.stringify({ event }) }),
  admin: () => call<AdminOnboarding>("/api/v1/admin/onboarding"),
  save: (settings: OnboardingSettings) =>
    call<AdminOnboarding>("/api/v1/admin/onboarding", { method: "PUT", body: JSON.stringify(settings) }),
  showAgain: () => call<AdminOnboarding>("/api/v1/admin/onboarding/show-again", { method: "POST" }),
};
