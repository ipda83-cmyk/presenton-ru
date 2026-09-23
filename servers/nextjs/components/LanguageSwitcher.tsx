"use client";

import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import { Globe } from "lucide-react";
import { setLocale } from "@/app/actions/locale";
import {
  AUTO_LOCALE,
  localePreferences,
  type AppLocale,
  type LocalePreference,
} from "@/i18n/config";
import { useLocalePreference } from "@/components/LocalePreferenceProvider";
import { getApiUrl } from "@/utils/api";

const SIZES = {
  sm: {
    group: "h-8 p-0.5 pl-2 gap-0.5",
    icon: "h-3.5 w-3.5",
    button: "h-full px-2.5 text-xs",
  },
  toolbar: {
    group: "h-[38px] p-1 pl-2.5 gap-0.5",
    icon: "h-3.5 w-3.5",
    button: "h-full px-2.5 text-xs",
  },
  md: {
    group: "h-[42.24px] p-1 pl-3 gap-1",
    icon: "h-4 w-4",
    button: "h-full px-3 text-[13px]",
  },
} as const;

// Переключатель языка интерфейса: RU / EN / Авто (по языку браузера).
// Сохраняет выбор (cookie + профиль пользователя) и перерисовывает страницу.
export default function LanguageSwitcher({
  className = "",
  size = "sm",
}: {
  className?: string;
  size?: keyof typeof SIZES;
}) {
  const locale = useLocale() as AppLocale;
  const preference = useLocalePreference();
  const t = useTranslations("language");
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const saved: LocalePreference = preference ?? locale;
  const [selected, setSelected] = useState<LocalePreference>(saved);
  const styles = SIZES[size];

  useEffect(() => setSelected(saved), [saved]);

  const change = (next: LocalePreference) => {
    if (next === selected || pending) return;
    setSelected(next);
    startTransition(async () => {
      // Signed-in users keep the choice in their profile so it follows them
      // to other browsers. Best effort: anonymous visitors get a 401 and the
      // cookie below still applies.
      try {
        await fetch(getApiUrl("/api/v1/auth/locale"), {
          method: "PUT",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ locale: next }),
        });
      } catch {
        // offline / backend unavailable: keep the local choice
      }
      await setLocale(next);
      router.refresh();
    });
  };

  const label = (option: LocalePreference) =>
    option === AUTO_LOCALE ? t("auto") : option.toUpperCase();
  const hint = (option: LocalePreference) =>
    option === AUTO_LOCALE ? t("autoHint", { lang: t(locale) }) : t(option);

  return (
    <div
      role="group"
      aria-label={t("label")}
      title={t("label")}
      className={`inline-flex shrink-0 items-center rounded-full border border-[#EDEEEF] bg-white ${styles.group} ${className}`}
    >
      <Globe className={`${styles.icon} shrink-0 text-[#667085]`} aria-hidden="true" />
      {localePreferences.map((option) => {
        const active = selected === option;
        return (
          <button
            key={option}
            type="button"
            onClick={() => change(option)}
            disabled={pending}
            aria-pressed={active}
            title={hint(option)}
            className={`${styles.button} inline-flex items-center rounded-full font-syne font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7A5AF8] disabled:cursor-wait ${
              active
                ? "bg-[#F4F3FF] text-[#5141E5]"
                : "text-[#475467] hover:bg-[#F8F8FA] hover:text-[#101323]"
            }`}
          >
            {label(option)}
          </button>
        );
      })}
    </div>
  );
}
