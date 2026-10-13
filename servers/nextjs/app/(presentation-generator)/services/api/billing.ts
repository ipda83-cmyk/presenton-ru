import { getApiUrl } from "@/utils/api";
import { tr } from "@/utils/clientI18n";
import { ApiResponseHandler } from "./api-error-handler";
import { getHeader } from "./header";

// Ruble balance and YooKassa top-ups (servers/fastapi/api/v1/billing/router.py).

export interface BillingPrices {
  /** Per Studio model: one image by resolution (Gemini) or by quality (GPT). */
  studio: Record<
    string,
    { resolution?: Record<string, number>; quality?: Record<string, number>; by_count?: Record<string, number[]> }
  >;
  per_slide: number;
}

export interface BillingMe {
  /** False: no sign-in (single-user mode) or billing switched off. */
  enabled: boolean;
  /** Administrators pay nothing. */
  free: boolean;
  balance?: number;
  receipt_email?: string | null;
  card?: { last4: string | null; type: string | null } | null;
  auto_topup?: {
    enabled: boolean;
    threshold: number;
    amount: number;
    threshold_range: [number, number];
    amount_range: [number, number];
  };
  prices: BillingPrices;
  topup_amounts: number[];
  payments_available: boolean;
  offer_url: string | null;
  signup_bonus: number;
}

export type BillingEntryKind = "bonus" | "topup" | "auto_topup" | "admin" | "charge" | "refund";

export interface BillingEntry {
  id: string;
  amount: number;
  balance_after: number;
  kind: BillingEntryKind;
  reason: string;
  reference: string | null;
  pending: boolean;
  refunded: boolean;
  details: Record<string, any>;
  created_at: string;
}

export interface BillingPayment {
  invoice_id: string;
  amount: number;
  kind: "topup" | "auto_topup";
  status: "pending" | "completed" | "failed";
  created_at: string;
}

export interface AdminBillingAccount {
  user_id: string;
  username: string;
  admin: boolean;
  balance: number | null;
  card: boolean;
  auto_topup: boolean;
}

const failed = () => tr("billing.errors.requestFailed", "The billing request failed");

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(getApiUrl(path), {
    credentials: "include",
    cache: "no-store",
    ...init,
    headers: { ...getHeader(), ...(init.headers || {}) },
  });
  return ApiResponseHandler.handleResponse(response, failed());
}

export const BillingApi = {
  me: () => call<BillingMe>("/api/v1/billing/me"),
  history: (limit = 50) =>
    call<{ entries: BillingEntry[]; payments: BillingPayment[] }>(`/api/v1/billing/history?limit=${limit}`),
  topup: (body: { amount: number; email: string; save_card: boolean; consent: boolean }) =>
    call<{ invoice_id: string; confirmation_url: string }>("/api/v1/billing/topup", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  checkPayment: (invoiceId: string) =>
    call<BillingPayment & { balance: number }>(
      `/api/v1/billing/payments/${encodeURIComponent(invoiceId)}/check`,
      { method: "POST" },
    ),
  setAutoTopup: (body: { enabled: boolean; threshold: number; amount: number }) =>
    call<Pick<BillingMe, "balance" | "card" | "auto_topup" | "receipt_email">>("/api/v1/billing/auto-topup", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  forgetCard: () => call<boolean>("/api/v1/billing/card", { method: "DELETE" }),

  adminAccounts: () => call<{ accounts: AdminBillingAccount[]; signup_bonus: number }>("/api/v1/admin/billing/accounts"),
  adminAdjust: (body: { user_id: string; amount: number; mode: "add" | "set"; note?: string }) =>
    call<{ user_id: string; balance: number }>("/api/v1/admin/billing/adjust", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  adminHistory: (userId: string) =>
    call<{ entries: BillingEntry[]; payments: BillingPayment[] }>(
      `/api/v1/admin/billing/history/${encodeURIComponent(userId)}`,
    ),
};

/** Price of one Studio request as the server computes it (pricing.image_price). */
export function studioPrice(
  prices: BillingPrices["studio"] | undefined,
  model: { key: string; family: string } | undefined,
  options: { resolution?: string; quality?: string; count?: number } = {},
): number | null {
  if (!prices || !model) return null;
  const table = prices[model.key];
  if (!table) return null;
  const count = Math.max(1, options.count ?? 1);
  if (model.family === "gpt") {
    const quality = options.quality && table.by_count?.[options.quality] ? options.quality : "standard";
    const totals = table.by_count?.[quality];
    return totals?.[Math.min(count, totals.length) - 1] ?? table.quality?.[quality] ?? null;
  }
  return table.resolution?.[options.resolution || "1K"] ?? table.resolution?.["1K"] ?? null;
}

export function formatRub(value: number): string {
  return `${new Intl.NumberFormat("ru-RU").format(value)}\u00a0₽`; // no line break before ₽
}
