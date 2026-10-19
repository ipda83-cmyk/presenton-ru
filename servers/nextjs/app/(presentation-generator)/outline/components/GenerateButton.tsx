"use client";

import React from "react";
import { Button } from "@/components/ui/button";
import { useTranslations } from "next-intl";
import { LoadingState } from "../types/index";
import { ChevronRight } from "lucide-react";
import { formatRub } from "../../services/api/billing";
import { isPaying, useBilling } from "@/components/billing/useBilling";

interface GenerateButtonProps {
  loadingState: LoadingState;
  streamState: { isStreaming: boolean; isLoading: boolean };
  selectedTemplateId: string | null;
  onSubmit: () => void;
  /** Slides in the outline: paying users see the price (per slide) on the button. */
  slideCount?: number;
}

const GenerateButton: React.FC<GenerateButtonProps> = ({
  loadingState,
  streamState,
  selectedTemplateId,
  onSubmit,
  slideCount = 0,
}) => {
  const t = useTranslations();
  const { me } = useBilling();
  const price = isPaying(me) && slideCount > 0 ? me.prices.per_slide * slideCount : 0;
  const isDisabled =
    loadingState.isLoading ||
    streamState.isLoading ||
    streamState.isStreaming ||
    !selectedTemplateId;

  const getButtonText = () => {
    if (loadingState.isLoading) return loadingState.message;
    if (streamState.isLoading || streamState.isStreaming) return t("common.loading");
    if (!selectedTemplateId) return t("outline.selectTemplate");
    return price > 0 ? `${t("common.continue")} · ${formatRub(price)}` : t("common.continue");
  };

  return (
    <Button
      disabled={isDisabled}
      onClick={() => {
        onSubmit();
      }}
      className="flex h-[46px] w-fit items-center gap-[2px] rounded-[58px] px-6 py-3 font-syne text-lg font-medium tracking-[-0.18px] text-[#101323] shadow-none hover:opacity-95 disabled:cursor-not-allowed disabled:opacity-60"
      style={{
        background: "linear-gradient(270deg, #D0F6D3 2.4%, #D5E8D7 27.88%, #E2F7D9 69.23%, #F2FADB 100%)",
      }}
    >
      {getButtonText()}
      <ChevronRight
        aria-hidden="true"
        strokeWidth={1.7}
        className="h-[18px] w-[18px]"
      />
    </Button>
  );
};

export default GenerateButton;
