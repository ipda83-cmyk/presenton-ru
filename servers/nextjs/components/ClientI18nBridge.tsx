"use client";

import { useTranslations } from "next-intl";

import { setClientTranslator } from "@/utils/clientI18n";

// Registers the root translator for non-React modules (see utils/clientI18n).
// Assigned during render so it is in place before any sibling effect or
// user-triggered request can surface an error message.
export default function ClientI18nBridge() {
  // Keys arrive as plain strings from non-React modules, so the strictly typed
  // root translator is widened here (tests/verify cover key existence).
  const t = useTranslations() as unknown as (
    key: string,
    values?: Record<string, string | number>
  ) => string;
  // This component is also rendered during SSR, where a module-level
  // translator would be shared by concurrent requests in different locales.
  // Register it in the browser only; on the server tr() keeps English.
  if (typeof window !== "undefined") {
    setClientTranslator(t);
  }
  return null;
}
