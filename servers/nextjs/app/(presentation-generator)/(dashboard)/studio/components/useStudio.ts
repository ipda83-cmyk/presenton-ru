"use client";

import { useCallback, useEffect, useState } from "react";
import { StudioApi, type StudioConfig, type StudioImage } from "../../../services/api/studio";

export type StudioState = {
  config: StudioConfig | null;
  configError: string | null;
  history: StudioImage[];
  historyLoading: boolean;
  addImages: (images: StudioImage[]) => void;
  removeImage: (id: string) => Promise<void>;
};

/** Studio settings and the user's image history, shared by the Studio pages. */
export function useStudio(): StudioState {
  const [config, setConfig] = useState<StudioConfig | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [history, setHistory] = useState<StudioImage[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    StudioApi.config()
      .then((value) => alive && setConfig(value))
      .catch((error: Error) => alive && setConfigError(error.message));
    StudioApi.history()
      .then((items) => alive && setHistory(items))
      .catch(() => alive && setHistory([]))
      .finally(() => alive && setHistoryLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  const addImages = useCallback((images: StudioImage[]) => {
    setHistory((current) => [...images, ...current.filter((item) => !images.some((image) => image.id === item.id))]);
  }, []);

  const removeImage = useCallback(async (id: string) => {
    await StudioApi.remove(id);
    setHistory((current) => current.filter((item) => item.id !== id));
  }, []);

  return { config, configError, history, historyLoading, addImages, removeImage };
}
