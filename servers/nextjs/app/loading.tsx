import { getTranslations } from "next-intl/server";
import { BrandSplashLoader } from "@/components/ui/brand-splash-loader";

export default async function Loading() {
  const t = await getTranslations("auth");
  return <BrandSplashLoader message={t("preparing")} />;
}
