import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import RegisterForm from "@/components/Auth/RegisterForm";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("account");
  return { title: `${t("register.title")} | Kvant AI Studio` };
}

export default function RegisterPage() {
  return <RegisterForm />;
}
