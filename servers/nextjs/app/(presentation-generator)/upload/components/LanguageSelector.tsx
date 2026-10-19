import { Button } from '@/components/ui/button';
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';

import { Check, ChevronDown } from 'lucide-react';
import React, { useState } from 'react'
import { LanguageType, isAutoLanguage } from '../type';
import { cn } from '@/lib/utils';
import { useTranslations } from 'next-intl';


export const LanguageSelector: React.FC<{
    value: string | null;
    onValueChange: (value: string) => void;

}> = ({ value, onValueChange }) => {
    const t = useTranslations("upload.languagePicker");
    const [openLanguage, setOpenLanguage] = useState(false);
    return (
        <Popover open={openLanguage} onOpenChange={setOpenLanguage}>
            <PopoverTrigger asChild>
                <Button
                    variant="outline"
                    role="combobox"
                    name="language"
                    data-testid="language-select"
                    aria-expanded={openLanguage}
                    className="px-3.5 py-1 justify-between rounded-[48px] font-manrope font-semibold overflow-hidden bg-[#F7F6F9] border-[#EDEEEF] focus-visible:ring-[#02940F] border-none"
                >
                    <p className="text-sm font-medium truncate">
                        {isAutoLanguage(value) ? t("auto") : value || t("placeholder")}
                    </p>
                    <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                </Button>
            </PopoverTrigger>
            <PopoverContent className="w-[300px] p-0" align="end">
                <Command>
                    <CommandInput
                        placeholder={t("search")}
                        className="font-manrope"
                    />
                    <CommandList>
                        <CommandEmpty>{t("empty")}</CommandEmpty>
                        <CommandGroup>
                            {Object.values(LanguageType).map((language) => (
                                <CommandItem
                                    key={language}
                                    value={language}
                                    role="option"
                                    onSelect={(currentValue) => {
                                        onValueChange(currentValue);
                                        setOpenLanguage(false);
                                    }}
                                    className="font-manrope"
                                >
                                    <Check
                                        className={cn(
                                            "mr-2 h-4 w-4",
                                            value === language ? "opacity-100" : "opacity-0"
                                        )}
                                    />
                                    {language === LanguageType.Auto ? t("auto") : language}
                                </CommandItem>
                            ))}
                        </CommandGroup>
                    </CommandList>
                </Command>
            </PopoverContent>
        </Popover>
    );
}