import type { Metadata } from "next";
import { Suspense } from "react";
import { getTranslations } from "next-intl/server";
import { VerifyEmail } from "@/components/Auth/AccountPages";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("account");
  return { title: `${t("verify.title")} | Kvant AI Studio` };
}

export default function VerifyEmailPage() {
  return (
    <Suspense>
      <VerifyEmail />
    </Suspense>
  );
}
