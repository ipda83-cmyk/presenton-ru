'use client'
import React from "react";
import PresentationPage from "./components/PresentationPage";
import { Button } from "@/components/ui/button";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import "../utils/prism-languages";
const page = () => {

  const t = useTranslations("common");
  const router = useRouter();
  const params = useSearchParams();
  const queryId = params.get("id");
  if (!queryId) {
    return (
      <div className="flex flex-col items-center justify-center h-screen font-syne">
        <h1 className="text-2xl font-bold">{t("noPresentationId")}</h1>
        <p className="text-gray-500 pb-4">{t("pleaseTryAgain")}</p>
        <Button onClick={() => router.push("/dashboard")}>{t("goHome")}</Button>
      </div>
    );
  }
  return (

    <PresentationPage presentation_id={queryId} />

  );
};
export default page;
