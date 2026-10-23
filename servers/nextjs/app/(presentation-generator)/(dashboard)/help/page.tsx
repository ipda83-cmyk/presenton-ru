import type { Metadata } from "next";
import { headers } from "next/headers";
import { getTranslations } from "next-intl/server";
import { ArrowUpRight } from "lucide-react";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import HelpArticles from "@/components/help/HelpArticles";
import {
  BUILTIN_SECTIONS,
  DOCS_URL,
  type BuiltinProblem,
} from "@/components/help/builtinHelp";
import { getServerFastApiBase } from "@/utils/serverAuth";
import type { HelpContent } from "../../services/api/help";

// The help the administrator edited (Admin → Help), otherwise the built-in
// one: a short guide in the interface language.

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("help");
  return { title: `${t("metaTitle")} | Kvant AI Studio` };
}

async function editedHelp(): Promise<HelpContent | null> {
  const cookie = (await headers()).get("cookie") ?? "";
  try {
    const response = await fetch(`${getServerFastApiBase()}/api/v1/help`, {
      headers: cookie ? { cookie } : undefined,
      cache: "no-store",
    });
    if (!response.ok) return null;
    const content = (await response.json()) as HelpContent;
    return content.custom ? content : null;
  } catch {
    return null;
  }
}

function ExternalLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 text-sm font-medium text-[#02940F] hover:underline"
    >
      {children}
      <ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
    </a>
  );
}

async function BuiltinHelp() {
  const t = await getTranslations("help");
  return (
    <>
      <p className="text-sm leading-6 text-[#475467]">{t("intro")}</p>
      <div className="mt-3">
        <ExternalLink href={DOCS_URL}>{t("docsLink")}</ExternalLink>
      </div>
      <p className="mt-2 text-xs leading-5 text-[#667085]">{t("basedOn")}</p>

      <nav
        aria-label={t("contents")}
        className="mt-8 rounded-[12px] border border-[#EDEEEF] bg-[#F9F8F8] p-5"
      >
        <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-[#03B015]">
          {t("contents")}
        </h2>
        <ol className="mt-3 grid gap-x-6 gap-y-2 sm:grid-cols-2">
          {BUILTIN_SECTIONS.map((section, index) => (
            <li key={section.id}>
              <a
                href={`#${section.id}`}
                className="text-sm text-[#191919] hover:text-[#02940F]"
              >
                {index + 1}. {t(`sections.${section.id}.title`)}
              </a>
            </li>
          ))}
        </ol>
      </nav>

      {BUILTIN_SECTIONS.map((section) => (
        <section
          key={section.id}
          id={section.id}
          aria-labelledby={`${section.id}-title`}
          className="mt-10 scroll-mt-32"
        >
          <h2
            id={`${section.id}-title`}
            className="text-lg font-medium tracking-[-0.3px] text-[#101323]"
          >
            {t(`sections.${section.id}.title`)}
          </h2>

          {section.kind === "steps" ? (
            <ol className="mt-4 list-decimal space-y-2.5 pl-5 text-sm leading-6 text-[#344054] marker:text-[#03B015]">
              {(t.raw(`sections.${section.id}.steps`) as string[]).map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          ) : null}

          {section.kind === "list" ? (
            <ul className="mt-4 list-disc space-y-2.5 pl-5 text-sm leading-6 text-[#344054] marker:text-[#03B015]">
              {(t.raw(`sections.${section.id}.items`) as string[]).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : null}

          {section.kind === "problems" ? (
            <dl className="mt-4 divide-y divide-[#EDEEEF] rounded-[12px] border border-[#EDEEEF]">
              {(t.raw(`sections.${section.id}.items`) as BuiltinProblem[]).map((item) => (
                <div key={item.problem} className="grid gap-1 px-5 py-4 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] md:gap-6">
                  <dt className="text-sm font-medium text-[#101323]">{item.problem}</dt>
                  <dd className="text-sm leading-6 text-[#475467]">{item.solution}</dd>
                </div>
              ))}
            </dl>
          ) : null}

          {"docs" in section ? (
            <div className="mt-3">
              <ExternalLink href={section.docs}>{t("moreInDocs")}</ExternalLink>
            </div>
          ) : null}
        </section>
      ))}
    </>
  );
}

export default async function HelpPage() {
  const t = await getTranslations("help");
  const edited = await editedHelp();

  return (
    <div className="min-h-screen font-syne">
      <header className="sticky top-0 z-40 ml-7 mr-[9px] flex min-h-[105px] items-center justify-between gap-4 border-b border-[#EDEEEF] bg-white px-1">
        <h1 className="text-[22px] font-medium tracking-[-0.66px] text-[#101323]">
          {t("title")}
        </h1>
        <LanguageSwitcher size="md" />
      </header>

      <main className="ml-7 mr-[9px] max-w-4xl px-1 py-8">
        {edited ? <HelpArticles sections={edited.sections} /> : <BuiltinHelp />}
      </main>
    </div>
  );
}
