import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { getServerAuthStatus } from "@/utils/serverAuth";
import StudioGenerate from "./components/StudioGenerate";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("studio.pages");
  return { title: `${t("generate")} | Kvant AI Studio` };
}

export default async function StudioPage() {
  const status = await getServerAuthStatus();
  return <StudioGenerate isAdmin={status.role === "admin"} />;
}
