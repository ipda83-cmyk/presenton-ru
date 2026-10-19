import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import BillingPage from "./components/BillingPage";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("billing");
  return { title: `${t("title")} | Kvant AI Studio` };
}

export default function Page() {
  return <BillingPage />;
}
