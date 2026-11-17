import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getLocale, getTranslations } from "next-intl/server";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import BrandLogo from "@/components/brand/BrandLogo";
import LegalArticle from "@/components/Auth/LegalArticle";
import { getServerFastApiBase } from "@/utils/serverAuth";
import type { LegalDocument } from "@/utils/accountApi";

// The public offer and the personal data policy (Admin → Documents); no sign-in.

const DOCUMENTS = ["offer", "privacy"] as const;

async function load(doc: string): Promise<LegalDocument | null> {
  try {
    const response = await fetch(`${getServerFastApiBase()}/api/v1/legal/${doc}`, { cache: "no-store" });
    return response.ok ? ((await response.json()) as LegalDocument) : null;
  } catch {
    return null;
  }
}

export async function generateMetadata({ params }: { params: Promise<{ doc: string }> }): Promise<Metadata> {
  const { doc } = await params;
  const t = await getTranslations("account.legal");
  const document = DOCUMENTS.includes(doc as (typeof DOCUMENTS)[number]) ? await load(doc) : null;
  return { title: `${document?.title || t(doc === "privacy" ? "privacy" : "offer")} | Kvant AI Studio` };
}

export default async function LegalPage({ params }: { params: Promise<{ doc: string }> }) {
  const { doc } = await params;
  if (!DOCUMENTS.includes(doc as (typeof DOCUMENTS)[number])) notFound();
  const t = await getTranslations("account.legal");
  const locale = await getLocale();
  const document = await load(doc);
  const title = document?.title || t(doc === "privacy" ? "privacy" : "offer");

  return (
    <div className="min-h-screen bg-white font-syne">
      <header className="sticky top-0 z-10 border-b border-[#EDEEEF] bg-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-4 px-4 py-4 sm:px-6">
          <Link href="/" className="flex items-center gap-2 text-sm font-semibold text-[#101323]">
            <BrandLogo variant="mark" height={20} />
            Kvant AI Studio
          </Link>
          <LanguageSwitcher />
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
        <h1 className="text-2xl font-semibold tracking-[-0.02em] text-[#101323]">{title}</h1>
        {document?.updated_at ? (
          <p className="mt-2 text-xs text-[#667085]">
            {t("updated", { date: new Date(document.updated_at).toLocaleDateString(locale) })}
          </p>
        ) : null}
        {document?.body ? <LegalArticle body={document.body} /> : <p className="mt-8 text-sm text-[#667085]">{t("empty")}</p>}
      </main>
    </div>
  );
}
