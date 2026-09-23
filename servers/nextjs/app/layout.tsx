import type { Metadata } from "next";
import "./globals.css";
import "katex/dist/katex.min.css";
import { Providers } from "./providers";
import MixpanelInitializer from "./MixpanelInitializer";
import { Toaster } from "@/components/ui/sonner";
import TailwindBrowserRuntime from "@/components/runtime/TailwindBrowserRuntime";
import ClientI18nBridge from "@/components/ClientI18nBridge";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages, getTranslations } from "next-intl/server";

export async function generateMetadata(): Promise<Metadata> {
  const locale = await getLocale();
  const t = await getTranslations("meta");
  const title = t("appTitle");
  const description = t("appDescription");
  return {
    metadataBase: new URL("https://presenton.ai"),
    title,
    description,
    keywords: [
      "AI presentation generator",
      "data storytelling",
      "data visualization tool",
      "AI data presentation",
      "presentation generator",
      "data to presentation",
      "interactive presentations",
      "professional slides",
    ],
    openGraph: {
      title,
      description,
      url: "https://presenton.ai",
      siteName: "Presenton",
      images: [
        {
          url: "https://presenton.ai/presenton-feature-graphics.png",
          width: 1200,
          height: 630,
          alt: t("logoAlt"),
        },
      ],
      type: "website",
      locale: locale === "ru" ? "ru_RU" : "en_US",
    },
    alternates: {
      canonical: "https://presenton.ai",
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: ["https://presenton.ai/presenton-feature-graphics.png"],
    },
  };
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    <html lang={locale}>
      <body className="antialiased">
        <NextIntlClientProvider locale={locale} messages={messages}>
          <ClientI18nBridge />
          <Providers>
            <MixpanelInitializer>

              {children}

            </MixpanelInitializer>
          </Providers>
          <Toaster position="top-center" />
        </NextIntlClientProvider>
        <TailwindBrowserRuntime />
      </body>
    </html>
  );
}
