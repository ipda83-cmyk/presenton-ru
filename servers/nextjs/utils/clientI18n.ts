// Translations for non-React client modules (API services, utils).
//
// Hooks cannot be called outside components, so <ClientI18nBridge /> (rendered
// inside NextIntlClientProvider in the root layout) registers the current
// root-level translator here. Until it has rendered — and on the server, where
// these modules may also be evaluated — the English fallback is returned.

type TranslationValues = Record<string, string | number>;
type Translator = (key: string, values?: TranslationValues) => string;

let translator: Translator | null = null;

export function setClientTranslator(next: Translator | null): void {
  translator = next;
}

function interpolate(text: string, values?: TranslationValues): string {
  if (!values) return text;
  return text.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in values ? String(values[name]) : match
  );
}

/**
 * Translate `key` (full path from the catalog root) in the UI language.
 * `fallback` is the English text with the same `{placeholders}`.
 */
export function tr(
  key: string,
  fallback: string,
  values?: TranslationValues
): string {
  if (translator) {
    try {
      return translator(key, values);
    } catch {
      // fall back to English below
    }
  }
  return interpolate(fallback, values);
}
