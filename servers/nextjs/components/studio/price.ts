import { formatRub, studioPrice } from "@/app/(presentation-generator)/services/api/billing";
import type { StudioConfig, StudioModel } from "@/app/(presentation-generator)/services/api/studio";

/** "Generate" -> "Generate · 12 ₽" for users who pay (administrators see no price). */
export function withPrice(
  label: string,
  config: StudioConfig | null | undefined,
  model: StudioModel | null | undefined,
  options: { resolution?: string; quality?: string; count?: number; times?: number } = {},
): string {
  if (!config?.charged || !model) return label;
  const one = studioPrice(config.prices, model, {
    resolution: model.resolutions.includes(options.resolution ?? "") ? options.resolution : undefined,
    quality: model.quality_levels.includes((options.quality ?? "") as never) ? options.quality : undefined,
    count: options.count,
  });
  if (one == null) return label;
  return `${label} · ${formatRub(one * Math.max(1, options.times ?? 1))}`;
}
