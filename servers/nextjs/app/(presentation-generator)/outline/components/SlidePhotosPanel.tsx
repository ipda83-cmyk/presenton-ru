"use client";

import { Images, Loader2, RefreshCw } from "lucide-react";
import { useTranslations } from "next-intl";
import { resolveBackendAssetUrl } from "@/utils/api";
import type { SlidePhoto } from "../../services/api/slide-photos";
import type { SlidePhotosState } from "../hooks/useSlidePhotos";

/** Drag-and-drop payload type for moving a photo onto a slide card. */
export const SLIDE_PHOTO_DRAG_TYPE = "application/x-presenton-slide-photo";

export function startPhotoDrag(event: React.DragEvent, photo: SlidePhoto) {
  event.dataTransfer.setData(SLIDE_PHOTO_DRAG_TYPE, photo.url);
  event.dataTransfer.effectAllowed = "move";
}

/** First line of a slide outline, without Markdown marks, for the slide picker. */
export function slideTitle(content: string): string {
  const line = (content || "")
    .split("\n")
    .map((value) => value.replace(/^[#>\-*\s]+|[*_`]/g, "").trim())
    .find(Boolean);
  if (!line) return "";
  return line.length > 48 ? `${line.slice(0, 47)}…` : line;
}

export default function SlidePhotosPanel({
  state,
  outlines,
  disabled,
}: {
  state: SlidePhotosState;
  outlines: { content: string }[];
  disabled: boolean;
}) {
  const t = useTranslations("slidePhotos");
  const { photos, matched, status, error } = state;
  if (!photos.length) return null;

  const placed = photos.filter((photo) => photo.slide !== null).length;
  const busy = status === "matching" || disabled;
  const note =
    status === "matching"
      ? t("matching")
      : status === "error"
        ? error || t("errors.requestFailed")
        : matched
          ? t(`matched.${matched}`)
          : t("waiting");

  return (
    <section
      aria-labelledby="slide-photos-title"
      aria-busy={status === "matching" || undefined}
      className="mt-8 rounded-[12px] bg-white px-5 py-6 font-syne shadow-[0_6.6px_6.6px_rgba(0,0,0,0.10)] sm:px-[30px]"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id="slide-photos-title" className="flex items-center gap-2 text-base font-medium text-[#191919]">
            <Images className="h-4 w-4 text-[#7A5AF8]" aria-hidden="true" />
            {t("title")}
            <span className="text-sm font-normal text-[#98A2B3]">{t("placed", { placed, total: photos.length })}</span>
          </h2>
          <p
            role={status === "error" ? "alert" : "status"}
            className={`mt-1.5 flex items-center gap-1.5 text-xs leading-5 ${status === "error" ? "text-red-700" : "text-[#667085]"}`}
          >
            {status === "matching" && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />}
            {note}
          </p>
        </div>
        <button
          type="button"
          onClick={() => void state.rematch()}
          disabled={busy || outlines.length === 0}
          className="inline-flex min-h-9 items-center gap-1.5 rounded-full border border-[#EDEEEF] bg-white px-3.5 text-[13px] font-medium text-[#5141E5] transition-colors hover:bg-[#F4F3FF] disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7A5AF8]"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          {t("rematch")}
        </button>
      </div>

      <ul className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        {photos.map((photo, index) => {
          const selectId = `slide-photo-${index}`;
          return (
            <li key={photo.url} className="flex min-w-0 flex-col gap-2">
              <div
                draggable={!busy}
                onDragStart={(event) => startPhotoDrag(event, photo)}
                title={t("dragHint")}
                className={`overflow-hidden rounded-[10px] border border-[#EDEEEF] bg-[#F6F6F9] ${busy ? "" : "cursor-grab active:cursor-grabbing"}`}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={resolveBackendAssetUrl(photo.url)}
                  alt={photo.name || t("photoAlt", { number: index + 1 })}
                  className={`aspect-[4/3] w-full object-cover ${photo.slide === null ? "opacity-50" : ""}`}
                  draggable={false}
                />
              </div>
              <label htmlFor={selectId} className="sr-only">
                {t("slideFor", { name: photo.name || index + 1 })}
              </label>
              <select
                id={selectId}
                value={photo.slide === null ? "" : String(photo.slide)}
                disabled={busy}
                onChange={(event) =>
                  state.assign(photo.url, event.target.value === "" ? null : Number(event.target.value))
                }
                className="min-h-9 w-full min-w-0 truncate rounded-lg border border-[#DBDBE1] bg-white px-2 text-xs text-[#2C2B37] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7A5AF8] disabled:opacity-60"
              >
                <option value="">{t("unused")}</option>
                {outlines.map((outline, slide) => {
                  const title = slideTitle(outline.content);
                  return (
                    <option key={slide} value={slide}>
                      {title ? t("slideOption", { number: slide + 1, title }) : t("slideNumber", { number: slide + 1 })}
                    </option>
                  );
                })}
              </select>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
