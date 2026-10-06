import ToolTip from '@/components/ToolTip';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { Pencil, SlidersHorizontal, X } from 'lucide-react';
import React, { useEffect, useState } from 'react';
import { PresentationConfig, ToneType, VerbosityType } from '../type';
import { cn } from '@/lib/utils';
import { useTranslations } from 'next-intl';

interface ConfigurationSelectsProps {
    config: PresentationConfig;
    onConfigChange: (key: keyof PresentationConfig, value: any) => void;
    compact?: boolean;
    className?: string;
}

type AdvancedKey =
    | 'tone'
    | 'verbosity'
    | 'instructions'
    | 'includeTableOfContents'
    | 'includeTitleSlide';
type AdvancedValues = Pick<PresentationConfig, AdvancedKey>;

const toggleClassName =
    'h-[22px] w-[36px] border-0 bg-[#D8D8DD] data-[state=checked]:bg-[#7A5AF8] ';

const pickAdvanced = (config: PresentationConfig): AdvancedValues => ({
    tone: config.tone,
    verbosity: config.verbosity,
    instructions: config.instructions,
    includeTableOfContents: config.includeTableOfContents,
    includeTitleSlide: config.includeTitleSlide,
});

// Instructions, tone, verbosity and slide toggles: shared by the dialog
// (edits a draft, saved with a button) and the inline panel (applies at once).
const AdvancedSettingsFields = ({
    values,
    onChange,
    idPrefix,
    autoFocusInstructions = false,
}: {
    values: AdvancedValues;
    onChange: <K extends AdvancedKey>(key: K, value: AdvancedValues[K]) => void;
    idPrefix: string;
    autoFocusInstructions?: boolean;
}) => {
    const t = useTranslations("upload.advanced");
    const instructionsId = `${idPrefix}-advanced-instructions`;

    return (
        <>
            <div className="bg-[#ECE8F6] px-6 py-5 min-[1800px]:px-8 min-[1800px]:py-6">
                <div className="flex items-start gap-2">
                    <Pencil className="mt-[3px] h-3.5 w-3.5 text-[#1C1B24] min-[1800px]:h-4 min-[1800px]:w-4" />
                    <div className="w-full">
                        <label
                            htmlFor={instructionsId}
                            className="block font-syne text-sm font-semibold leading-none text-[#1F1D2A] min-[1800px]:text-base"
                        >
                            {t("instructionsLabel")}
                        </label>
                        <Textarea
                            id={instructionsId}
                            value={values.instructions}
                            autoFocus={autoFocusInstructions}
                            rows={2}
                            onChange={(event) => onChange('instructions', event.target.value)}
                            placeholder={t("instructionsPlaceholder")}
                            className="mt-1 min-h-[64px] resize-none border-0 bg-transparent p-0 text-sm leading-[1.3] text-[#242430] shadow-none placeholder:text-[#7C7B87] focus-visible:ring-0 focus-visible:ring-offset-0 min-[1800px]:min-h-[80px] min-[1800px]:text-base"
                        />
                    </div>
                </div>
            </div>

            <div className="space-y-4 px-6 pb-5 pt-3.5 min-[1800px]:space-y-5 min-[1800px]:px-8 min-[1800px]:pb-7 min-[1800px]:pt-5">
                <div className="flex items-center justify-between gap-3">
                    <label className="font-syne text-sm font-semibold leading-none text-[#1F1D2A] min-[1800px]:text-base">{t("tone")}</label>
                    <Select
                        value={values.tone}
                        onValueChange={(value) => onChange('tone', value as ToneType)}
                    >
                        <SelectTrigger
                            aria-label={t("tone")}
                            className="w-[150px] rounded-xl border-[#DBDBE1] bg-white p-2.5 font-syne text-sm font-medium text-[#2C2B37] shadow-none focus:ring-0 focus-visible:ring-0 min-[1800px]:w-[170px] min-[1800px]:text-base"
                        >
                            <SelectValue placeholder={t("tonePlaceholder")} />
                        </SelectTrigger>
                        <SelectContent className="z-[120] font-syne">
                            {Object.values(ToneType).map((tone) => (
                                <SelectItem key={tone} value={tone} className="text-sm font-medium min-[1800px]:text-base">
                                    {t(`toneOptions.${tone}`)}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>

                <div className="flex items-center justify-between gap-3">
                    <label className="font-syne text-sm font-semibold leading-none text-[#1F1D2A] min-[1800px]:text-base">{t("verbosity")}</label>
                    <Select
                        value={values.verbosity}
                        onValueChange={(value) => onChange('verbosity', value as VerbosityType)}
                    >
                        <SelectTrigger
                            aria-label={t("verbosity")}
                            className="w-[150px] rounded-xl border-[#DBDBE1] bg-white p-2.5 font-syne text-sm font-medium text-[#2C2B37] shadow-none focus:ring-0 focus-visible:ring-0 min-[1800px]:w-[170px] min-[1800px]:text-base"
                        >
                            <SelectValue placeholder={t("verbosityPlaceholder")} />
                        </SelectTrigger>
                        <SelectContent className="z-[120] font-syne">
                            {Object.values(VerbosityType).map((verbosity) => (
                                <SelectItem key={verbosity} value={verbosity} className="text-sm font-medium min-[1800px]:text-base">
                                    {t(`verbosityOptions.${verbosity.replace("-", "_")}`)}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>

                <div className="flex items-center justify-between gap-3">
                    <label className="font-syne text-sm font-semibold leading-none text-[#1F1D2A] min-[1800px]:text-base">
                        {t("includeToc")}
                    </label>
                    <Switch
                        aria-label={t("includeToc")}
                        checked={values.includeTableOfContents}
                        onCheckedChange={(checked) => onChange('includeTableOfContents', checked)}
                        className={toggleClassName}
                    />
                </div>

                <div className="flex items-center justify-between gap-3">
                    <label className="font-syne text-sm font-semibold leading-none text-[#1F1D2A] min-[1800px]:text-base">{t("titleSlide")}</label>
                    <Switch
                        aria-label={t("titleSlide")}
                        checked={values.includeTitleSlide}
                        onCheckedChange={(checked) => onChange('includeTitleSlide', checked)}
                        className={toggleClassName}
                    />
                </div>
            </div>
        </>
    );
};

// Always-visible panel beside the prompt on wide screens. Changes apply at
// once, like the other generation controls.
export const AdvancedSettingsPanel = ({
    config,
    onConfigChange,
    className,
}: Omit<ConfigurationSelectsProps, 'compact'>) => {
    const t = useTranslations("upload.advanced");

    return (
        <section
            aria-labelledby="advanced-settings-panel-title"
            className={cn(
                "overflow-hidden rounded-[20px] border border-[#E7E9F2] bg-[#F3F3F6]",
                className,
            )}
            data-testid="advanced-settings-panel"
        >
            <div className="flex items-center gap-2 bg-[#F8F8FA] px-6 py-4 min-[1800px]:px-8">
                <SlidersHorizontal className="h-3.5 w-3.5 text-[#1C1C27]" aria-hidden="true" />
                <div>
                    <h2
                        id="advanced-settings-panel-title"
                        className="font-syne text-sm font-semibold leading-none text-[#191919] min-[1800px]:text-base"
                    >
                        {t("title")}
                    </h2>
                    <p className="mt-1 text-xs text-[#808080]">{t("subtitle")}</p>
                </div>
            </div>
            <AdvancedSettingsFields
                values={pickAdvanced(config)}
                onChange={(key, value) => onConfigChange(key, value)}
                idPrefix="panel"
            />
        </section>
    );
};

const AdvanceSettings = ({
    config,
    onConfigChange,
    compact = false,
    className,
}: ConfigurationSelectsProps) => {
    const t = useTranslations("upload.advanced");
    const [openAdvanced, setOpenAdvanced] = useState(false);
    const [advancedDraft, setAdvancedDraft] = useState<AdvancedValues>(() =>
        pickAdvanced(config),
    );

    const handleOpenAdvanced = () => {
        setAdvancedDraft(pickAdvanced(config));
        setOpenAdvanced(true);
    };

    const handleCloseAdvanced = () => {
        setOpenAdvanced(false);
    };

    const handleSaveAdvanced = () => {
        onConfigChange('tone', advancedDraft.tone);
        onConfigChange('verbosity', advancedDraft.verbosity);
        onConfigChange('instructions', advancedDraft.instructions);
        onConfigChange('includeTableOfContents', advancedDraft.includeTableOfContents);
        onConfigChange('includeTitleSlide', advancedDraft.includeTitleSlide);
        setOpenAdvanced(false);
    };

    useEffect(() => {
        if (!openAdvanced) {
            return;
        }

        const previousOverflow = document.body.style.overflow;

        const onKeyDown = (event: KeyboardEvent) => {
            if (event.key === 'Escape') {
                handleCloseAdvanced();
            }
        };

        document.body.style.overflow = 'hidden';
        window.addEventListener('keydown', onKeyDown);

        return () => {
            document.body.style.overflow = previousOverflow;
            window.removeEventListener('keydown', onKeyDown);
        };
    }, [openAdvanced]);

    return (
        <>
            <div className={cn(!compact && "ml-auto", className)}>
                <ToolTip content={t("button")}>
                    <button
                        aria-label={t("button")}
                        title={t("button")}
                        type="button"
                        onClick={handleOpenAdvanced}
                        className={cn(
                            "flex items-center justify-center rounded-full border bg-white text-[#1C1C27] transition hover:bg-[#F7F7FA] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#5141E5]/25",
                            compact
                                ? "h-[34px] w-[42px] border-[#EDEEEF] shadow-none"
                                : "h-10 w-10 border-[#E4E5E8] shadow-sm min-[1800px]:h-11 min-[1800px]:w-11 min-[2200px]:h-12 min-[2200px]:w-12"
                        )}
                        data-testid="advanced-settings-button"
                    >
                        <SlidersHorizontal
                            className={cn(
                                compact
                                    ? "h-3.5 w-3.5"
                                    : "h-3.5 w-3.5 min-[1800px]:h-4 min-[1800px]:w-4 min-[2200px]:h-5 min-[2200px]:w-5"
                            )}
                            aria-hidden="true"
                        />
                    </button>
                </ToolTip>
            </div>

            {openAdvanced && (
                <div
                    className="fixed inset-0 z-[70] bg-black/35 flex items-center justify-center"
                    onClick={handleCloseAdvanced}
                    role="presentation"
                >
                    <div
                        role="dialog"
                        aria-modal="true"
                        aria-label={t("title")}
                        className="relative mx-auto mt-[108px] w-[calc(100vw-2rem)] max-w-[640px] overflow-visible min-[1800px]:max-w-[720px] min-[2200px]:max-w-[800px]"
                        onClick={(event) => event.stopPropagation()}
                    >
                        <button
                            type="button"
                            onClick={handleCloseAdvanced}
                            aria-label={t("close")}
                            className="absolute -top-[62px] right-2 flex h-[50px] w-[50px] items-center justify-center rounded-full border border-[#E7E7EC] bg-white text-[#2C2B35] shadow-sm transition hover:bg-[#F8F8FB] min-[1800px]:h-[56px] min-[1800px]:w-[56px]"
                        >
                            <X className="h-3.5 w-3.5 min-[1800px]:h-4 min-[1800px]:w-4" />
                        </button>

                        <div className="overflow-hidden rounded-[24px] border border-[#E7E9F2] bg-[#F3F3F6] shadow-[0_24px_80px_rgba(15,23,42,0.20)]">
                            <div className="flex items-start justify-between gap-4 bg-[#F8F8FA] px-6 py-[22px] min-[1800px]:px-8 min-[1800px]:py-7">
                                <div>
                                    <h2 className="font-syne text-lg font-semibold leading-none text-[#191919] min-[1800px]:text-xl min-[2200px]:text-2xl">
                                        {t("title")}
                                    </h2>
                                    <p className="mt-1 text-sm text-[#808080] min-[1800px]:text-base">{t("subtitle")}</p>
                                </div>

                                <Button
                                    type="button"
                                    onClick={handleSaveAdvanced}
                                    style={{
                                        background:
                                            'linear-gradient(270deg, #D5CAFC 2.4%, #E3D2EB 27.88%, #F4DCD3 69.23%, #FDE4C2 100%)',
                                    }}
                                    className="rounded-full px-[28px] py-[10px] font-syne text-xs font-semibold text-[#1E1D2B] shadow-none hover:opacity-95 min-[1800px]:px-8 min-[1800px]:py-3 min-[1800px]:text-sm"
                                >
                                    {t("save")}
                                </Button>
                            </div>

                            <AdvancedSettingsFields
                                values={advancedDraft}
                                onChange={(key, value) =>
                                    setAdvancedDraft((prev) => ({ ...prev, [key]: value }))
                                }
                                idPrefix="dialog"
                                autoFocusInstructions
                            />
                        </div>
                    </div>
                </div>
            )}
        </>
    );
};

export default AdvanceSettings;
