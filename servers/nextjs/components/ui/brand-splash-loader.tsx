"use client";

import { useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import { cn } from "@/lib/utils";

interface BrandSplashLoaderProps {
  message?: string;
  className?: string;
}

/** How long the splash stays at least (the switch-on animation takes ~2.6 s). */
export const BRAND_SPLASH_MIN_DURATION_MS = 3000;

const SPLASH_ANIMATION_MS = 2700;
const NAME = [
  { text: "Kvant ", accent: false },
  { text: "AI Studio", accent: true },
];

// One splash per page load: a later loader (route change, sign-in) continues
// the animation from where the first one was instead of starting over.
let splashSessionStartedAt: number | null = null;

function startedAgoMs(): number {
  if (splashSessionStartedAt === null) {
    splashSessionStartedAt = Date.now();
  }
  return Math.min(Date.now() - splashSessionStartedAt, SPLASH_ANIMATION_MS);
}

/**
 * Kvant AI Studio splash: a grey toggle switches on (the knob slides right,
 * the pill fills green, a ring pulses), then the name appears next to it.
 * Keyframes live in app/globals.css (brand-splash-*).
 */
export function BrandSplashLoader({ message = "Preparing your workspace", className }: BrandSplashLoaderProps) {
  const nameRef = useRef<HTMLSpanElement>(null);
  const [offsetMs, setOffsetMs] = useState(0);
  const [shift, setShift] = useState<number | null>(null);

  useLayoutEffect(() => {
    setOffsetMs(-startedAgoMs());
    const measure = () => {
      const width = nameRef.current?.getBoundingClientRect().width ?? 0;
      setShift((width + 22) / 2); // the mark starts centred, then moves left
    };
    measure();
    void document.fonts?.ready.then(measure);
  }, []);

  let index = 0;
  return (
    <main
      aria-busy="true"
      aria-label={message}
      role="status"
      className={cn("brand-splash", className)}
      style={{ "--t0": `${offsetMs}ms`, "--shift": `${shift ?? 0}px` } as CSSProperties}
    >
      <div className="brand-splash-row" aria-hidden="true" style={{ visibility: shift === null ? "hidden" : "visible" }}>
        <svg className="brand-splash-mark" viewBox="0 0 448 264" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <filter id="brand-splash-knob-shadow" x="-30%" y="-30%" width="160%" height="160%">
              <feDropShadow dx="0" dy="6" stdDeviation="8" floodColor="#101323" floodOpacity=".18" />
            </filter>
          </defs>
          <rect width="448" height="264" rx="132" fill="#E4E7EC" />
          <rect className="brand-splash-fill" width="448" height="264" rx="132" fill="#05C218" />
          <circle className="brand-splash-ring" cx="304" cy="132" r="92" fill="none" stroke="#05C218" strokeWidth="14" />
          <circle className="brand-splash-knob" cx="132" cy="132" r="92" fill="#FFFFFF" filter="url(#brand-splash-knob-shadow)" />
        </svg>
        <span ref={nameRef} className="brand-splash-name">
          {NAME.map((part) => (
            <span key={part.text} className={part.accent ? "brand-splash-accent" : undefined}>
              {[...part.text].map((char) => (
                <span key={index} className="brand-splash-letter" style={{ "--i": index++ } as CSSProperties}>
                  {char}
                </span>
              ))}
            </span>
          ))}
        </span>
      </div>
      <p className="brand-splash-status">{message}</p>
    </main>
  );
}
