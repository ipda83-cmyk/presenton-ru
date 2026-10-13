"use client";

import { useCallback, useEffect, useState } from "react";
import { BillingApi, type BillingMe } from "@/app/(presentation-generator)/services/api/billing";
import { onBillingChanged } from "@/utils/billingEvents";

// The sidebar, the top bar and the page may all ask at once: one request serves them.
let inflight: Promise<BillingMe> | null = null;
function fetchMe(): Promise<BillingMe> {
  inflight ??= BillingApi.me().finally(() => {
    inflight = null;
  });
  return inflight;
}

/** The user's balance, prices and payment settings; refreshes after paid
 * requests and when the tab gets focus (e.g. back from the payment page). */
export function useBilling(enabled = true) {
  const [me, setMe] = useState<BillingMe | null>(null);
  const [loading, setLoading] = useState(enabled);

  const refresh = useCallback(async () => {
    try {
      setMe(await fetchMe());
    } catch {
      // Signed out or the server is away: keep what we had.
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    void refresh();
    const off = onBillingChanged(() => void refresh());
    const onFocus = () => void refresh();
    window.addEventListener("focus", onFocus);
    return () => {
      off();
      window.removeEventListener("focus", onFocus);
    };
  }, [enabled, refresh]);

  return { me, loading, refresh, setMe };
}

/** True when the signed-in user pays for generations (not an administrator). */
export function isPaying(me: BillingMe | null): me is BillingMe & { balance: number } {
  return Boolean(me?.enabled && !me.free && typeof me.balance === "number");
}
