"use client";

import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { setLocale } from "@/app/actions/locale";
import { locales, type AppLocale } from "@/i18n/config";

// Переключатель языка интерфейса (RU/EN). Сохраняет выбор и перерисовывает страницу.
export default function LanguageSwitcher({ className = "" }: { className?: string }) {
  const active = useLocale() as AppLocale;
  const t = useTranslations("language");
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  const change = (next: AppLocale) => {
    if (next === active || pending) return;
    startTransition(async () => {
      await setLocale(next);
      router.refresh();
    });
  };

  return (
    <div
      role="group"
      aria-label={t("label")}
      className={`inline-flex items-center rounded-full border border-[#EDEEEF] bg-[#F7F6F9] p-0.5 ${className}`}
    >
      {locales.map((loc) => (
        <button
          key={loc}
          type="button"
          onClick={() => change(loc)}
          disabled={pending}
          aria-pressed={active === loc}
          title={t("switchTo", { lang: t(loc) })}
          className={`px-2.5 py-1 text-xs font-semibold font-manrope rounded-full transition-colors ${
            active === loc
              ? "bg-white text-[#5141E5] shadow-sm"
              : "text-gray-500 hover:text-gray-800"
          }`}
        >
          {loc.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
