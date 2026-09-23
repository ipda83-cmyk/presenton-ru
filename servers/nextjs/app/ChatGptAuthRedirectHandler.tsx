"use client";

import { useEffect, useRef } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { notify } from "@/components/ui/sonner";
import {
  CHATGPT_AUTH_REQUIRED_EVENT,
  ChatGptAuthRequiredEventDetail,
  logoutChatGptAuth,
} from "@/utils/chatgptAuth";

export default function ChatGptAuthRedirectHandler() {
  const t = useTranslations("settings");
  const router = useRouter();
  const pathname = usePathname();
  const handlingRef = useRef(false);

  useEffect(() => {
    const handleAuthRequired = async (event: Event) => {
      const detail = (event as CustomEvent<ChatGptAuthRequiredEventDetail>)
        .detail;

      if (handlingRef.current) return;
      handlingRef.current = true;

      // The backend detail is English; the condition itself is known, so the
      // toast always uses the UI-language wording.
      void detail;
      notify.error(
        t("chatgptReauthTitle"),
        t("chatgptReauthBody"),
        { id: "chatgpt-auth-required", duration: 8000 }
      );

      try {
        await logoutChatGptAuth();
      } catch (error) {
        console.warn("Could not fully clear ChatGPT credentials:", error);
      }

      const target = "/settings?chatgpt=reauth";
      if (pathname === "/settings") {
        router.replace(target);
      } else {
        router.push(target);
      }

      window.setTimeout(() => {
        handlingRef.current = false;
      }, 2000);
    };

    window.addEventListener(CHATGPT_AUTH_REQUIRED_EVENT, handleAuthRequired);
    return () => {
      window.removeEventListener(CHATGPT_AUTH_REQUIRED_EVENT, handleAuthRequired);
    };
  }, [pathname, router]);

  return null;
}
