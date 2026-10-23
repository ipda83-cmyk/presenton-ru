"use client";

import { useEffect, useState } from "react";
import DOMPurify from "dompurify";
import { marked } from "marked";
import { ArrowUpRight, FileText, PlayCircle } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import {
  formatFileSize,
  type HelpSection,
} from "@/app/(presentation-generator)/services/api/help";

/** Markdown → safe HTML (links open in a new tab; no scripts, frames or styles). */
function useMarkdown(source: string): string {
  const [html, setHtml] = useState("");
  useEffect(() => {
    let alive = true;
    void Promise.resolve(marked.parse(source, { gfm: true, breaks: true })).then((parsed) => {
      if (!alive) return;
      const clean = DOMPurify.sanitize(parsed, {
        USE_PROFILES: { html: true },
        FORBID_TAGS: ["style", "iframe", "form", "input", "button"],
        FORBID_ATTR: ["style"],
      });
      const holder = document.createElement("div");
      holder.innerHTML = clean;
      holder.querySelectorAll("a[href]").forEach((link) => {
        link.setAttribute("target", "_blank");
        link.setAttribute("rel", "noreferrer");
      });
      setHtml(holder.innerHTML);
    });
    return () => {
      alive = false;
    };
  }, [source]);
  return html;
}

function SectionBody({ body }: { body: string }) {
  const html = useMarkdown(body);
  if (!body.trim()) return null;
  return (
    <div
      className="prose prose-sm mt-4 max-w-none text-[#344054] prose-headings:font-medium prose-headings:text-[#101323] prose-a:text-[#02940F] prose-li:marker:text-[#03B015] prose-img:rounded-lg"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

export function HelpSectionView({ section }: { section: HelpSection }) {
  const t = useTranslations("help");
  const locale = useLocale();
  return (
    <section
      id={`s-${section.id}`}
      aria-labelledby={`s-${section.id}-title`}
      className="mt-10 scroll-mt-32"
    >
      {section.title ? (
        <h2
          id={`s-${section.id}-title`}
          className="text-lg font-medium tracking-[-0.3px] text-[#101323]"
        >
          {section.title}
        </h2>
      ) : null}
      <SectionBody body={section.body} />

      {section.videos.length ? (
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          {section.videos.map((video, index) =>
            video.embed ? (
              <figure key={`${video.url}-${index}`} className="overflow-hidden rounded-[12px] border border-[#EDEEEF] bg-black">
                <iframe
                  src={video.embed}
                  title={video.title || t("video")}
                  className="aspect-video w-full"
                  allow="encrypted-media; fullscreen; picture-in-picture"
                  allowFullScreen
                  loading="lazy"
                  referrerPolicy="strict-origin-when-cross-origin"
                />
                {video.title ? (
                  <figcaption className="bg-white px-4 py-2 text-xs text-[#475467]">{video.title}</figcaption>
                ) : null}
              </figure>
            ) : (
              <a
                key={`${video.url}-${index}`}
                href={video.url}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-3 rounded-[12px] border border-[#EDEEEF] px-4 py-3 text-sm text-[#101323] hover:border-[#B8EFC0]"
              >
                <PlayCircle className="h-5 w-5 shrink-0 text-[#03B015]" aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate">{video.title || video.url}</span>
                <ArrowUpRight className="h-4 w-4 shrink-0 text-[#667085]" aria-hidden="true" />
              </a>
            ),
          )}
        </div>
      ) : null}

      {section.files.length ? (
        <ul className="mt-5 divide-y divide-[#EDEEEF] rounded-[12px] border border-[#EDEEEF]">
          {section.files.map((file) => (
            <li key={file.url}>
              <a
                href={file.url}
                target="_blank"
                rel="noreferrer"
                download={file.name}
                className="flex items-center gap-3 px-4 py-3 text-sm text-[#101323] hover:bg-[#F9F8F8]"
              >
                <FileText className="h-5 w-5 shrink-0 text-[#03B015]" aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate">{file.name}</span>
                {file.size ? (
                  <span className="shrink-0 text-xs text-[#667085]">{formatFileSize(file.size, locale)}</span>
                ) : null}
              </a>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

/** The edited help: contents, then the sections. */
export default function HelpArticles({ sections }: { sections: HelpSection[] }) {
  const t = useTranslations("help");
  const titled = sections.filter((section) => section.title);
  return (
    <>
      {titled.length > 1 ? (
        <nav
          aria-label={t("contents")}
          className="mt-8 rounded-[12px] border border-[#EDEEEF] bg-[#F9F8F8] p-5"
        >
          <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-[#03B015]">
            {t("contents")}
          </h2>
          <ol className="mt-3 grid gap-x-6 gap-y-2 sm:grid-cols-2">
            {titled.map((section, index) => (
              <li key={section.id}>
                <a href={`#s-${section.id}`} className="text-sm text-[#191919] hover:text-[#02940F]">
                  {index + 1}. {section.title}
                </a>
              </li>
            ))}
          </ol>
        </nav>
      ) : null}
      {sections.map((section) => (
        <HelpSectionView key={section.id} section={section} />
      ))}
    </>
  );
}
