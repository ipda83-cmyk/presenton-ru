"use client";

import React, { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { resolveBackendAssetUrl } from "@/utils/api";
import type { StudioModel } from "../../../services/api/studio";

export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;

/** <img>/<canvas> source for a Studio image: data URLs as is, app_data paths via the backend. */
export function imageSrc(image: string): string {
  return image.startsWith("data:") ? image : resolveBackendAssetUrl(image);
}

export function readImageFile(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

export function useElapsedSeconds(active: boolean): number {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!active) return;
    setSeconds(0);
    const started = Date.now();
    const timer = window.setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, [active]);
  return seconds;
}

export function FormCard({
  title,
  subtitle,
  children,
  label,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  label?: string;
}) {
  return (
    <section
      aria-label={label ?? title}
      className="flex w-full flex-col overflow-hidden rounded-[20px] border border-[#E7E9F2] bg-[#F3F3F6] lg:sticky lg:top-[125px] lg:max-w-[400px]"
    >
      <div className="bg-[#F8F8FA] px-[22px] py-[18px]">
        <h2 className="font-syne text-base font-semibold text-[#191919]">{title}</h2>
        <p className="mt-1 text-xs text-[#808080]">{subtitle}</p>
      </div>
      {children}
    </section>
  );
}

export function PromptField({
  id,
  label,
  value,
  onChange,
  placeholder,
  rows = 4,
  optional,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  rows?: number;
  optional?: string;
}) {
  return (
    <div className="bg-[#ECE8F6] px-[22px] py-[18px]">
      <label htmlFor={id} className="block font-syne text-[13px] font-semibold text-[#1F1D2A]">
        {label}
        {optional && <span className="ml-1 font-normal text-[#667085]">{optional}</span>}
      </label>
      <textarea
        id={id}
        rows={rows}
        maxLength={4000}
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        className="mt-2 w-full resize-y border-0 bg-transparent text-sm leading-[1.4] text-[#242430] outline-none placeholder:text-[#8A8798]"
      />
    </div>
  );
}

export function FieldLabel({ children, htmlFor }: { children: React.ReactNode; htmlFor?: string }) {
  const className = "font-syne text-[13px] font-semibold text-[#1F1D2A]";
  return htmlFor ? (
    <label htmlFor={htmlFor} className={className}>
      {children}
    </label>
  ) : (
    <span className={className}>{children}</span>
  );
}

export function ChipGroup<T extends string | number>({
  label,
  options,
  value,
  onChange,
  format,
}: {
  label: string;
  options: readonly T[];
  value: T;
  onChange: (value: T) => void;
  format?: (value: T) => string;
}) {
  return (
    <div className="flex flex-col gap-2">
      <FieldLabel>{label}</FieldLabel>
      <div role="group" aria-label={label} className="flex flex-wrap gap-2">
        {options.map((option) => {
          const active = option === value;
          return (
            <button
              key={String(option)}
              type="button"
              aria-pressed={active}
              onClick={() => onChange(option)}
              className={[
                "min-h-9 rounded-full border px-3.5 font-syne text-[13px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7A5AF8]",
                active
                  ? "border-[#CEC6FF] bg-[#F4F3FF] font-semibold text-[#5141E5]"
                  : "border-[#DBDBE1] bg-white font-medium text-[#2C2B37] hover:border-[#CEC6FF]",
              ].join(" ")}
            >
              {format ? format(option) : String(option)}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function ModelSelect({
  id,
  models,
  value,
  onChange,
}: {
  id: string;
  models: StudioModel[];
  value: string;
  onChange: (key: string) => void;
}) {
  const t = useTranslations("studio");
  const current = models.find((model) => model.key === value);
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between gap-3">
        <FieldLabel htmlFor={id}>{t("fields.model")}</FieldLabel>
        <select
          id={id}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="min-h-10 min-w-[190px] rounded-xl border border-[#DBDBE1] bg-white px-3 font-syne text-[13px] font-medium text-[#2C2B37] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7A5AF8]"
        >
          {models.map((model) => (
            <option key={model.key} value={model.key}>
              {model.title}
            </option>
          ))}
        </select>
      </div>
      {current?.tags[0] && t.has(`models.${current.tags[0]}`) && (
        <p className="text-right text-[11px] leading-4 text-[#667085]">{t(`models.${current.tags[0]}`)}</p>
      )}
    </div>
  );
}

export function GradientButton({
  children,
  busy,
  disabled,
  onClick,
}: {
  children: React.ReactNode;
  busy?: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className="inline-flex min-h-[46px] w-full items-center justify-center gap-2 rounded-[48px] font-syne text-sm font-semibold text-[#1E1D2B] transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7A5AF8] focus-visible:ring-offset-2"
      style={{ background: "linear-gradient(270deg, #D5CAFC 2.4%, #E3D2EB 27.88%, #F4DCD3 69.23%, #FDE4C2 100%)" }}
    >
      {busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
      {children}
    </button>
  );
}

export function SoftButton({
  children,
  onClick,
  disabled,
  busy,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  busy?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className="inline-flex min-h-[42px] items-center justify-center gap-1.5 rounded-xl border border-[#DBDBE1] bg-white px-3 font-syne text-[13px] font-medium text-[#2C2B37] transition-colors hover:border-[#CEC6FF] hover:bg-[#FAFAFF] disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7A5AF8]"
    >
      {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />}
      {children}
    </button>
  );
}

export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <p role="alert" className="rounded-xl border border-red-200 bg-red-50 px-3 py-2.5 text-sm leading-5 text-red-700">
      {error}
    </p>
  );
}

export function BusyOverlay({ active, label }: { active: boolean; label: string }) {
  const t = useTranslations("studio");
  const seconds = useElapsedSeconds(active);
  if (!active) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 rounded-2xl bg-white/75 backdrop-blur-[2px]"
    >
      <Loader2 className="h-8 w-8 animate-spin text-[#7A5AF8]" aria-hidden="true" />
      <p className="font-syne text-sm font-medium text-[#101323]">{label}</p>
      <p className="text-xs text-[#667085]">{t("busy.elapsed", { seconds })}</p>
    </div>
  );
}

export function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}
