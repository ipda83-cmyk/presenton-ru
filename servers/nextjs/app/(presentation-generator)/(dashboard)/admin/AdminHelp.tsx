"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowDown,
  ArrowUp,
  ChevronDown,
  Eye,
  FileText,
  ImagePlus,
  Loader2,
  Paperclip,
  Pencil,
  Plus,
  RotateCcw,
  Trash2,
  Video,
} from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { errorMessage } from "@/components/studio/controls";
import { HelpSectionView } from "@/components/help/HelpArticles";
import { builtinHelpSections } from "@/components/help/builtinHelp";
import {
  HelpApi,
  formatFileSize,
  type HelpContent,
  type HelpSection,
} from "../../services/api/help";

const inputClass =
  "h-10 w-full rounded-lg border border-[#EDEEEF] bg-white px-3 text-sm text-[#101323] outline-none focus:border-[#03B015]";
const ghostButton =
  "inline-flex h-8 items-center gap-1.5 rounded-full border border-[#EDEEEF] bg-white px-3 text-xs text-[#344054] transition hover:border-[#B8EFC0] hover:text-[#02940F] disabled:opacity-50";
const iconButton =
  "flex h-8 w-8 items-center justify-center rounded-full text-[#667085] transition hover:bg-[#F4FEF5] hover:text-[#02940F] disabled:opacity-30";

const newId = () => Math.random().toString(36).slice(2, 14);

