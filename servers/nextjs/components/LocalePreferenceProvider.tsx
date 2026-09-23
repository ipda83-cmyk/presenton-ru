"use client";

import { createContext, useContext } from "react";
import type { LocalePreference } from "@/i18n/config";

// Сохранённый выбор языка (ru / en / auto) из cookie; null — выбора не было
// (действует язык по умолчанию). Нужен переключателю, чтобы подсветить «Авто».
const LocalePreferenceContext = createContext<LocalePreference | null>(null);

export function LocalePreferenceProvider({
  value,
  children,
}: {
  value: LocalePreference | null;
  children: React.ReactNode;
}) {
  return (
    <LocalePreferenceContext.Provider value={value}>
      {children}
    </LocalePreferenceContext.Provider>
  );
}

export function useLocalePreference(): LocalePreference | null {
  return useContext(LocalePreferenceContext);
}
