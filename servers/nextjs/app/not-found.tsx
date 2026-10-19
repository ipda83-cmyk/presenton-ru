import type { Metadata } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { Button } from "@/components/ui/button";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("meta");
  return { title: t("notFoundTitle") };
}

/**
 * Unknown routes only. Keep the 404.svg inside a fixed max height + object-contain
 * so the illustration never scales to full-viewport (the old w-3/4-only layout could).
 */
export default async function NotFound() {
  const t = await getTranslations("notFound");
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gray-100 p-6 text-center">
      <div className="mx-auto w-full max-w-lg rounded-lg bg-white p-8 shadow-md">
        <div className="mx-auto mb-6 flex h-48 w-full max-w-[300px] items-center justify-center overflow-hidden sm:h-56 sm:max-w-sm">
          <img
            src="/404.svg"
            alt={t("imageAlt")}
            width={500}
            height={500}
            className="h-full w-full object-contain object-center"
            loading="eager"
            decoding="async"
          />
        </div>
        <h1 className="mb-4 font-syne text-2xl font-bold text-gray-800 sm:text-3xl">
          {t("heading")}
        </h1>
        <p className="mb-4 text-base text-gray-600 sm:text-lg">
          {t("body")}
        </p>

        <div className="mb-8 flex flex-col justify-center gap-3 sm:flex-row sm:space-x-4">
          <Link href="/dashboard" className="inline-flex sm:flex-1 sm:justify-center">
            <Button className="w-full rounded-md bg-green-600 px-6 py-2 text-white hover:bg-green-700 sm:w-auto">
              {t("home")}
            </Button>
          </Link>
          <Link href="/" className="inline-flex sm:flex-1 sm:justify-center">
            <Button className="w-full rounded-md bg-gray-600 px-6 py-2 text-white hover:bg-gray-700 sm:w-auto">
              {t("start")}
            </Button>
          </Link>
        </div>
      </div>
    </div>
  );
}
