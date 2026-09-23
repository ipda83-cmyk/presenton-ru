'use client';

import React, { useEffect, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { LLMConfig } from '@/types/llm_config';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { useTranslations } from 'next-intl';

export type BedrockManualPatch = Partial<
  Pick<
    LLMConfig,
    | 'BEDROCK_MODEL'
    | 'BEDROCK_REGION'
    | 'BEDROCK_API_KEY'
    | 'BEDROCK_AWS_ACCESS_KEY_ID'
    | 'BEDROCK_AWS_SECRET_ACCESS_KEY'
    | 'BEDROCK_AWS_SESSION_TOKEN'
    | 'BEDROCK_PROFILE_NAME'
  >
>;

interface BedrockManualFieldsProps {
  llmConfig: LLMConfig;
  onPatch: (patch: BedrockManualPatch) => void;
}

function hasAdvancedContent(config: LLMConfig): boolean {
  return (
    !!(config.BEDROCK_AWS_SESSION_TOKEN || '').trim() ||
    !!(config.BEDROCK_PROFILE_NAME || '').trim()
  );
}

export default function BedrockManualFields({
  llmConfig,
  onPatch,
}: BedrockManualFieldsProps) {
  const t = useTranslations('fields');
  const [advancedOpen, setAdvancedOpen] = useState(() => hasAdvancedContent(llmConfig));

  useEffect(() => {
    if (hasAdvancedContent(llmConfig)) setAdvancedOpen(true);
  }, [llmConfig.BEDROCK_AWS_SESSION_TOKEN, llmConfig.BEDROCK_PROFILE_NAME]);

  const inputClass =
    'w-full min-w-0 rounded-lg border border-gray-300 px-3 py-3 text-sm outline-none transition-colors focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20';

  return (
    <div className="mt-3 w-full min-w-0 max-w-full space-y-4">
      <div className="space-y-1.5">
        <label className="block text-sm font-medium text-gray-700">{t("model")}</label>
        <input
          type="text"
          value={llmConfig.BEDROCK_MODEL || ''}
          onChange={(e) => onPatch({ BEDROCK_MODEL: e.target.value })}
          className={inputClass}
          placeholder={t("egValue", { value: "us.anthropic.claude-3-5-haiku-20241022-v1:0" })}
        />
      </div>

      <div className="space-y-1.5">
        <label className="block text-sm font-medium text-gray-700">{t("region")}</label>
        <input
          type="text"
          value={llmConfig.BEDROCK_REGION || ''}
          onChange={(e) => onPatch({ BEDROCK_REGION: e.target.value })}
          className={inputClass}
          placeholder={t("egValue", { value: "us-east-1" })}
        />
      </div>

      <div className="space-y-1.5">
        <label className="block text-sm font-medium text-gray-700">
          {t("bedrockApiKeyOptional")}
        </label>
        <input
          type="password"
          value={llmConfig.BEDROCK_API_KEY || ''}
          onChange={(e) => onPatch({ BEDROCK_API_KEY: e.target.value })}
          className={inputClass}
          placeholder={t("bedrockApiKeyPh")}
        />
      </div>

      <div className="space-y-1.5">
        <label className="block text-sm font-medium text-gray-700">{t("awsAccessKeyId")}</label>
        <input
          type="text"
          value={llmConfig.BEDROCK_AWS_ACCESS_KEY_ID || ''}
          onChange={(e) => onPatch({ BEDROCK_AWS_ACCESS_KEY_ID: e.target.value })}
          className={inputClass}
          placeholder={t("awsAccessKeyIdPh")}
        />
      </div>

      <div className="space-y-1.5">
        <label className="block text-sm font-medium text-gray-700">
          {t("awsSecretAccessKey")}
        </label>
        <input
          type="password"
          value={llmConfig.BEDROCK_AWS_SECRET_ACCESS_KEY || ''}
          onChange={(e) => onPatch({ BEDROCK_AWS_SECRET_ACCESS_KEY: e.target.value })}
          className={inputClass}
          placeholder={t("awsSecretAccessKeyPh")}
        />
      </div>

      <p className="text-xs text-gray-500">
        {t("bedrockAuthHint")}
      </p>

      <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
        <CollapsibleTrigger asChild>
          <button
            type="button"
            className="flex w-full min-w-0 items-center justify-between gap-2 rounded-lg border border-gray-200 bg-[#F9F9FA] px-3 py-2.5 text-left text-sm font-medium text-gray-800 transition-colors hover:bg-gray-100"
          >
            <span>{t("advancedSettings")}</span>
            <ChevronDown
              className={cn(
                'h-4 w-4 shrink-0 text-gray-600 transition-transform duration-200',
                advancedOpen && 'rotate-180'
              )}
              aria-hidden
            />
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent className="space-y-3 overflow-hidden">
          <div className="space-y-3 border-t border-gray-100 pt-3">
            <div className="space-y-1.5">
              <label className="block text-sm font-medium text-gray-700">
                {t("awsSessionToken")}
              </label>
              <input
                type="password"
                value={llmConfig.BEDROCK_AWS_SESSION_TOKEN || ''}
                onChange={(e) => onPatch({ BEDROCK_AWS_SESSION_TOKEN: e.target.value })}
                className={inputClass}
                placeholder={t("optional")}
              />
            </div>
            <div className="space-y-1.5">
              <label className="block text-sm font-medium text-gray-700">
                {t("awsProfileName")}
              </label>
              <input
                type="text"
                value={llmConfig.BEDROCK_PROFILE_NAME || ''}
                onChange={(e) => onPatch({ BEDROCK_PROFILE_NAME: e.target.value })}
                className={inputClass}
                placeholder={t("optional")}
              />
            </div>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}
