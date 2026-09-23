import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { ArrowUpRight } from "lucide-react";
import LanguageSwitcher from "@/components/LanguageSwitcher";

// Краткая справка внутри приложения на языке интерфейса. Официальная
// документация Presenton есть только на английском — на неё ведут ссылки.
const DOCS_URL = "https://docs.presenton.ai/help";
const TROUBLESHOOTING_URL = "https://docs.presenton.ai/archive/v0.9.0-beta/troubleshooting";
const GITHUB_ISSUES_URL = "https://github.com/presenton/presenton/issues";
const DISCORD_INVITE_URL = "https://discord.com/invite/9ZsKKxudNE";

type Problem = { problem: string; solution: string };

const SECTIONS = [
  { id: "start", kind: "steps", docs: DOCS_URL },
  { id: "language", kind: "list" },
  { id: "templates", kind: "list", docs: DOCS_URL },
  { id: "generation", kind: "problems", docs: `${TROUBLESHOOTING_URL}/generation` },
  { id: "content", kind: "problems", docs: `${TROUBLESHOOTING_URL}/content-and-media` },
  { id: "export", kind: "problems", docs: `${TROUBLESHOOTING_URL}/editing-and-export` },
  { id: "hosting", kind: "problems", docs: `${TROUBLESHOOTING_URL}/hosting` },
  { id: "support", kind: "steps", docs: `${TROUBLESHOOTING_URL}/support` },
] as const;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("help");
  return { title: `${t("metaTitle")} | Presenton` };
}

function ExternalLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 text-sm font-medium text-[#5141E5] hover:underline"
    >
      {children}
      <ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
    </a>
  );
}

export default async function HelpPage() {
  const t = await getTranslations("help");

  return (
    <div className="min-h-screen font-syne">
      <header className="sticky top-0 z-40 ml-7 mr-[9px] flex min-h-[105px] items-center justify-between gap-4 border-b border-[#EDEEEF] bg-white px-1">
        <h1 className="text-[22px] font-medium tracking-[-0.66px] text-[#101323]">
          {t("title")}
        </h1>
        <LanguageSwitcher size="md" />
      </header>

      <main className="ml-7 mr-[9px] max-w-4xl px-1 py-8">
        <p className="text-sm leading-6 text-[#475467]">{t("intro")}</p>
        <div className="mt-3">
          <ExternalLink href={DOCS_URL}>{t("docsLink")}</ExternalLink>
        </div>

        <nav
          aria-label={t("contents")}
          className="mt-8 rounded-[12px] border border-[#EDEEEF] bg-[#F9F8F8] p-5"
        >
          <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-[#7A5AF8]">
            {t("contents")}
          </h2>
          <ol className="mt-3 grid gap-x-6 gap-y-2 sm:grid-cols-2">
            {SECTIONS.map((section, index) => (
              <li key={section.id}>
                <a
                  href={`#${section.id}`}
                  className="text-sm text-[#191919] hover:text-[#5141E5]"
                >
                  {index + 1}. {t(`sections.${section.id}.title`)}
                </a>
              </li>
            ))}
          </ol>
        </nav>

        {SECTIONS.map((section) => (
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
              <ol className="mt-4 list-decimal space-y-2.5 pl-5 text-sm leading-6 text-[#344054] marker:text-[#7A5AF8]">
                {(t.raw(`sections.${section.id}.steps`) as string[]).map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
            ) : null}

            {section.kind === "list" ? (
              <ul className="mt-4 list-disc space-y-2.5 pl-5 text-sm leading-6 text-[#344054] marker:text-[#7A5AF8]">
                {(t.raw(`sections.${section.id}.items`) as string[]).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : null}

            {section.kind === "problems" ? (
              <dl className="mt-4 divide-y divide-[#EDEEEF] rounded-[12px] border border-[#EDEEEF]">
                {(t.raw(`sections.${section.id}.items`) as Problem[]).map((item) => (
                  <div key={item.problem} className="grid gap-1 px-5 py-4 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] md:gap-6">
                    <dt className="text-sm font-medium text-[#101323]">{item.problem}</dt>
                    <dd className="text-sm leading-6 text-[#475467]">{item.solution}</dd>
                  </div>
                ))}
              </dl>
            ) : null}

            {section.id === "support" ? (
              <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2">
                <ExternalLink href={GITHUB_ISSUES_URL}>
                  {t("sections.support.github")}
                </ExternalLink>
                <ExternalLink href={DISCORD_INVITE_URL}>
                  {t("sections.support.discord")}
                </ExternalLink>
              </div>
            ) : null}

            {"docs" in section ? (
              <div className="mt-3">
                <ExternalLink href={section.docs}>{t("moreInDocs")}</ExternalLink>
              </div>
            ) : null}
          </section>
        ))}
      </main>
    </div>
  );
}