/** Administrators: the Help page — sections in Markdown, files and videos. */
export default function AdminHelp() {
  const t = useTranslations("adminHelp");
  const tHelp = useTranslations("help");
  const locale = useLocale();
  const [content, setContent] = useState<HelpContent | null>(null);
  const [sections, setSections] = useState<HelpSection[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [preview, setPreview] = useState<Set<string>>(() => new Set());
  const [busy, setBusy] = useState<string | null>("load");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const bodies = useRef<Record<string, HTMLTextAreaElement | null>>({});

  const apply = useCallback(
    (value: HelpContent) => {
      setContent(value);
      setSections(value.custom ? value.sections : builtinHelpSections(tHelp));
      setDirty(false);
    },
    [tHelp],
  );

  const run = useCallback(
    async <T,>(kind: string, action: () => Promise<T>): Promise<T | null> => {
      setBusy(kind);
      setError(null);
      setSaved(false);
      try {
        return await action();
      } catch (reason) {
        setError(errorMessage(reason, t("errors.requestFailed")));
        return null;
      } finally {
        setBusy(null);
      }
    },
    [t],
  );

  useEffect(() => {
    void run("load", async () => apply(await HelpApi.read()));
  }, [apply, run]);

  // A patch, or a function of the current section (for uploads that finish later).
  const change = (
    id: string,
    patch: Partial<HelpSection> | ((section: HelpSection) => Partial<HelpSection>),
  ) => {
    setSections((current) =>
      current.map((section) =>
        section.id === id
          ? { ...section, ...(typeof patch === "function" ? patch(section) : patch) }
          : section,
      ),
    );
    setDirty(true);
    setSaved(false);
  };

  const move = (index: number, step: number) => {
    setSections((current) => {
      const next = [...current];
      const [item] = next.splice(index, 1);
      next.splice(index + step, 0, item);
      return next;
    });
    setDirty(true);
  };

  const remove = (id: string) => {
    setSections((current) => current.filter((section) => section.id !== id));
    setDirty(true);
  };

  const add = () => {
    const section: HelpSection = { id: newId(), title: "", body: "", files: [], videos: [] };
    setSections((current) => [...current, section]);
    setOpen(section.id);
    setDirty(true);
  };

  const togglePreview = (id: string) =>
    setPreview((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const pickFile = (accept: string, onFile: (file: File) => void) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = accept;
    input.onchange = () => {
      const file = input.files?.[0];
      if (file) onFile(file);
    };
    input.click();
  };

  const attachFile = (section: HelpSection) =>
    pickFile("", (file) =>
      void run(`file-${section.id}`, async () => {
        const uploaded = await HelpApi.upload(file);
        change(section.id, (current) => ({ files: [...current.files, uploaded] }));
      }),
    );

  const insertImage = (section: HelpSection) =>
    pickFile("image/png,image/jpeg,image/gif,image/webp", (file) =>
      void run(`image-${section.id}`, async () => {
        const uploaded = await HelpApi.upload(file);
        const area = bodies.current[section.id];
        const alt = uploaded.name.replace(/\.[^.]+$/, "").replace(/[[\]]/g, "");
        const snippet = `\n![${alt}](${uploaded.url})\n`;
        change(section.id, (current) => {
          const at = Math.min(area ? area.selectionStart : current.body.length, current.body.length);
          return { body: current.body.slice(0, at) + snippet + current.body.slice(at) };
        });
      }),
    );

  const save = () =>
    void run("save", async () => {
      apply(await HelpApi.save(sections));
      setSaved(true);
    });

  const reset = () =>
    void run("reset", async () => {
      apply(await HelpApi.reset());
      setConfirmReset(false);
      setOpen(null);
    });

  if (busy === "load" && !content) {
    return (
      <div className="flex items-center gap-2 py-10 text-sm text-[#667085]">
        <Loader2 className="h-4 w-4 animate-spin" /> {t("loading")}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <section className="rounded-[12px] border border-[#EDEEEF] bg-white p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-2xl">
            <h2 className="text-sm font-semibold text-[#101323]">{t("title")}</h2>
            <p className="mt-1 text-xs leading-relaxed text-[#667085]">{t("desc")}</p>
            <p className="mt-2 text-xs font-medium text-[#02940F]">
              {content?.custom
                ? t("stateCustom", {
                    date: content.updated_at ? new Date(content.updated_at).toLocaleString(locale) : "—",
                  })
                : t("stateBuiltin")}
            </p>
          </div>
          <Link href="/help" target="_blank" className={ghostButton}>
            <Eye className="h-3.5 w-3.5" /> {t("openHelp")}
          </Link>
        </div>
      </section>

      {sections.map((section, index) => {
        const expanded = open === section.id;
        const previewing = preview.has(section.id);
        return (
          <section key={section.id} className="rounded-[12px] border border-[#EDEEEF] bg-white">
            <div className="flex items-center gap-2 px-4 py-3">
              <button
                type="button"
                className="flex min-w-0 flex-1 items-center gap-2 text-left"
                onClick={() => setOpen(expanded ? null : section.id)}
                aria-expanded={expanded}
              >
                <ChevronDown
                  className={`h-4 w-4 shrink-0 text-[#667085] transition ${expanded ? "rotate-180" : ""}`}
                />
                <span className="truncate text-sm font-medium text-[#101323]">
                  {section.title || <span className="text-[#98A2B3]">{t("untitled")}</span>}
                </span>
                {section.files.length + section.videos.length ? (
                  <span className="shrink-0 text-xs text-[#667085]">
                    {t("attachments", { files: section.files.length, videos: section.videos.length })}
                  </span>
                ) : null}
              </button>
              <button type="button" className={iconButton} disabled={index === 0} onClick={() => move(index, -1)} aria-label={t("moveUp")}>
                <ArrowUp className="h-4 w-4" />
              </button>
              <button
                type="button"
                className={iconButton}
                disabled={index === sections.length - 1}
                onClick={() => move(index, 1)}
                aria-label={t("moveDown")}
              >
                <ArrowDown className="h-4 w-4" />
              </button>
              <button type="button" className={iconButton} onClick={() => remove(section.id)} aria-label={t("deleteSection")}>
                <Trash2 className="h-4 w-4" />
              </button>
            </div>

            {expanded ? (
              <div className="space-y-5 border-t border-[#EDEEEF] px-5 py-5">
                <label className="block">
                  <span className="mb-1.5 block text-xs font-medium text-[#344054]">{t("sectionTitle")}</span>
                  <input
                    className={inputClass}
                    value={section.title}
                    maxLength={200}
                    placeholder={t("sectionTitlePh")}
                    onChange={(event) => change(section.id, { title: event.target.value })}
                  />
                </label>

                <div>
                  <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
                    <span className="text-xs font-medium text-[#344054]">{t("body")}</span>
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        className={ghostButton}
                        disabled={busy === `image-${section.id}`}
                        onClick={() => insertImage(section)}
                      >
                        {busy === `image-${section.id}` ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <ImagePlus className="h-3.5 w-3.5" />
                        )}
                        {t("insertImage")}
                      </button>
                      <button type="button" className={ghostButton} onClick={() => togglePreview(section.id)}>
                        {previewing ? <Pencil className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                        {previewing ? t("edit") : t("preview")}
                      </button>
                    </div>
                  </div>
                  {previewing ? (
                    <div className="rounded-lg border border-[#EDEEEF] px-5 pb-5 font-syne">
                      <HelpSectionView section={section} />
                    </div>
                  ) : (
                    <>
                      <textarea
                        ref={(element) => {
                          bodies.current[section.id] = element;
                        }}
                        className="min-h-[220px] w-full rounded-lg border border-[#EDEEEF] bg-white px-3 py-2.5 font-mono text-[13px] leading-6 text-[#101323] outline-none focus:border-[#03B015]"
                        value={section.body}
                        maxLength={50000}
                        onChange={(event) => change(section.id, { body: event.target.value })}
                      />
                      <p className="mt-1.5 text-xs leading-5 text-[#667085]">{t("markdownHint")}</p>
                    </>
                  )}
                </div>

                <div>
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <span className="text-xs font-medium text-[#344054]">{t("videos")}</span>
                    <button
                      type="button"
                      className={ghostButton}
                      onClick={() => change(section.id, { videos: [...section.videos, { url: "", title: "" }] })}
                    >
                      <Video className="h-3.5 w-3.5" /> {t("addVideo")}
                    </button>
                  </div>
                  {section.videos.map((video, videoIndex) => (
                    <div key={videoIndex} className="mb-2 grid gap-2 md:grid-cols-[minmax(0,3fr)_minmax(0,2fr)_auto]">
                      <input
                        className={inputClass}
                        type="url"
                        value={video.url}
                        placeholder="https://rutube.ru/video/…"
                        onChange={(event) =>
                          change(section.id, {
                            videos: section.videos.map((item, i) =>
                              i === videoIndex ? { ...item, url: event.target.value, embed: undefined } : item,
                            ),
                          })
                        }
                      />
                      <input
                        className={inputClass}
                        value={video.title}
                        placeholder={t("videoTitlePh")}
                        onChange={(event) =>
                          change(section.id, {
                            videos: section.videos.map((item, i) =>
                              i === videoIndex ? { ...item, title: event.target.value } : item,
                            ),
                          })
                        }
                      />
                      <button
                        type="button"
                        className={iconButton}
                        aria-label={t("remove")}
                        onClick={() =>
                          change(section.id, { videos: section.videos.filter((_, i) => i !== videoIndex) })
                        }
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                  <p className="text-xs leading-5 text-[#667085]">{t("videoHint")}</p>
                </div>

                <div>
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <span className="text-xs font-medium text-[#344054]">{t("files")}</span>
                    <button
                      type="button"
                      className={ghostButton}
                      disabled={busy === `file-${section.id}`}
                      onClick={() => attachFile(section)}
                    >
                      {busy === `file-${section.id}` ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Paperclip className="h-3.5 w-3.5" />
                      )}
                      {t("attachFile")}
                    </button>
                  </div>
                  {section.files.map((file, fileIndex) => (
                    <div key={file.url} className="mb-2 flex items-center gap-2">
                      <FileText className="h-4 w-4 shrink-0 text-[#03B015]" />
                      <input
                        className={inputClass}
                        value={file.name}
                        onChange={(event) =>
                          change(section.id, {
                            files: section.files.map((item, i) =>
                              i === fileIndex ? { ...item, name: event.target.value } : item,
                            ),
                          })
                        }
                      />
                      <span className="shrink-0 text-xs text-[#667085]">{formatFileSize(file.size, locale)}</span>
                      <button
                        type="button"
                        className={iconButton}
                        aria-label={t("remove")}
                        onClick={() =>
                          change(section.id, { files: section.files.filter((_, i) => i !== fileIndex) })
                        }
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                  <p className="text-xs leading-5 text-[#667085]">{t("filesHint")}</p>
                </div>
              </div>
            ) : null}
          </section>
        );
      })}

      <button type="button" className={ghostButton} onClick={add}>
        <Plus className="h-3.5 w-3.5" /> {t("addSection")}
      </button>

      <div className="sticky bottom-4 z-10 flex flex-wrap items-center gap-3 rounded-[12px] border border-[#EDEEEF] bg-white/95 px-5 py-4 shadow-sm backdrop-blur">
        <button
          type="button"
          className="inline-flex h-10 items-center justify-center gap-2 rounded-full bg-[#03B015] px-5 text-xs font-semibold text-white transition hover:bg-[#02940F] disabled:opacity-60"
          disabled={busy !== null}
          onClick={save}
        >
          {busy === "save" ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          {t("save")}
        </button>
        {content?.custom ? (
          confirmReset ? (
            <span className="flex flex-wrap items-center gap-2 text-xs text-[#B42318]">
              {t("resetConfirm")}
              <button type="button" className={ghostButton} disabled={busy !== null} onClick={reset}>
                {busy === "reset" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                {t("resetYes")}
              </button>
              <button type="button" className={ghostButton} onClick={() => setConfirmReset(false)}>
                {t("cancel")}
              </button>
            </span>
          ) : (
            <button type="button" className={ghostButton} onClick={() => setConfirmReset(true)}>
              <RotateCcw className="h-3.5 w-3.5" /> {t("reset")}
            </button>
          )
        ) : null}
        <span className="text-xs text-[#667085]" role="status">
          {error ? (
            <span className="text-[#B42318]">{error}</span>
          ) : saved ? (
            t("saved")
          ) : dirty ? (
            t("unsaved")
          ) : null}
        </span>
      </div>
    </div>
  );
}
