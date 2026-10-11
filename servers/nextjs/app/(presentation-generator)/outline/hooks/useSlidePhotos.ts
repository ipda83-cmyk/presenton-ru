import { useCallback, useEffect, useRef, useState } from "react";
import { arrayMove } from "@dnd-kit/sortable";
import { store } from "@/store/store";
import {
  SlidePhotosApi,
  remapSlidePhotos,
  type SlidePhoto,
  type SlidePhotoMatch,
} from "../../services/api/slide-photos";

export type SlidePhotosStatus = "idle" | "loading" | "matching" | "saving" | "error";

export type SlidePhotosState = {
  photos: SlidePhoto[];
  matched: SlidePhotoMatch | null;
  status: SlidePhotosStatus;
  error: string | null;
  /** Put a photo on a slide (null: do not use it). */
  assign: (url: string, slide: number | null) => void;
  /** Keep photos with their slides when the outline is reordered. */
  moveSlide: (oldIndex: number, newIndex: number) => void;
  rematch: () => Promise<void>;
  /** Wait for pending saves (before preparing the presentation). */
  flush: () => Promise<void>;
};

const currentOutlines = () => store.getState().presentationGeneration.outlines ?? [];

/**
 * The user's photos for the outline page: loaded with the presentation, placed
 * by meaning once the outline is ready, then moved by the user.
 */
export function useSlidePhotos(presentationId: string | null, outlineReady: boolean): SlidePhotosState {
  const [photos, setPhotos] = useState<SlidePhoto[]>([]);
  const [matched, setMatched] = useState<SlidePhotoMatch | null>(null);
  const [status, setStatus] = useState<SlidePhotosStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [loadedFor, setLoadedFor] = useState<string | null>(null);
  const pending = useRef<Promise<unknown>>(Promise.resolve());
  const autoMatched = useRef<string | null>(null);

  useEffect(() => {
    setPhotos([]);
    setMatched(null);
    setError(null);
    setLoadedFor(null);
    if (!presentationId) return;
    let alive = true;
    setStatus("loading");
    SlidePhotosApi.get(presentationId)
      .then((record) => {
        if (!alive) return;
        setPhotos(record.photos);
        setMatched(record.matched);
        setLoadedFor(presentationId);
        setStatus("idle");
      })
      .catch(() => {
        if (!alive) return;
        setLoadedFor(presentationId);
        setStatus("idle");
      });
    return () => {
      alive = false;
    };
  }, [presentationId]);

  const runMatch = useCallback(async () => {
    if (!presentationId) return;
    setStatus("matching");
    setError(null);
    try {
      const slides = currentOutlines().map((outline) => ({ content: outline.content }));
      const record = await SlidePhotosApi.match(presentationId, slides);
      setPhotos(record.photos);
      setMatched(record.matched);
      setStatus("idle");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : null);
      setStatus("error");
    }
  }, [presentationId]);

  // A fresh outline (new or regenerated presentation): place the photos by meaning.
  useEffect(() => {
    if (!presentationId || loadedFor !== presentationId || !outlineReady) return;
    if (!photos.length || matched !== null || autoMatched.current === presentationId) return;
    autoMatched.current = presentationId;
    void runMatch();
  }, [presentationId, loadedFor, outlineReady, photos.length, matched, runMatch]);

  const persist = useCallback(
    (next: SlidePhoto[], nextMatched: SlidePhotoMatch | null) => {
      if (!presentationId) return;
      setPhotos(next);
      setMatched(nextMatched);
      setStatus("saving");
      const save = pending.current
        .catch(() => undefined)
        .then(() => SlidePhotosApi.save(presentationId, next, nextMatched))
        .then(() => {
          setStatus("idle");
          setError(null);
        })
        .catch((reason: unknown) => {
          setError(reason instanceof Error ? reason.message : null);
          setStatus("error");
        });
      pending.current = save;
    },
    [presentationId],
  );

  const assign = useCallback(
    (url: string, slide: number | null) => {
      persist(
        photos.map((photo) => (photo.url === url ? { ...photo, slide } : photo)),
        "manual",
      );
    },
    [persist, photos],
  );

  const moveSlide = useCallback(
    (oldIndex: number, newIndex: number) => {
      if (oldIndex === newIndex || !photos.some((photo) => photo.slide !== null)) return;
      const count = Math.max(currentOutlines().length, oldIndex + 1, newIndex + 1);
      const order = arrayMove(
        Array.from({ length: count }, (_, index) => index),
        oldIndex,
        newIndex,
      );
      persist(remapSlidePhotos(photos, order), matched);
    },
    [matched, persist, photos],
  );

  const flush = useCallback(async () => {
    await pending.current.catch(() => undefined);
  }, []);

  return { photos, matched, status, error, assign, moveSlide, rematch: runMatch, flush };
}
