import { cn } from "@/lib/utils";

/** Product name; the logo below is its mark (a switched-on toggle, KVANTOR brand). */
export const BRAND_NAME = "Kvant AI Studio";
export const BRAND_GREEN = "#05C218";

/** The toggle mark: a green pill with the white knob on the right (448×264). */
export function BrandMark({
  height = 24,
  onDark = false,
  className,
  title,
}: {
  height?: number;
  onDark?: boolean;
  className?: string;
  title?: string;
}) {
  return (
    <svg
      viewBox="0 0 448 264"
      height={height}
      width={(height * 448) / 264}
      className={cn("shrink-0", className)}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect width="448" height="264" rx="132" fill={onDark ? "#FFFFFF" : BRAND_GREEN} />
      <circle cx="304" cy="132" r="92" fill={onDark ? BRAND_GREEN : "#FFFFFF"} />
    </svg>
  );
}

/** Mark + "Kvant AI Studio", or the mark alone. */
export default function BrandLogo({
  variant = "full",
  height = 24,
  onDark = false,
  className,
  textClassName,
}: {
  variant?: "full" | "mark";
  height?: number;
  onDark?: boolean;
  className?: string;
  textClassName?: string;
}) {
  if (variant === "mark") {
    return <BrandMark height={height} onDark={onDark} className={className} title={BRAND_NAME} />;
  }
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)} aria-label={BRAND_NAME} role="img">
      <BrandMark height={height} onDark={onDark} />
      <span
        aria-hidden="true"
        className={cn(
          "whitespace-nowrap font-syne font-bold leading-none tracking-[-0.02em]",
          onDark ? "text-white" : "text-[#101323]",
          textClassName,
        )}
        style={{ fontSize: Math.round(height * 0.78) }}
      >
        Kvant <span className={cn("font-medium", onDark ? "text-[#B8EFC0]" : "text-[#027A0E]")}>AI Studio</span>
      </span>
    </span>
  );
}
