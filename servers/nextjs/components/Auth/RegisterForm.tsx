"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import AuthCard, { authButtonClass, authInputClass, authLinkClass } from "./AuthCard";
import SmartCaptcha from "./SmartCaptcha";
import { AccountApi, AccountError, type RegistrationInfo } from "@/utils/accountApi";

export default function RegisterForm() {
  const t = useTranslations("account");
  const router = useRouter();
  const [info, setInfo] = useState<RegistrationInfo | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [offer, setOffer] = useState(false);
  const [privacy, setPrivacy] = useState(false);
  const [captcha, setCaptcha] = useState<string | null>(null);
  const [captchaReset, setCaptchaReset] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    AccountApi.info()
      .then(setInfo)
      .catch(() => setInfo({ open: false, password_min: 8, captcha_key: null, offer_url: null, privacy_url: null, bonus: 0 }));
  }, []);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!info) return;
    setError(null);
    if (password.length < info.password_min) return setError(t("passwordShort", { min: info.password_min }));
    if (password !== confirm) return setError(t("passwordsDiffer"));
    if (!offer || !privacy) return setError(t("consentNeeded"));
    if (info.captcha_key && !captcha) return setError(t("captchaNeeded"));
    setBusy(true);
    try {
      await AccountApi.register({ email: email.trim(), password, accept_offer: offer, accept_privacy: privacy, captcha });
      router.replace("/dashboard");
    } catch (reason) {
      setError(reason instanceof AccountError ? reason.message : t("failed"));
      if (info.captcha_key) setCaptchaReset((value) => value + 1);
      setBusy(false);
    }
  };

  if (!info) {
    return (
      <AuthCard title={t("register.title")}>
        <p className="flex items-center gap-2 text-sm text-[#6B7280]">
          <Loader2 className="h-4 w-4 animate-spin" /> {t("loading")}
        </p>
      </AuthCard>
    );
  }

  if (!info.open) {
    return (
      <AuthCard title={t("register.closedTitle")} intro={t("register.closedText")}>
        <Link href="/" className={`${authButtonClass} block text-center`}>
          {t("toSignIn")}
        </Link>
      </AuthCard>
    );
  }

  const docLink = (url: string | null, label: string) =>
    url ? (
      <a href={url} target="_blank" rel="noreferrer" className={authLinkClass}>
        {label}
      </a>
    ) : (
      label
    );

  return (
    <AuthCard
      eyebrow="Kvant AI Studio"
      title={t("register.title")}
      intro={info.bonus > 0 ? t("register.introBonus", { bonus: info.bonus }) : t("register.intro")}
      footer={
        <>
          {t("register.haveAccount")}{" "}
          <Link href="/" className={authLinkClass}>
            {t("toSignIn")}
          </Link>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-4" noValidate>
        <label className="block space-y-2">
          <span className="block text-sm font-medium text-[#374151]">{t("email")}</span>
          <input
            id="register-email"
            type="email"
            autoComplete="email"
            required
            maxLength={254}
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="name@company.ru"
            className={authInputClass}
            disabled={busy}
          />
        </label>
        <label className="block space-y-2">
          <span className="block text-sm font-medium text-[#374151]">{t("password")}</span>
          <input
            id="register-password"
            type="password"
            autoComplete="new-password"
            required
            minLength={info.password_min}
            maxLength={128}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder={t("passwordHint", { min: info.password_min })}
            className={authInputClass}
            disabled={busy}
          />
        </label>
        <label className="block space-y-2">
          <span className="block text-sm font-medium text-[#374151]">{t("passwordAgain")}</span>
          <input
            id="register-confirm"
            type="password"
            autoComplete="new-password"
            required
            maxLength={128}
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
            className={authInputClass}
            disabled={busy}
          />
        </label>

        <label className="flex items-start gap-3 text-xs leading-5 text-[#374151]">
          <input id="register-offer" type="checkbox" checked={offer} onChange={(event) => setOffer(event.target.checked)} className="mt-0.5 h-4 w-4 accent-[#03B015]" />
          <span>
            {t("register.acceptOffer")} {docLink(info.offer_url, t("register.offer"))}
          </span>
        </label>
        <label className="flex items-start gap-3 text-xs leading-5 text-[#374151]">
          <input id="register-privacy" type="checkbox" checked={privacy} onChange={(event) => setPrivacy(event.target.checked)} className="mt-0.5 h-4 w-4 accent-[#03B015]" />
          <span>
            {t("register.acceptPrivacy")} {docLink(info.privacy_url, t("register.privacy"))}
          </span>
        </label>

        {info.captcha_key ? <SmartCaptcha siteKey={info.captcha_key} onToken={setCaptcha} resetSignal={captchaReset} /> : null}

        {error ? (
          <p role="alert" className="rounded-lg border border-[#FECDCA] bg-[#FEF3F2] px-4 py-3 text-xs text-[#B42318]">
            {error}
          </p>
        ) : null}

        <button type="submit" disabled={busy} className={authButtonClass}>
          {busy ? t("register.creating") : t("register.submit")}
        </button>
      </form>
    </AuthCard>
  );
}
