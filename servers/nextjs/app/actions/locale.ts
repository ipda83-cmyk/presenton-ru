"use server";

import { cookies } from "next/headers";
import { defaultLocale, isAppLocale, type AppLocale } from "@/i18n/config";

const ONE_YEAR_SECONDS = 60 * 60 * 24 * 365;

// Сохранение выбранного языка интерфейса в cookie (работает всегда, в т.ч. для
// анонимных сессий и режима без авторизации). В профиль пользователя выбор пишет
// LanguageSwitcher через PUT /api/v1/auth/locale; при входе бэкенд выставляет
// cookie из профиля (порядок: профиль → cookie → ru).
export async function setLocale(locale: AppLocale): Promise<void> {
  const next = isAppLocale(locale) ? locale : defaultLocale;
  const store = await cookies();
  store.set("NEXT_LOCALE", next, {
    path: "/",
    maxAge: ONE_YEAR_SECONDS,
    sameSite: "lax",
  });
}
