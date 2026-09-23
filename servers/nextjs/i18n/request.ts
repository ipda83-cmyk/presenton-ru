import { getRequestConfig } from "next-intl/server";
import { cookies, headers } from "next/headers";
import { LOCALE_COOKIE, resolveLocale } from "./config";

// Определение локали без префикса в URL (решение Р2): cookie NEXT_LOCALE хранит
// выбор (ru / en / auto). Профиль пользователя попадает в cookie при входе.
// "auto" — язык браузера из Accept-Language; нет выбора — русский.
export default getRequestConfig(async () => {
  const [store, requestHeaders] = await Promise.all([cookies(), headers()]);
  const locale = resolveLocale(
    store.get(LOCALE_COOKIE)?.value,
    requestHeaders.get("accept-language"),
  );

  return {
    locale,
    messages: (await import(`../messages/${locale}.json`)).default,
  };
});
