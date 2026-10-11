import { getApiUrl } from "@/utils/api";
import { tr } from "@/utils/clientI18n";
import { ApiResponseHandler } from "./api-error-handler";
import { getHeader } from "./header";
import { ImagesApi } from "./images";

// The user's own photos placed on outline slides (servers/fastapi/utils/slide_photos.py).
export type SlidePhotoMatch = "vision" | "order" | "manual";

export interface SlidePhoto {
  url: string;
  name: string;
  /** Outline slide index, or null when the photo is not used. */
  slide: number | null;
}

export interface SlidePhotosRecord {
  photos: SlidePhoto[];
  matched: SlidePhotoMatch | null;
  updated_at?: string;
}

const PHOTO_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);
const PHOTO_EXTENSION = /\.(png|jpe?g|webp)$/i;

/** Attachments that can go on slides as pictures. */
export function isSlidePhotoFile(file: File): boolean {
  return PHOTO_TYPES.has(file.type) || (!file.type && PHOTO_EXTENSION.test(file.name));
}

export function normalizeSlidePhotosRecord(value: unknown): SlidePhotosRecord {
  const record = (value && typeof value === "object" ? value : {}) as Record<string, unknown>;
  const photos = Array.isArray(record.photos)
    ? record.photos.flatMap((item): SlidePhoto[] => {
        if (!item || typeof item !== "object") return [];
        const photo = item as Record<string, unknown>;
        if (typeof photo.url !== "string" || !photo.url) return [];
        const slide = typeof photo.slide === "number" && Number.isInteger(photo.slide) && photo.slide >= 0 ? photo.slide : null;
        return [{ url: photo.url, name: String(photo.name ?? ""), slide }];
      })
    : [];
  const matched = ["vision", "order", "manual"].includes(record.matched as string)
    ? (record.matched as SlidePhotoMatch)
    : null;
  return { photos, matched, updated_at: typeof record.updated_at === "string" ? record.updated_at : undefined };
}

const failed = () => tr("slidePhotos.errors.requestFailed", "Could not update the photos");
const path = (presentationId: string, suffix = "") =>
  getApiUrl(`/api/v1/ppt/outlines/${encodeURIComponent(presentationId)}/photos${suffix}`);

export const SlidePhotosApi = {
  async get(presentationId: string): Promise<SlidePhotosRecord> {
    const response = await fetch(path(presentationId), { credentials: "include", cache: "no-store" });
    return normalizeSlidePhotosRecord(await ApiResponseHandler.handleResponse(response, failed()));
  },

  async save(presentationId: string, photos: SlidePhoto[], matched: SlidePhotoMatch | null): Promise<SlidePhotosRecord> {
    const response = await fetch(path(presentationId), {
      method: "PUT",
      headers: getHeader(),
      credentials: "include",
      body: JSON.stringify({ photos, matched }),
    });
    return normalizeSlidePhotosRecord(await ApiResponseHandler.handleResponse(response, failed()));
  },

  /** Ask the model to place every photo on the slide it fits best. */
  async match(presentationId: string, slides?: { content: string }[]): Promise<SlidePhotosRecord> {
    const response = await fetch(path(presentationId, "/match"), {
      method: "POST",
      headers: getHeader(),
      credentials: "include",
      body: JSON.stringify(slides ? { slides } : {}),
    });
    return normalizeSlidePhotosRecord(await ApiResponseHandler.handleResponse(response, failed()));
  },

  /** Save attached photos to the user's images and link them to the presentation. */
  async attach(presentationId: string, files: File[]): Promise<SlidePhotosRecord | null> {
    const photos: SlidePhoto[] = [];
    for (const file of files) {
      const asset = await ImagesApi.uploadImage(file);
      if (asset?.file_url) photos.push({ url: asset.file_url, name: file.name, slide: null });
    }
    if (!photos.length) return null;
    return SlidePhotosApi.save(presentationId, photos, null);
  },
};

/**
 * Keep photos with their slides when the outline changes: `order[newIndex]`
 * is the old index of the slide now at newIndex (null for a new slide).
 */
export function remapSlidePhotos(photos: SlidePhoto[], order: (number | null)[]): SlidePhoto[] {
  const newIndexOf = new Map<number, number>();
  order.forEach((oldIndex, newIndex) => {
    if (oldIndex !== null) newIndexOf.set(oldIndex, newIndex);
  });
  return photos.map((photo) => ({
    ...photo,
    slide: photo.slide === null ? null : newIndexOf.get(photo.slide) ?? null,
  }));
}
