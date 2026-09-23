import { requireAdminSession } from "@/utils/serverAuth";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import AdminPanel from "./AdminPanel";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("meta");
  return { title: t("adminTitle") };
}

export default async function AdminPage() {
  await requireAdminSession();
  return <AdminPanel />;
}
