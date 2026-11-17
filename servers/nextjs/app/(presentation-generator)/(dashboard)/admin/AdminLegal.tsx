"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Eye, Loader2, Pencil } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import LegalArticle from "@/components/Auth/LegalArticle";
import { AccountApi, AccountError, type LegalDocument } from "@/utils/accountApi";

const DOCUMENTS = ["offer", "privacy"] as const;
type Doc = (typeof DOCUMENTS)[number];

function Editor({ doc }: { doc: Doc }) {
  const t = useTranslations("adminLegal");
  const locale = useLocale();
  const [document, setDocument] = useState<LegalDocument | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [preview, setPreview] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    AccountApi.document(doc)
      .then((value) => {
        setDocument(value);
        setTitle(value.title || t(`defaultTitle.${doc}`));
        setBody(value.body);
      })
      .catch(() => setNote({ ok: false, text: t("failed") }));
  }, [doc, t]);

  const save = async () => {
    setBusy(true);
    setNote(null);
    try {
      const saved = await AccountApi.saveDocument(doc, title, body);
      setDocument(saved);
      setNote({ ok: true, text: t("saved") });
    } catch (reason) {
      setNote({ ok: false, text: reason instanceof AccountError ? reason.message : t("failed") });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="space-y-4 rounded-[12px] border border-[#EDEEEF] bg-white p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-[#101323]">{t(`defaultTitle.${doc}`)}</h2>
          <p className="mt-1 text-xs text-[#667085]">
            {document?.updated_at
              ? t("updated", { date: new Date(document.updated_at).toLocaleString(locale) })
              : t("empty")}
          </p>
        </div>
        <Link href={`/legal/${doc}`} target="_blank" className="text-xs font-semibold text-[#027A0E] hover:underline">
          {t("open")} ↗
        </Link>
      </div>
      <label className="block">
        <span className="mb-1.5 block text-xs font-medium text-[#344054]">{t("titleLabel")}</span>
        <input
          id={`legal-${doc}-title`}
          value={title}
          maxLength={200}
          onChange={(event) => setTitle(event.target.value)}
          className="h-10 w-full rounded-lg border border-[#EDEEEF] px-3 text-sm outline-none focus:border-[#03B015]"
        />
      </label>
      <div>
        <div className="mb-1.5 flex items-center justify-between gap-2">
          <span className="text-xs font-medium text-[#344054]">{t("bodyLabel")}</span>
          <button
            type="button"
            onClick={() => setPreview((value) => !value)}
            className="inline-flex h-8 items-center gap-1.5 rounded-full border border-[#EDEEEF] px-3 text-xs text-[#344054] hover:border-[#B8EFC0]"
          >
            {preview ? <Pencil className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
            {preview ? t("edit") : t("preview")}
          </button>
        </div>
        {preview ? (
          <div className="rounded-lg border border-[#EDEEEF] px-5 pb-5 font-syne">
            <LegalArticle body={body} />
          </div>
        ) : (
          <textarea
            id={`legal-${doc}-body`}
            value={body}
            onChange={(event) => setBody(event.target.value)}
            placeholder={t("bodyPlaceholder")}
            className="min-h-[320px] w-full rounded-lg border border-[#EDEEEF] px-3 py-2.5 font-mono text-[13px] leading-6 outline-none focus:border-[#03B015]"
          />
        )}
        <p className="mt-1.5 text-xs text-[#667085]">{t("hint")}</p>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={busy}
          onClick={() => void save()}
          className="inline-flex h-10 items-center gap-2 rounded-full bg-[#03B015] px-5 text-xs font-semibold text-white hover:bg-[#02940F] disabled:opacity-60"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          {t("save")}
        </button>
        {note ? <span className={`text-xs ${note.ok ? "text-[#027A0E]" : "text-[#B42318]"}`}>{note.text}</span> : null}
      </div>
    </section>
  );
}

/** Administrators: the offer and the personal data policy shown at sign-up. */
export default function AdminLegal() {
  const t = useTranslations("adminLegal");
  return (
    <div className="space-y-5">
      <p className="max-w-2xl text-xs leading-relaxed text-[#667085]">{t("desc")}</p>
      {DOCUMENTS.map((doc) => (
        <Editor key={doc} doc={doc} />
      ))}
    </div>
  );
}
