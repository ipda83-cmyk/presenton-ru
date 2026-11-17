"use client";

import { useEffect, useRef } from "react";
import { useLocale } from "next-intl";

// Yandex SmartCaptcha widget (https://yandex.cloud/docs/smartcaptcha/).

type SmartCaptchaApi = {
  render: (container: HTMLElement, options: Record<string, unknown>) => number;
  reset: (widgetId?: number) => void;
};

declare global {
  interface Window {
    smartCaptcha?: SmartCaptchaApi;
  }
}

const SCRIPT_URL = "https://smartcaptcha.yandexcloud.net/captcha.js";

function loadScript(): Promise<SmartCaptchaApi> {
  if (window.smartCaptcha) return Promise.resolve(window.smartCaptcha);
  return new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${SCRIPT_URL}"]`);
    const script = existing ?? document.createElement("script");
    const done = () => (window.smartCaptcha ? resolve(window.smartCaptcha) : reject(new Error("SmartCaptcha did not load")));
    script.addEventListener("load", done, { once: true });
    script.addEventListener("error", () => reject(new Error("SmartCaptcha did not load")), { once: true });
    if (!existing) {
      script.src = SCRIPT_URL;
      script.async = true;
      script.defer = true;
      document.head.appendChild(script);
    }
  });
}

/** Renders the captcha; `onToken` gets the token, or null when it expires. */
export default function SmartCaptcha({
  siteKey,
  onToken,
  resetSignal,
}: {
  siteKey: string;
  onToken: (token: string | null) => void;
  /** Change it to show a fresh captcha (after a refused attempt). */
  resetSignal?: number;
}) {
  const locale = useLocale();
  const container = useRef<HTMLDivElement>(null);
  const widget = useRef<number | undefined>(undefined);
  const callback = useRef(onToken);
  callback.current = onToken;

  useEffect(() => {
    let cancelled = false;
    loadScript()
      .then((api) => {
        if (cancelled || !container.current || widget.current !== undefined) return;
        widget.current = api.render(container.current, {
          sitekey: siteKey,
          hl: locale === "en" ? "en" : "ru",
          callback: (token: string) => callback.current(token),
          "token-expired": () => callback.current(null),
        });
      })
      .catch(() => callback.current(null));
    return () => {
      cancelled = true;
    };
  }, [locale, siteKey]);

  useEffect(() => {
    if (resetSignal && widget.current !== undefined) {
      window.smartCaptcha?.reset(widget.current);
      callback.current(null);
    }
  }, [resetSignal]);

  return <div ref={container} className="min-h-[102px]" />;
}
