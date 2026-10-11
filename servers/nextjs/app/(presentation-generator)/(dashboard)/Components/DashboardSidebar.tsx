"use client";

import React, { useEffect, useState } from "react";
import { LayoutDashboard, Star, Brain, Settings, HelpCircle, UsersRound, Sparkles, Brush, ImagePlus, Menu } from "lucide-react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { useTranslations } from "next-intl";
import StudioMark from "@/components/studio/StudioMark";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";



export const defaultNavItems = [
    { key: "dashboard" as const, label: "Dashboard", icon: LayoutDashboard },
    { key: "templates" as const, label: "Standard", icon: Star },
    { key: "designs" as const, label: "Smart", icon: Brain },
    { key: "community" as const, label: "Community", icon: UsersRound },



];
// AI Image Studio tools, grouped under the presentation sections.
const studioNavItems = [
    { href: "/studio", key: "studioGenerate" as const, icon: Sparkles },
    { href: "/studio/brush", key: "studioBrush" as const, icon: Brush },
    { href: "/studio/reference", key: "studioReference" as const, icon: ImagePlus },
];

export const BelongingNavItems = [
    { key: "settings" as const, label: "Settings", icon: Settings },
    
]

type DashboardSidebarProps = {
    showCommunity?: boolean;
    showTemplates?: boolean;
};

