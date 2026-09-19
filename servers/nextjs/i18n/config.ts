// Централизованная конфигурация локалей интерфейса.
// Язык презентации (что генерирует ИИ) — это отдельная сущность, здесь речь только про язык UI.

export const locales = ["ru", "en"] as const;

export type AppLocale = (typeof locales)[number];

// Русский — язык по умолчанию (решение Р1).
export const defaultLocale: AppLocale = "ru";

export function isAppLocale(value: string | undefined | null): value is AppLocale {
  return !!value && (locales as readonly string[]).includes(value);
}
