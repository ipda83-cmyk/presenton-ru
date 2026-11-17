import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { ForgotPassword } from "@/components/Auth/AccountPages";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("account");
  return { title: `${t("forgot.title")} | Kvant AI Studio` };
}

export default function ForgotPasswordPage() {
  return <ForgotPassword />;
}
