"use client";

import { forwardRef, memo, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";

export interface MaskCanvasHandle {
  /** PNG data URL at the image's natural size: transparent = area to change. */
  exportMask: () => string | null;
  clearMask: () => void;
  isMaskEmpty: () => boolean;
}

export type BrushTool = "brush" | "eraser";

const OVERLAY_COLOR = "#7C5CF6";
const OVERLAY_ALPHA = 0.55;
const MAX_DISPLAY_WIDTH = 1400;

interface Props {
  src: string;
  /** Brush diameter in display pixels. */
  brushSize: number;
  showMask: boolean;
  tool: BrushTool;
  label: string;
  onStrokeEnd?: () => void;
  onReady?: (size: { width: number; height: number }) => void;
  onError?: () => void;
}

/**
 * The image with a paintable mask on top (ported from AI Image Studio).
 * Strokes are interpolated between pointer events so fast moves stay solid.
 * The mask lives at the image's natural size; a display-size overlay mirrors
 * it so redrawing never scans pixels.
 */
const MaskCanvasInner = forwardRef<MaskCanvasHandle, Props>(function MaskCanvas(
  { src, brushSize, showMask, tool, label, onStrokeEnd, onReady, onError },
  ref,
) {
  const displayRef = useRef<HTMLCanvasElement>(null);
  const ringRef = useRef<HTMLSpanElement>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const maskRef = useRef<HTMLCanvasElement | null>(null);
  const overlayRef = useRef<HTMLCanvasElement | null>(null);
  const drawing = useRef(false);
  const dirty = useRef(false);
  const lastPoint = useRef<{ x: number; y: number } | null>(null);
  const [dims, setDims] = useState({ w: 0, h: 0, natW: 0, natH: 0 });

  const redraw = useCallback(() => {
    const canvas = displayRef.current;
    const image = imageRef.current;
    if (!canvas || !image || !canvas.width) return;
    const context = canvas.getContext("2d")!;
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    if (showMask && overlayRef.current && dirty.current) {
      context.globalAlpha = OVERLAY_ALPHA;
      context.drawImage(overlayRef.current, 0, 0);
      context.globalAlpha = 1;
    }
  }, [showMask]);

  useEffect(() => {
    let cancelled = false;
    const image = new Image();
    image.crossOrigin = "anonymous";
    image.onload = () => {
      if (cancelled) return;
      imageRef.current = image;
      const scale = Math.min(1, MAX_DISPLAY_WIDTH / image.naturalWidth);
      const w = Math.max(1, Math.round(image.naturalWidth * scale));
      const h = Math.max(1, Math.round(image.naturalHeight * scale));

      const mask = document.createElement("canvas");
      mask.width = image.naturalWidth;
      mask.height = image.naturalHeight;
      const maskContext = mask.getContext("2d")!;
      maskContext.fillStyle = "#000";
      maskContext.fillRect(0, 0, mask.width, mask.height);
      maskRef.current = mask;

      const overlay = document.createElement("canvas");
      overlay.width = w;
      overlay.height = h;
      overlayRef.current = overlay;
      dirty.current = false;

      setDims({ w, h, natW: image.naturalWidth, natH: image.naturalHeight });
      onReady?.({ width: image.naturalWidth, height: image.naturalHeight });
    };
    image.onerror = () => {
      if (!cancelled) onError?.();
    };
    image.src = src;
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src]);

  useEffect(() => {
    redraw();
  }, [dims, redraw]);

  function stamp(x: number, y: number, prev: { x: number; y: number } | null) {
    const mask = maskRef.current;
    const overlay = overlayRef.current;
    if (!mask || !overlay || !dims.w) return;
    const toNatural = dims.natW / dims.w;
    const radius = brushSize / 2;
    const maskContext = mask.getContext("2d")!;
    const overlayContext = overlay.getContext("2d")!;
    const erase = tool === "eraser";
    maskContext.fillStyle = erase ? "#000" : "#fff";
    overlayContext.globalCompositeOperation = erase ? "destination-out" : "source-over";
    overlayContext.fillStyle = OVERLAY_COLOR;

    const dot = (px: number, py: number) => {
      maskContext.beginPath();
      maskContext.arc(px * toNatural, py * toNatural, radius * toNatural, 0, Math.PI * 2);
      maskContext.fill();
      overlayContext.beginPath();
      overlayContext.arc(px, py, radius, 0, Math.PI * 2);
      overlayContext.fill();
    };

    if (prev) {
      const distance = Math.hypot(x - prev.x, y - prev.y);
      const steps = Math.ceil(distance / Math.max(radius * 0.35, 1));
      for (let i = 1; i <= steps; i++) {
        const t = i / steps;
        dot(prev.x + (x - prev.x) * t, prev.y + (y - prev.y) * t);
      }
    } else {
      dot(x, y);
    }
    overlayContext.globalCompositeOperation = "source-over";
    if (!erase) dirty.current = true;
    redraw();
  }

  function toDisplay(event: React.PointerEvent) {
    const rect = displayRef.current!.getBoundingClientRect();
    return {
      x: ((event.clientX - rect.left) / rect.width) * dims.w,
      y: ((event.clientY - rect.top) / rect.height) * dims.h,
    };
  }

  function moveRing(event: React.PointerEvent) {
    const ring = ringRef.current;
    const canvas = displayRef.current;
    if (!ring || !canvas || !dims.w) return;
    const rect = canvas.getBoundingClientRect();
    const size = brushSize * (rect.width / dims.w);
    ring.style.width = `${size}px`;
    ring.style.height = `${size}px`;
    ring.style.transform = `translate(${event.clientX - rect.left - size / 2}px, ${event.clientY - rect.top - size / 2}px)`;
    ring.style.opacity = "1";
  }

  function endStroke() {
    if (!drawing.current) return;
    drawing.current = false;
    lastPoint.current = null;
    onStrokeEnd?.();
  }

  const clear = useCallback(() => {
    const mask = maskRef.current;
    const overlay = overlayRef.current;
    if (mask) {
      const context = mask.getContext("2d")!;
      context.fillStyle = "#000";
      context.fillRect(0, 0, mask.width, mask.height);
    }
    overlay?.getContext("2d")!.clearRect(0, 0, overlay.width, overlay.height);
    dirty.current = false;
    redraw();
  }, [redraw]);

  useImperativeHandle(ref, () => ({
    exportMask: () => {
      const mask = maskRef.current;
      if (!mask || !dirty.current) return null;
      const context = mask.getContext("2d")!;
      const data = context.getImageData(0, 0, mask.width, mask.height);
      const pixels = data.data;
      let painted = false;
      for (let i = 0; i < pixels.length; i += 4) {
        if (pixels[i] > 128) {
          pixels[i + 3] = 0;
          painted = true;
        } else {
          pixels[i] = 0;
          pixels[i + 1] = 0;
          pixels[i + 2] = 0;
          pixels[i + 3] = 255;
        }
      }
      if (!painted) return null; // everything was erased again
      const out = document.createElement("canvas");
      out.width = mask.width;
      out.height = mask.height;
      out.getContext("2d")!.putImageData(data, 0, 0);
      return out.toDataURL("image/png");
    },
    clearMask: clear,
    isMaskEmpty: () => !dirty.current,
  }));

  return (
    <div className="relative inline-block max-w-full overflow-hidden rounded-xl">
      <canvas
        ref={displayRef}
        width={dims.w}
        height={dims.h}
        role="img"
        aria-label={label}
        className="block h-auto max-h-[70vh] max-w-full cursor-none touch-none select-none"
        onPointerDown={(event) => {
          if (event.button !== 0) return;
          drawing.current = true;
          lastPoint.current = null;
          event.currentTarget.setPointerCapture(event.pointerId);
          const point = toDisplay(event);
          stamp(point.x, point.y, null);
          lastPoint.current = point;
        }}
        onPointerMove={(event) => {
          moveRing(event);
          if (!drawing.current) return;
          const point = toDisplay(event);
          stamp(point.x, point.y, lastPoint.current);
          lastPoint.current = point;
        }}
        onPointerUp={endStroke}
        onPointerCancel={endStroke}
        onPointerLeave={(event) => {
          if (ringRef.current) ringRef.current.style.opacity = "0";
          if (!event.currentTarget.hasPointerCapture(event.pointerId)) endStroke();
        }}
      />
      <span
        ref={ringRef}
        aria-hidden="true"
        className="pointer-events-none absolute left-0 top-0 rounded-full border-2 border-white opacity-0 shadow-[0_0_0_1px_rgba(16,19,35,0.55)]"
      />
    </div>
  );
});

// memo: typing a prompt in the parent must not repaint the canvas.
export const MaskCanvas = memo(MaskCanvasInner);