const TemplatesIcon = ({ className, color = "currentColor" }: { className?: string; color?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true"><path d="M4 14h6" /><path d="M4 2h10" /><rect x="4" y="18" width="16" height="4" rx="1" /><rect x="4" y="6" width="16" height="4" rx="1" /></svg>
);

type MobileItem = { href: string; label: string; icon: React.ComponentType<{ className?: string }> };

// Phones: the 114px rail would take a third of the screen, so the same
// sections open from a menu button in a slim top bar instead.
const MobileNav = ({ showCommunity, showTemplates }: Required<DashboardSidebarProps>) => {
    const pathname = usePathname();
    const t = useTranslations("dash");
    const [open, setOpen] = useState(false);

    useEffect(() => {
        setOpen(false);
    }, [pathname]);

    const sections: MobileItem[] = [
        { href: "/dashboard", label: t("sidebar.dashboard"), icon: LayoutDashboard },
        ...(showTemplates ? [{ href: "/templates", label: t("sidebar.templates"), icon: TemplatesIcon }] : []),
        ...(showCommunity ? [{ href: "/community", label: t("sidebar.community"), icon: UsersRound }] : []),
    ];
    const studio: MobileItem[] = studioNavItems.map(({ href, key, icon }) => ({ href, label: t(`sidebar.${key}`), icon }));
    const footer: MobileItem[] = [
        { href: "/settings", label: t("sidebar.settings"), icon: Settings },
        { href: "/help", label: t("sidebar.help"), icon: HelpCircle },
    ];

    const item = ({ href, label, icon: Icon }: MobileItem) => {
        const active = pathname === href;
        return (
            <Link
                key={href}
                href={href}
                prefetch={false}
                aria-current={active ? "page" : undefined}
                className={[
                    "flex min-h-11 items-center gap-3 rounded-[10px] px-3 text-sm transition-colors",
                    active ? "bg-white font-medium text-[#101323] shadow-[0_4px_10px_rgba(124,81,248,0.12)]" : "text-slate-800 hover:bg-white/70",
                ].join(" ")}
            >
                <Icon className={`h-4 w-4 shrink-0 ${active ? "text-[#5146E5]" : "text-slate-600"}`} />
                {label}
            </Link>
        );
    };

    return (
        <div className="flex h-14 items-center gap-3 border-b border-[#E1E1E5] bg-[#F6F6F9] px-4 md:hidden">
            <Link href="/dashboard" className="flex items-center gap-2" aria-label={t("sidebar.dashboard")}>
                <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#7C51F8] p-0.5">
                    <img src="/logo-with-bg.png" alt={t("logoAlt")} className="h-full w-full object-contain" />
                </span>
                <span className="font-syne text-base font-semibold text-[#101323]">Presenton</span>
            </Link>
            <Sheet open={open} onOpenChange={setOpen}>
                <SheetTrigger asChild>
                    <button
                        type="button"
                        aria-label={t("sidebar.menu")}
                        className="ml-auto flex h-11 w-11 items-center justify-center rounded-full text-[#101323] transition-colors hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7A5AF8]"
                    >
                        <Menu className="h-5 w-5" aria-hidden="true" />
                    </button>
                </SheetTrigger>
                <SheetContent side="left" aria-describedby={undefined} className="flex w-[280px] flex-col overflow-y-auto bg-[#F6F6F9] p-0 font-syne">
                    <SheetTitle className="px-5 pb-1 pt-5 font-syne text-base font-semibold text-[#101323]">{t("sidebar.menu")}</SheetTitle>
                    <nav aria-label={t("sectionsAria")} className="flex flex-1 flex-col gap-1 px-3 pb-6">
                        {sections.map(item)}
                        <p className="mb-1 mt-4 flex items-center gap-1.5 px-3">
                            <StudioMark size={18} />
                            <span className="text-[10px] font-bold uppercase tracking-[0.08em] text-[#7A5AF8]">{t("sidebar.studio")}</span>
                        </p>
                        {studio.map(item)}
                        <div className="my-3 border-t border-[#E1E1E5]" />
                        {footer.map(item)}
                    </nav>
                </SheetContent>
            </Sheet>
        </div>
    );
};

const DashboardSidebar = ({
    showCommunity = true,
    showTemplates = true,
}: DashboardSidebarProps) => {
    const pathname = usePathname();
    const t = useTranslations("dash");

    return (
        <>
        <MobileNav showCommunity={showCommunity} showTemplates={showTemplates} />
        <aside
            className="sticky top-0 hidden h-screen w-[114px] shrink-0 flex-col justify-between border-r border-[#E1E1E5] bg-[#F6F6F9] px-4 py-8 backdrop-blur md:flex"
            aria-label={t("sidebarAria")}
        >
            <div>

                <Link href={`/dashboard`} className="flex items-center  pb-6 border-b border-[#E1E1E5]   gap-2    ">
                    <div className="bg-[#7C51F8] rounded-full cursor-pointer p-1 flex justify-center items-center mx-auto">
                        <img src="/logo-with-bg.png" alt={t("logoAlt")} className="h-[40px] object-contain w-full" />
                    </div>
                </Link>
                <nav className="pt-6 font-syne" aria-label={t("sectionsAria")}>
                    <div className="  space-y-6">

                        {/* Dashboard */}
                        <Link
                            prefetch={false}
                            href={`/dashboard`}
                            className={[
                                "flex flex-col tex-center items-center gap-2  transition-colors",
                                pathname === "/dashboard" ? "" : "ring-transparent",
                            ].join(" ")}
                            aria-label={t("sidebar.dashboard")}
                            title={t("sidebar.dashboard")}
                        >
                            <LayoutDashboard className={["h-4 w-4", pathname === "/dashboard" ? "text-[#5146E5]" : "text-slate-600"].join(" ")} />
                            <span className="text-[11px] text-slate-800">{t("sidebar.dashboard")}</span>
                        </Link>
                        {showTemplates ? <Link
                            prefetch={false}
                            href={`/templates`}
                            className={[
                                "flex flex-col tex-center items-center gap-2  transition-colors",
                                pathname === "/templates" ? "" : "ring-transparent",
                            ].join(" ")}
                            aria-label={t("sidebar.templates")}
                            title={t("sidebar.templates")}
                        >
                            <div className="flex flex-col cursor-pointer tex-center items-center gap-2  transition-colors">
                                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke={`${pathname === "/templates" ? "#5146E5" : "#475569"}`} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4"><path d="M4 14h6" /><path d="M4 2h10" /><rect x="4" y="18" width="16" height="4" rx="1" /><rect x="4" y="6" width="16" height="4" rx="1" /></svg>
                                <span className="text-[11px] text-slate-800">{t("sidebar.templates")}</span>
                            </div>
                        </Link> : null}
                        {showCommunity ? <Link
                            prefetch={false}
                            href="/community"
                            className="flex flex-col items-center gap-2 text-center transition-colors"
                            aria-label={t("sidebar.community")}
                            title={t("sidebar.community")}
                        >
                            <UsersRound className={`h-4 w-4 ${pathname === "/community" ? "text-[#5146E5]" : "text-slate-600"}`} />
                            <span className="text-[11px] text-slate-800">{t("sidebar.community")}</span>
                        </Link> : null}
                        <div className="border-t border-[#E1E1E5] pt-4" role="group" aria-labelledby="sidebar-studio-label">
                            <p id="sidebar-studio-label" className="mb-4 flex items-center justify-center gap-1.5">
                                <StudioMark size={18} />
                                <span className="text-[10px] font-bold uppercase tracking-[0.08em] text-[#7A5AF8]">{t("sidebar.studio")}</span>
                            </p>
                            <div className="space-y-4">
                                {studioNavItems.map(({ href, key, icon: Icon }) => {
                                    const active = pathname === href;
                                    return (
                                        <Link
                                            key={href}
                                            prefetch={false}
                                            href={href}
                                            aria-current={active ? "page" : undefined}
                                            className={[
                                                "-mx-2 flex flex-col items-center gap-1.5 rounded-[10px] px-0.5 py-1.5 text-center transition-colors",
                                                active ? "bg-white shadow-[0_4px_10px_rgba(124,81,248,0.12)]" : "hover:bg-white/60",
                                            ].join(" ")}
                                        >
                                            <Icon className={`h-4 w-4 ${active ? "text-[#5146E5]" : "text-slate-600"}`} aria-hidden="true" />
                                            <span className="text-[11px] leading-[1.25] text-slate-800">{t(`sidebar.${key}`)}</span>
                                        </Link>
                                    );
                                })}
                            </div>
                        </div>
                        {/* <Link
                            prefetch={false}
                            href={`/theme`}
                            className={[
                                "flex flex-col tex-center items-center gap-2  transition-colors",
                                pathname === "/theme" ? "" : "ring-transparent",
                            ].join(" ")}
                            aria-label={t("themes")}
                            title={t("themes")}
                        >
                            <div className="flex flex-col cursor-pointer tex-center items-center gap-2  transition-colors">
                                <Palette className={`h-4 w-4 ${pathname === "/theme" ? "text-[#5146E5]" : "text-slate-600"}`} />
                                <span className="text-[11px] text-slate-800">{t("themes")}</span>
                            </div>
                        </Link> */}
                    </div>
                </nav>
            </div>

            <div className="border-t border-[#E1E1E5] pt-5 font-syne">
                  <Link
                    href="/settings"
                    className="flex flex-col items-center gap-2 transition-colors"
                >
                    <Settings className="h-4 w-4" />
                    <span className="text-[11px] text-slate-800">{t("sidebar.settings")}</span>
                </Link>
                <div className="py-2"/>
                <Link
                    prefetch={false}
                    href="/help"
                    className="flex flex-col items-center gap-2 transition-colors"
                >
                    <HelpCircle className={`h-4 w-4 ${pathname === "/help" ? "text-[#5146E5]" : ""}`} />
                    <span className="text-[11px] text-slate-800">{t("sidebar.help")}</span>
                </Link>
            </div>

        </aside>
        </>
    );
};

export default DashboardSidebar;
