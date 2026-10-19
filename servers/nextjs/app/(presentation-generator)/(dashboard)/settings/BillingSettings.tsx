"use client";

import React, { useEffect, useState } from "react";
import { Copy, Eye, EyeOff, Wallet } from "lucide-react";
import { useTranslations } from "next-intl";
import { LLMConfig } from "@/types/llm_config";

type Field =
  | "BILLING_ENABLED"
  | "BILLING_PRICE_PER_SLIDE"
  | "BILLING_SIGNUP_BONUS"
  | "BILLING_OFFER_URL"
  | "YOOKASSA_SHOP_ID"
  | "YOOKASSA_SECRET_KEY"
  | "YOOKASSA_VAT_CODE";

const input =
  "h-12 w-full rounded-lg border border-gray-300 px-4 text-sm text-[#191919] outline-none transition-colors focus:border-blue-500";
const label = "mb-2 block text-sm font-medium text-[#4C5554]";
const hint = "mt-1.5 text-xs leading-5 text-gray-500";

// Payments (administrators only, like all provider settings): prices, the
// signup bonus and the YooKassa shop. Empty fields keep the defaults.
const BillingSettings = ({
  llmConfig,
  setLlmConfig,
}: {
  llmConfig: LLMConfig;
  setLlmConfig: React.Dispatch<React.SetStateAction<LLMConfig>>;
}) => {
  const t = useTranslations("settings.billing");
  const [showKey, setShowKey] = useState(false);
  const [webhook, setWebhook] = useState("");
  const [copied, setCopied] = useState(false);
  const update = (field: Field, value: string) => setLlmConfig((current) => ({ ...current, [field]: value }));
  const enabled = (llmConfig.BILLING_ENABLED ?? "true").toLowerCase() !== "false";

  useEffect(() => {
    setWebhook(`${window.location.origin}/api/v1/billing/yookassa/webhook`);
  }, []);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(webhook);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="space-y-6 rounded-[12px] bg-[#F9F8F8] p-7">
      <div className="mb-4 rounded-[12px] bg-white p-10 pt-8">
        <div className="flex flex-col items-start justify-between gap-8 lg:flex-row lg:gap-10">
          <div className="max-w-[320px]">
            <span className="mb-4 flex h-[60px] w-[60px] items-center justify-center rounded-full bg-[#F4FEF5]">
              <Wallet className="h-7 w-7 text-[#02940F]" aria-hidden="true" />
            </span>
            <h3 className="font-syne text-xl font-normal text-[#191919]">{t("title")}</h3>
            <p className="mt-2 text-sm leading-6 text-[#808080]">{t("desc")}</p>
          </div>
          <div className="w-full max-w-[720px] space-y-6">
            <label className="flex items-center gap-2 text-sm font-medium text-[#191919]">
              <input
                type="checkbox"
                className="h-4 w-4 accent-[#03B015]"
                checked={enabled}
                onChange={(event) => update("BILLING_ENABLED", event.target.checked ? "true" : "false")}
              />
              {t("enabled")}
            </label>
            <p className={`${hint} -mt-4`}>{t("enabledHint")}</p>

            <div className="grid gap-6 sm:grid-cols-2">
              <div>
                <label htmlFor="billing-price-slide" className={label}>{t("pricePerSlide")}</label>
                <input
                  id="billing-price-slide"
                  type="number"
                  inputMode="numeric"
                  min={0}
                  className={input}
                  placeholder="10"
                  value={llmConfig.BILLING_PRICE_PER_SLIDE || ""}
                  onChange={(event) => update("BILLING_PRICE_PER_SLIDE", event.target.value)}
                />
                <p className={hint}>{t("pricePerSlideHint")}</p>
              </div>
              <div>
                <label htmlFor="billing-bonus" className={label}>{t("bonus")}</label>
                <input
                  id="billing-bonus"
                  type="number"
                  inputMode="numeric"
                  min={0}
                  className={input}
                  placeholder="100"
                  value={llmConfig.BILLING_SIGNUP_BONUS || ""}
                  onChange={(event) => update("BILLING_SIGNUP_BONUS", event.target.value)}
                />
                <p className={hint}>{t("bonusHint")}</p>
              </div>
            </div>

            <div className="border-t border-[#EDEEEF] pt-6">
              <h4 className="font-syne text-base text-[#191919]">{t("yookassa")}</h4>
              <p className={hint}>{t("yookassaHint")}</p>
            </div>
            <div className="grid gap-6 sm:grid-cols-2">
              <div>
                <label htmlFor="yookassa-shop" className={label}>{t("shopId")}</label>
                <input
                  id="yookassa-shop"
                  className={input}
                  autoComplete="off"
                  value={llmConfig.YOOKASSA_SHOP_ID || ""}
                  onChange={(event) => update("YOOKASSA_SHOP_ID", event.target.value)}
                />
              </div>
              <div>
                <label htmlFor="yookassa-secret" className={label}>{t("secretKey")}</label>
                <div className="relative">
                  <input
                    id="yookassa-secret"
                    type={showKey ? "text" : "password"}
                    autoComplete="off"
                    className={`${input} pr-12`}
                    value={llmConfig.YOOKASSA_SECRET_KEY || ""}
                    onChange={(event) => update("YOOKASSA_SECRET_KEY", event.target.value)}
                  />
                  <button
                    type="button"
                    className="absolute inset-y-0 right-0 flex w-12 items-center justify-center rounded-r-lg text-gray-500 hover:text-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500"
                    onClick={() => setShowKey((value) => !value)}
                    aria-label={showKey ? t("hideKey") : t("showKey")}
                    aria-pressed={showKey}
                  >
                    {showKey ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
                  </button>
                </div>
              </div>
              <div>
                <label htmlFor="yookassa-vat" className={label}>{t("vatCode")}</label>
                <input
                  id="yookassa-vat"
                  type="number"
                  inputMode="numeric"
                  min={1}
                  max={12}
                  className={input}
                  placeholder="1"
                  value={llmConfig.YOOKASSA_VAT_CODE || ""}
                  onChange={(event) => update("YOOKASSA_VAT_CODE", event.target.value)}
                />
                <p className={hint}>{t("vatCodeHint")}</p>
              </div>
              <div>
                <label htmlFor="billing-offer" className={label}>{t("offerUrl")}</label>
                <input
                  id="billing-offer"
                  type="url"
                  className={input}
                  placeholder="https://"
                  value={llmConfig.BILLING_OFFER_URL || ""}
                  onChange={(event) => update("BILLING_OFFER_URL", event.target.value)}
                />
                <p className={hint}>{t("offerUrlHint")}</p>
              </div>
            </div>
            <div>
              <p className={label}>{t("webhook")}</p>
              <div className="flex gap-2">
                <code className="flex min-h-12 flex-1 items-center overflow-x-auto rounded-lg border border-[#EDEEEF] bg-[#F9FAFB] px-4 text-xs text-[#191919]">
                  {webhook}
                </code>
                <button
                  type="button"
                  onClick={() => void copy()}
                  className="inline-flex min-h-12 items-center gap-1.5 rounded-lg border border-[#EDEEEF] px-3 text-sm text-[#191919] hover:bg-[#F6F6F9] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                >
                  <Copy className="h-4 w-4" aria-hidden="true" />
                  {copied ? t("copied") : t("copy")}
                </button>
              </div>
              <p className={hint}>{t("webhookHint")}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default BillingSettings;
