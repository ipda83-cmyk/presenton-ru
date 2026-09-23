// Централизованная конфигурация локалей интерфейса.
// Язык презентации (что генерирует ИИ) — это отдельная сущность, здесь речь только про язык UI.

export const locales = ["ru", "en"] as const;

export type AppLocale = (typeof locales)[number];

// Русский — язык по умолчанию (решение Р1).
export const defaultLocale: AppLocale = "ru";

// Выбор пользователя (cookie NEXT_LOCALE и профиль): конкретный язык или
// "auto" — по языку браузера (Accept-Language).
export const AUTO_LOCALE = "auto";
export const localePreferences = ["ru", "en", AUTO_LOCALE] as const;
export type LocalePreference = (typeof localePreferences)[number];

export const LOCALE_COOKIE = "NEXT_LOCALE";

export function isAppLocale(value: string | undefined | null): value is AppLocale {
  return !!value && (locales as readonly string[]).includes(value);
}

// "en-US" -> "en"; неподдерживаемые языки -> null.
function toAppLocale(value: string | null | undefined): AppLocale | null {
  if (!value) return null;
  const primary = value.trim().toLowerCase().replace(/_/g, "-").split("-", 1)[0];
  return isAppLocale(primary) ? primary : null;
}

export function normalizePreference(
  value: string | null | undefined,
): LocalePreference | null {
  if (value?.trim().toLowerCase() === AUTO_LOCALE) return AUTO_LOCALE;
  return toAppLocale(value);
}

const QUALITY = /^(0(\.\d{0,3})?|1(\.0{0,3})?)$/;

// Первый поддерживаемый язык из Accept-Language с учётом q.
// Синхронно с negotiate_locale в servers/fastapi/utils/i18n/__init__.py.
export function negotiateLocale(acceptLanguage: string | null | undefined): AppLocale | null {
  if (!acceptLanguage) return null;
  const ranked: { quality: number; index: number; tag: string }[] = [];
  acceptLanguage.split(",").forEach((part, index) => {
    const [tag, ...params] = part.split(";").map((item) => item.trim());
    let quality = 1;
    for (const param of params) {
      const separator = param.indexOf("=");
      const name = separator === -1 ? param : param.slice(0, separator);
      if (name.trim().toLowerCase() !== "q") continue;
      const value = separator === -1 ? "" : param.slice(separator + 1).trim();
      quality = QUALITY.test(value) ? Number(value) : 0;
    }
    if (tag && quality > 0) ranked.push({ quality, index, tag });
  });
  ranked.sort((a, b) => b.quality - a.quality || a.index - b.index);
  for (const { tag } of ranked) {
    const locale = toAppLocale(tag);
    if (locale) return locale;
  }
  return null;
}

// Язык интерфейса по сохранённому выбору: явный язык — как есть, "auto" — по
// браузеру (иначе язык по умолчанию), выбора нет — язык по умолчанию.
export function resolveLocale(
  preference: string | null | undefined,
  acceptLanguage: string | null | undefined,
): AppLocale {
  const normalized = normalizePreference(preference);
  if (normalized === AUTO_LOCALE) return negotiateLocale(acceptLanguage) ?? defaultLocale;
  return normalized ?? defaultLocale;
}
