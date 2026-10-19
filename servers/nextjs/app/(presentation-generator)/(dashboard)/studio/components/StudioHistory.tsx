"use client";

import { useState } from "react";
import { Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import type { StudioImage } from "../../../services/api/studio";
import { imageSrc } from "@/components/studio/controls";

const COLLAPSED_COUNT = 10;

// The user's Studio images, newest first. Picking one hands it to the page.
export default function StudioHistory({
  items,
  loading,
  selectedUrl,
  onPick,
  onRemove,
}: {
  items: StudioImage[];
  loading: boolean;
  selectedUrl?: string | null;
  onPick: (image: StudioImage) => void;
  onRemove: (image: StudioImage) => Promise<void>;
}) {
  const t = useTranslations("studio.history");
  const [expanded, setExpanded] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const visible = expanded ? items : items.slice(0, COLLAPSED_COUNT);

  async function remove(image: StudioImage) {
    if (!window.confirm(t("confirmDelete"))) return;
    setRemoving(image.id);
    setError(null);
    try {
      await onRemove(image);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("deleteFailed"));
    } finally {
      setRemoving(null);
    }
  }

  return (
    <section aria-labelledby="studio-history-title" className="flex flex-col gap-2.5">
      <div className="flex items-center justify-between gap-3">
        <h2 id="studio-history-title" className="font-syne text-[15px] font-medium text-[#191919]">
          {t("title")}
          {items.length > 0 && <span className="ml-1.5 text-[#98A2B3]">{items.length}</span>}
        </h2>
        {items.length > COLLAPSED_COUNT && (
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            className="font-syne text-[13px] font-semibold text-[#02940F] hover:text-[#027A0E]"
          >
            {expanded ? t("collapse") : t("showAll", { count: items.length })}
          </button>
        )}
      </div>
      {error && (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      )}
      {loading ? (
        <p className="text-sm text-[#667085]">{t("loading")}</p>
      ) : items.length === 0 ? (
        <p className="rounded-xl border border-dashed border-[#DBDBE1] px-4 py-5 text-center text-sm text-[#667085]">
          {t("empty")}
        </p>
      ) : (
        <ul className="grid grid-cols-3 gap-3 sm:grid-cols-4 xl:grid-cols-5">
          {visible.map((image) => {
            const selected = image.file_url === selectedUrl;
            const prompt = image.extras.prompt || t(`modes.${image.extras.mode ?? "create"}`);
            return (
              <li key={image.id} className="group relative">
                <button
                  type="button"
                  onClick={() => onPick(image)}
                  aria-pressed={selected}
                  title={prompt}
                  className={[
                    "block aspect-[4/3] w-full overflow-hidden rounded-[10px] border bg-[#F6F6F9] transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#03B015]",
                    selected ? "border-[#03B015] ring-2 ring-[#CDF8D1]" : "border-[#EDEEEF] hover:border-[#CDF8D1]",
                  ].join(" ")}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={imageSrc(image.file_url)} alt={prompt} loading="lazy" className="h-full w-full object-cover" />
                </button>
                <button
                  type="button"
                  onClick={() => remove(image)}
                  disabled={removing === image.id}
                  aria-label={t("delete")}
                  title={t("delete")}
                  className="absolute right-1.5 top-1.5 flex h-7 w-7 items-center justify-center rounded-full bg-white/90 text-[#475467] shadow-sm transition hover:text-red-600 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#03B015] disabled:opacity-60 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100"
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
