import { getRequestConfig } from "next-intl/server";
import { cookies } from "next/headers";
import { defaultLocale, isAppLocale } from "./config";

// Определение локали без префикса в URL (решение Р2): читаем cookie NEXT_LOCALE.
// Порядок: (позже) профиль пользователя -> cookie -> язык по умолчанию (ru).
export default getRequestConfig(async () => {
  const store = await cookies();
  const cookieLocale = store.get("NEXT_LOCALE")?.value;
  const locale = isAppLocale(cookieLocale) ? cookieLocale : defaultLocale;

  return {
    locale,
    messages: (await import(`../messages/${locale}.json`)).default,
  };
});
