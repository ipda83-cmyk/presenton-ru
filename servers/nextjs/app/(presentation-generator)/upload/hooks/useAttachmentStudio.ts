import { useCallback, useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { resolveBackendAssetUrl } from "@/utils/api";
import { useStudioAvailable, type StudioPanelItem } from "@/components/studio/StudioPanel";
import { isSlidePhotoFile } from "../../services/api/slide-photos";

/** "office-before.jpg" -> "office-before-studio.png" (once, however often edited). */
export function studioFileName(name: string, type: string): string {
  const base = (name.replace(/\.[^./\\]+$/, "") || "photo").replace(/-studio$/, "");
  const extension = type === "image/jpeg" ? "jpg" : type === "image/webp" ? "webp" : "png";
  return `${base}-studio.${extension}`;
}

/**
 * Attached photos on the create page, editable in AI Image Studio before the
 * presentation is made: previews, the Studio panel, and swapping a photo for
 * its edited version ("Add to presentation").
 */
export function useAttachmentStudio(files: File[], setFiles: Dispatch<SetStateAction<File[]>>) {
  const ids = useRef(new WeakMap<File, string>());
  const nextId = useRef(0);
  const previews = useRef(new Map<File, string>());
  const [previewVersion, setPreviewVersion] = useState(0);
  const [open, setOpen] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);

  const idOf = useCallback((file: File) => {
    let id = ids.current.get(file);
    if (!id) {
      nextId.current += 1;
      id = `photo-${nextId.current}`;
      ids.current.set(file, id);
    }
    return id;
  }, []);

  useEffect(() => {
    const map = previews.current;
    const photos = new Set(files.filter(isSlidePhotoFile));
    let changed = false;
    for (const file of photos) {
      if (!map.has(file)) {
        map.set(file, URL.createObjectURL(file));
        changed = true;
      }
    }
    for (const [file, url] of map) {
      if (!photos.has(file)) {
        URL.revokeObjectURL(url);
        map.delete(file);
        changed = true;
      }
    }
    if (changed) setPreviewVersion((value) => value + 1);
  }, [files]);

  useEffect(
    () => () => {
      for (const url of previews.current.values()) URL.revokeObjectURL(url);
      previews.current.clear();
    },
    [],
  );

  const hasPhotos = files.some(isSlidePhotoFile);
  // The button only shows once the Studio has an arckep key.
  const available = useStudioAvailable(hasPhotos);

  const items: StudioPanelItem[] = useMemo(
    () =>
      files.filter(isSlidePhotoFile).flatMap((file) => {
        const src = previews.current.get(file);
        return src ? [{ id: idOf(file), name: file.name, src }] : [];
      }),
    // previewVersion: object URLs are kept in a ref.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [files, idOf, previewVersion],
  );

  // Close when the photos were removed (not while a swapped one gets its preview).
  useEffect(() => {
    if (open && !hasPhotos) setOpen(false);
  }, [open, hasPhotos]);

  const openFor = useCallback(
    (file: File) => {
      setActiveId(idOf(file));
      setOpen(true);
    },
    [idOf],
  );

  const replace = useCallback(
    async (item: StudioPanelItem, image: string) => {
      const response = await fetch(resolveBackendAssetUrl(image), { credentials: "include" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const blob = await response.blob();
      const type = blob.type.startsWith("image/") ? blob.type : "image/png";
      const edited = new File([blob], studioFileName(item.name, type), { type });
      ids.current.set(edited, item.id);
      setFiles((current) => current.map((file) => (idOf(file) === item.id ? edited : file)));
    },
    [idOf, setFiles],
  );

  const close = useCallback(() => setOpen(false), []);

  return {
    previewOf: (file: File) => (isSlidePhotoFile(file) ? previews.current.get(file) : undefined),
    studioAvailable: available,
    openFor,
    panel: {
      open,
      items,
      activeId,
      onActiveChange: setActiveId,
      onClose: close,
      onAdd: replace,
    },
  };
}
