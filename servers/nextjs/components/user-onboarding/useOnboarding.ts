"use client";

import { useEffect, useSyncExternalStore } from "react";
import {
  OnboardingApi,
  type Onboarding,
  type OnboardingEvent,
} from "@/app/(presentation-generator)/services/api/onboarding";

// One copy for the whole app: the dashboard, the editor and the Studio all
// read it, a mark from any of them updates every one.
let current: Onboarding | null = null;
let loading: Promise<void> | null = null;
const listeners = new Set<() => void>();

function publish(value: Onboarding | null) {
  current = value;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function refreshOnboarding(): Promise<void> {
  loading ??= OnboardingApi.read()
    .then(publish)
    .catch(() => undefined) // no onboarding is better than a broken page
    .finally(() => {
      loading = null;
    });
  return loading;
}

export async function markOnboarding(event: OnboardingEvent): Promise<void> {
  try {
    publish(await OnboardingApi.mark(event));
  } catch {
    // A lost mark only means a hint shows once more.
  }
}

let editedSent = false;

/** The editor saved a change made by the user: the checklist item is done. */
export function markSlideEdited() {
  if (editedSent) return;
  const item = current?.checklist.find((entry) => entry.id === "edited");
  if (item?.done) return;
  editedSent = true;
  void markOnboarding("edited");
}

/** The onboarding state; `fresh` asks the server again (the checklist changes). */
export function useOnboarding({ fresh = false }: { fresh?: boolean } = {}) {
  const value = useSyncExternalStore(subscribe, () => current, () => null);
  useEffect(() => {
    if (fresh || !current) void refreshOnboarding();
  }, [fresh]);
  return value;
}
