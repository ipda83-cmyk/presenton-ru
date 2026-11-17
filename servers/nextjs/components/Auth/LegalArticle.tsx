"use client";

import { HelpSectionView } from "@/components/help/HelpArticles";

/** A document in Markdown, rendered and sanitized the same way as Help. */
export default function LegalArticle({ body }: { body: string }) {
  return <HelpSectionView section={{ id: "document", title: "", body, files: [], videos: [] }} />;
}
