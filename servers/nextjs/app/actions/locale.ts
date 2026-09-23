"use server";

import { cookies } from "next/headers";
import {
  defaultLocale,
  LOCALE_COOKIE,
  normalizePreference,
  type LocalePreference,
} from "@/i18n/config";

const ONE_YEAR_SECONDS = 60 * 60 * 24 * 365;

// Сохранение выбранного языка интерфейса (ru / en / auto) в cookie (работает
// всегда, в т.ч. для анонимных сессий и режима без авторизации). В профиль
// пользователя выбор пишет LanguageSwitcher через PUT /api/v1/auth/locale; при
// входе бэкенд выставляет cookie из профиля (порядок: профиль → cookie → ru).
export async function setLocale(preference: LocalePreference): Promise<void> {
  const next = normalizePreference(preference) ?? defaultLocale;
  const store = await cookies();
  store.set(LOCALE_COOKIE, next, {
    path: "/",
    maxAge: ONE_YEAR_SECONDS,
    sameSite: "lax",
  });
}

// Сохранённый выбор (для подсветки в переключателе); null — выбора не было.
export async function getLocalePreference(): Promise<LocalePreference | null> {
  const store = await cookies();
  return normalizePreference(store.get(LOCALE_COOKIE)?.value);
}
