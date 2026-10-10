import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { getServerAuthStatus } from "@/utils/serverAuth";
import { isStudioImagePath } from "../../../services/api/studio-paths";
import StudioBrush from "../components/StudioBrush";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("studio.pages");
  return { title: `${t("brush")} | Presenton` };
}

export default async function StudioBrushPage({
  searchParams,
}: {
  searchParams: Promise<{ image?: string | string[] }>;
}) {
  const [status, params] = await Promise.all([getServerAuthStatus(), searchParams]);
  const image = typeof params.image === "string" && isStudioImagePath(params.image) ? params.image : null;
  return <StudioBrush isAdmin={status.role === "admin"} initialImage={image} />;
}
