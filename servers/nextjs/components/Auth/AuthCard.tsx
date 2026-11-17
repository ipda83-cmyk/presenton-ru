"use client";

import Link from "next/link";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import BrandLogo from "@/components/brand/BrandLogo";

// The frame of the sign-in, sign-up and password pages (the same look as AuthGate).

export const authInputClass =
  "h-12 w-full rounded-lg border border-[#E1E1E5] bg-white px-4 text-sm text-[#191919] outline-none transition placeholder:text-[#9CA3AF] focus:border-[#03B015] focus:ring-2 focus:ring-[#03B015]/15";
export const authButtonClass =
  "w-full rounded-[58px] border border-[#EDEEEF] bg-[#03B015] px-5 py-3 font-syne text-xs font-semibold text-white transition hover:bg-[#02940F] disabled:cursor-not-allowed disabled:opacity-60";
export const authLinkClass = "font-medium text-[#027A0E] hover:underline";

export default function AuthCard({
  eyebrow,
  title,
  intro,
  children,
  footer,
}: {
  eyebrow?: string;
  title: string;
  intro?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-white p-6 font-syne">
      <div className="absolute right-6 top-6 z-20">
        <LanguageSwitcher />
      </div>
      <section className="relative z-10 w-full max-w-lg rounded-[20px] border border-[#EDEEEF] bg-[#F9F8F8] p-7 sm:p-10">
        <div className="mb-6 flex items-center gap-4">
          <Link href="/" className="flex h-[60px] w-[60px] shrink-0 items-center justify-center rounded-[4px] bg-[#F4FEF5] p-3" aria-label="Kvant AI Studio">
            <BrandLogo variant="mark" height={22} />
          </Link>
          <div>
            {eyebrow ? (
              <p className="font-syne text-[10px] font-semibold uppercase tracking-[0.14em] text-[#03B015]">{eyebrow}</p>
            ) : null}
            <h1 className="mt-1 font-syne text-xl font-normal leading-tight tracking-[-0.03em] text-black sm:text-[22px]">{title}</h1>
          </div>
        </div>
        {intro ? <div className="max-w-md text-sm leading-relaxed text-[#6B7280]">{intro}</div> : null}
        <div className="mt-6">{children}</div>
        {footer ? <div className="mt-6 text-center text-xs text-[#6B7280]">{footer}</div> : null}
      </section>
    </main>
  );
}
