import { getApiUrl } from "@/utils/api";
import { formatFastApiDetail } from "@/utils/authErrors";

// Self sign-up, e-mail confirmation, password reset, documents
// (servers/fastapi/api/v1/auth/registration_router.py, api/v1/legal/router.py).

export interface RegistrationInfo {
  open: boolean;
  password_min: number;
  /** Yandex SmartCaptcha site key; null = no captcha. */
  captcha_key: string | null;
  offer_url: string | null;
  privacy_url: string | null;
  bonus: number;
}

export interface LegalDocument {
  doc: "offer" | "privacy";
  title: string;
  /** Markdown; empty = not filled in yet. */
  body: string;
  updated_at: string | null;
}

export class AccountError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(getApiUrl(path), {
    credentials: "include",
    cache: "no-store",
    ...init,
    headers: { "Content-Type": "application/json", Accept: "application/json", ...(init.headers || {}) },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail;
    throw new AccountError(detail === undefined ? `HTTP ${response.status}` : formatFastApiDetail(detail), response.status);
  }
  return payload as T;
}

const post = <T,>(path: string, body: unknown) => call<T>(path, { method: "POST", body: JSON.stringify(body) });

export const AccountApi = {
  info: () => call<RegistrationInfo>("/api/v1/auth/registration"),
  register: (body: { email: string; password: string; accept_offer: boolean; accept_privacy: boolean; captcha?: string | null }) =>
    post<{ letter_sent: boolean }>("/api/v1/auth/register", body),
  verify: (token: string) => post<{ verified: boolean; bonus: number }>("/api/v1/auth/verify-email", { token }),
  resend: () => post<{ sent: boolean; verified: boolean }>("/api/v1/auth/verify-email/resend", {}),
  forgot: (email: string) => post<{ sent: boolean }>("/api/v1/auth/password/forgot", { email }),
  reset: (token: string, password: string) => post<unknown>("/api/v1/auth/password/reset", { token, password }),
  document: (doc: string) => call<LegalDocument>(`/api/v1/legal/${encodeURIComponent(doc)}`),
  saveDocument: (doc: string, title: string, body: string) =>
    call<LegalDocument>(`/api/v1/admin/legal/${encodeURIComponent(doc)}`, { method: "PUT", body: JSON.stringify({ title, body }) }),
};

export interface AdminRegistration {
  settings: { open: boolean; ip_daily_limit: number; blocked_domains: string[] };
  mail: { configured: boolean; missing: string[] };
  captcha: { configured: boolean };
  builtin_blocked_domains: number;
}

export const AdminRegistrationApi = {
  read: () => call<AdminRegistration>("/api/v1/admin/registration"),
  save: (settings: AdminRegistration["settings"]) =>
    call<AdminRegistration>("/api/v1/admin/registration", { method: "PUT", body: JSON.stringify(settings) }),
  testEmail: (to?: string) => post<{ sent: boolean; to: string }>("/api/v1/admin/registration/test-email", to ? { to } : {}),
};
