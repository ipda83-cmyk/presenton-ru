import React from "react";
import { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import OutlinePage from "./components/OutlinePage";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("meta");
  return {
    title: t("outlineTitle"),
    description: t("outlineDescription"),
    alternates: {
      canonical: "https://presenton.ai/create"
    },
    keywords: [
      "presentation generator",
      "AI presentations",
      "data visualization",
      "automatic presentation maker",
      "professional slides",
      "data-driven presentations",
      "document to presentation",
      "presentation automation",
      "smart presentation tool",
      "business presentations"
    ]
  };
}

const page = () => {
  return (
    <div className="relative min-h-screen" translate="no">
      <OutlinePage />
    </div>
  );
};

export default page;
