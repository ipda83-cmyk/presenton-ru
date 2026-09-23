import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { isCommunityEnabled } from "@/utils/community";
import CommunityPage from "./components/CommunityPage";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("meta");
  return {
    title: t("communityTitle"),
    description: t("communityDescription"),
  };
}

export default function Page() {
  if (!isCommunityEnabled(process.env.PRESENTON_COMMUNITY_ENABLED)) {
    notFound();
  }

  return <CommunityPage />;
}
