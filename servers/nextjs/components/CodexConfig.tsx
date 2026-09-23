"use client";
import { useEffect, useRef, useState } from "react";
import {
  Loader2,
  RefreshCw,
  Trash2,
  UserCheck,
  ArrowRight,
} from "lucide-react";
import { notify } from "@/components/ui/sonner";
import { useTranslations } from "next-intl";
import { getApiUrl } from "@/utils/api";
import { MixpanelEvent, trackEvent } from "@/utils/mixpanel";
import { usePathname, useRouter } from "next/navigation";
import { syncStoreAfterCodexSignOut } from "@/utils/storeHelpers";
import {
  DEFAULT_CODEX_MODEL,
  isSupportedCodexModel,
} from "@/utils/codexModels";
import {
  isChatGptAuthRequiredResponse,
  normalizeChatGptAuthMessage,
  requestChatGptReauth,
} from "@/utils/chatgptAuth";

interface CodexConfigProps {
  codexModel: string;
  onInputChange: (value: string | boolean, field: string) => void;
  onAuthStatusChange?: (authenticated: boolean) => void;
}

type AuthStatus = "checking" | "unauthenticated" | "polling" | "authenticated";

interface StatusResponse {
  status: string;
  account_id?: string;
  username?: string;
  email?: string;
  is_pro?: boolean;
  detail?: string;
}

export default function CodexConfig({
  codexModel,
  onInputChange,
  onAuthStatusChange,
}: CodexConfigProps) {
  const t = useTranslations("settings");
  const [authStatus, setAuthStatus] = useState<AuthStatus>("checking");
  const [accountId, setAccountId] = useState<string | null>(null);
  const [username, setUsername] = useState<string | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [manualCode, setManualCode] = useState("");
  const [isExchanging, setIsExchanging] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pathname = usePathname();
  const router = useRouter();

  const stopPolling = () => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  };

  useEffect(() => {
    checkCurrentAuthStatus();
    return () => stopPolling();
  }, []);

  useEffect(() => {
    onAuthStatusChange?.(authStatus === "authenticated");
  }, [authStatus, onAuthStatusChange]);

  useEffect(() => {
    if (codexModel && !isSupportedCodexModel(codexModel)) {
      onInputChange(DEFAULT_CODEX_MODEL, "codex_model");
    }
  }, [codexModel, onInputChange]);

  const applyProfile = (data: Partial<StatusResponse>) => {
    setAccountId(data.account_id ?? null);
    setUsername(data.username ?? null);
    setEmail(data.email ?? null);
  };

  const checkCurrentAuthStatus = async () => {
    try {
      const res = await fetch(getApiUrl("/api/v1/ppt/codex/auth/status"));
      if (!res.ok) {
        setAuthStatus("unauthenticated");
        applyProfile({});
        return;
      }
      const data: StatusResponse = await res.json();
      if (data.status === "authenticated") {
        onInputChange('codex', 'LLM');
        if (!isSupportedCodexModel(codexModel)) {
          onInputChange(DEFAULT_CODEX_MODEL, 'codex_model');
        }
        setAuthStatus("authenticated");
        applyProfile(data);
      } else {
        setAuthStatus("unauthenticated");
        applyProfile({});
      }
    } catch {
      setAuthStatus("unauthenticated");
      applyProfile({});
    }
  };

  const handleSignIn = async () => {
    trackEvent(MixpanelEvent.Provider_Login_Clicked, {
      provider: "chatgpt",
      implementation: "codex",
      source: "onboarding",
    });
    try {

      trackEvent(MixpanelEvent.Codex_SignIn_API_Call);
      onInputChange('codex', 'LLM');

      const res = await fetch(getApiUrl("/api/v1/ppt/codex/auth/initiate"), {
        method: "POST",
      });
      if (!res.ok) throw new Error("Failed to initiate auth");
      const data = await res.json();
      const { session_id, url } = data;

      setSessionId(session_id);
      setAuthStatus("polling");
      window.open(url, "_blank", "noopener,noreferrer");

      pollIntervalRef.current = setInterval(async () => {
        try {
          const pollRes = await fetch(
            getApiUrl(`/api/v1/ppt/codex/auth/status/${session_id}`)
          );
          if (!pollRes.ok) return;
          const pollData: StatusResponse = await pollRes.json();

          if (pollData.status === "success") {
            trackEvent(MixpanelEvent.Codex_SignIn_Completed, { method: "browser_poll" });
            trackEvent(MixpanelEvent.Provider_Connection_Completed, {
              provider: "chatgpt",
              implementation: "codex",
              source: "onboarding",
              method: "browser_poll",
            });
            stopPolling();
            setAuthStatus("authenticated");
            applyProfile(pollData);
            setSessionId(null);
            if (!isSupportedCodexModel(codexModel)) {
              onInputChange(DEFAULT_CODEX_MODEL, "codex_model");
            }
            notify.success(
              t("codexSignedInTitle"),
              t("codexSignedInBody")
            );
          } else if (pollData.status === "failed") {
            trackEvent(MixpanelEvent.Codex_SignIn_Failed, { method: "browser_poll" });
            stopPolling();
            setAuthStatus("unauthenticated");
            applyProfile({});
            notify.error(
              t("codexSignInFailedTitle"),
              t("codexAuthIncomplete")
            );
          }
        } catch {
          // keep polling on transient errors
        }
      }, 2000);
    } catch (err) {
      trackEvent(MixpanelEvent.Codex_SignIn_Failed, { method: "initiate" });
      notify.error(
        t("codexSignInFailedTitle"),
        t("codexCouldNotStart")
      );
      setAuthStatus("unauthenticated");
      applyProfile({});
    }
  };

  const handleManualExchange = async () => {
    if (!sessionId || !manualCode.trim()) return;
    setIsExchanging(true);
    try {
      const res = await fetch(getApiUrl("/api/v1/ppt/codex/auth/exchange"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, code: manualCode.trim() }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || t("codexExchangeFailed"));
      }
      const data = await res.json();
      trackEvent(MixpanelEvent.Codex_SignIn_Completed, { method: "manual_exchange" });
      trackEvent(MixpanelEvent.Provider_Connection_Completed, {
        provider: "chatgpt",
        implementation: "codex",
        source: "onboarding",
        method: "manual_exchange",
      });
      stopPolling();
      setAuthStatus("authenticated");
      applyProfile(data);
      setSessionId(null);
      setManualCode("");
      if (!isSupportedCodexModel(codexModel)) {
        onInputChange(DEFAULT_CODEX_MODEL, "codex_model");
      }
      notify.success(
        t("codexSignedInTitle"),
        t("codexSignedInBody")
      );
    } catch (err: any) {
      trackEvent(MixpanelEvent.Codex_SignIn_Failed, { method: "manual_exchange" });
      notify.error(
        t("codexSignInFailedTitle"),
        err.message || t("codexCodeRejected")
      );
    } finally {
      setIsExchanging(false);
    }
  };

  const handleCancelPolling = () => {
    trackEvent(MixpanelEvent.Codex_SignIn_Cancelled);
    stopPolling();
    setSessionId(null);
    setManualCode("");
    setAuthStatus("unauthenticated");
  };

  const handleSignOut = async () => {
    trackEvent(MixpanelEvent.Provider_Logout_Clicked, {
      provider: "chatgpt",
      implementation: "codex",
      source: "onboarding",
    });
    setIsLoggingOut(true);
    try {
      const response = await fetch(getApiUrl("/api/v1/ppt/codex/auth/logout"), {
        method: "POST",
      });
      if (!response.ok) {
        throw new Error(`Codex logout returned ${response.status}`);
      }
      trackEvent(MixpanelEvent.Codex_Signed_Out);
      trackEvent(MixpanelEvent.Provider_Connection_Deleted, {
        provider: "chatgpt",
        implementation: "codex",
        source: "onboarding",
      });
      setAuthStatus("unauthenticated");
      setAccountId(null);
      setUsername(null);
      setEmail(null);
      onInputChange("", "codex_model");
      onInputChange("", "CODEX_ACCESS_TOKEN");
      onInputChange("", "CODEX_REFRESH_TOKEN");
      onInputChange("", "CODEX_TOKEN_EXPIRES");
      onInputChange("", "CODEX_ACCOUNT_ID");
      onInputChange("", "CODEX_USERNAME");
      onInputChange("", "CODEX_EMAIL");
      onInputChange(false, "CODEX_IS_PRO");
      syncStoreAfterCodexSignOut();
      router.replace(pathname.startsWith("/settings") ? "/settings" : "/");
      notify.success(
        t("codexSignedOutTitle"),
        t("codexSignedOutBody")
      );
    } catch {
      notify.error(
        t("codexSignOutFailedTitle"),
        t("codexSignOutFailedBody")
      );
    } finally {
      setIsLoggingOut(false);
    }
  };

  const handleRefreshToken = async () => {
    setIsRefreshing(true);
    try {
      const res = await fetch(getApiUrl("/api/v1/ppt/codex/auth/refresh"), {
        method: "POST",
      });
      if (!res.ok) {
        let errorData: { detail?: unknown; message?: string; error?: string } | null = null;
        let message = "Your ChatGPT session could not be renewed. Please sign in again.";
        try {
          const parsedError: { detail?: unknown; message?: string; error?: string } = await res.json();
          errorData = parsedError;
          message =
            (typeof parsedError.detail === "string" && parsedError.detail) ||
            parsedError.message ||
            parsedError.error ||
            message;
        } catch {}
        if (isChatGptAuthRequiredResponse(res, errorData, message)) {
          requestChatGptReauth({
            message: normalizeChatGptAuthMessage(message),
            source: "codex-refresh",
          });
          return;
        }
        throw new Error(message);
      }
      const data = await res.json();
      applyProfile(data);
      notify.success(
        t("codexSessionRefreshedTitle"),
        t("codexSessionRefreshedBody")
      );
    } catch {
      notify.error(
        t("codexSessionRefreshFailedTitle"),
        t("codexSessionRenewFailed")
      );
      setAuthStatus("unauthenticated");
      applyProfile({});
    } finally {
      setIsRefreshing(false);
    }
  };

  if (authStatus === "checking") {
    return (
      <div className="mb-5 w-full p-3 border border-[#EDEEEF] font-syne rounded-[8px] flex items-center gap-6">
        <div className="w-[74px] h-[74px] bg-[#333333] rounded-full flex items-center justify-center shrink-0">
          <Loader2 className="w-10 h-10 text-[#191919] animate-spin" />
        </div>
        <div className="text-start flex-1 min-w-0">
          <h4 className="text-[#191919] text-lg font-medium">{t("codexCheckingStatus")}</h4>
          <p className="text-[#B3B3B3] text-sm font-normal">
            {t("codexVerifying")}
          </p>
        </div>
      </div>
    );
  }

  if (authStatus === "polling") {
    return (
      <div className="mb-5 space-y-4 font-syne">
        <div className="w-full p-3 border border-[#EDEEEF] rounded-[8px] flex items-center justify-between gap-4">
          <div className="flex items-center gap-6 min-w-0 flex-1">
            <div className="w-[40px] h-[40px] bg-[#EDEEEF] rounded-full flex items-center justify-center shrink-0">
              <Loader2 className="w-5 h-5 text-[#191919] animate-spin" />
            </div>
            <div className="text-start min-w-0">
              <h4 className="text-[#191919] text-lg font-medium">{t("codexWaitingSignIn")}</h4>
              <p className="text-[#B3B3B3] text-sm font-normal">
                {t("codexCompleteInTab")}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleCancelPolling}
            className="shrink-0 text-sm text-[#B3B3B3] hover:text-[#191919] underline underline-offset-2 transition-colors"
          >
            {t("codexCancel")}
          </button>
        </div>

        <div className="space-y-2 rounded-[8px] border border-[#EDEEEF] p-3">
          <p className="text-[#191919] text-xs font-normal">
            {t("codexPasteHint")}
          </p>
          <div className="flex gap-2">
            <input
              type="text"
              placeholder={t("codexPastePlaceholder")}
              className="flex-1 min-w-0 px-3 py-2.5 outline-none border border-[#EDEEEF] rounded-[8px]  text-sm text-[#191919] placeholder:text-[#666666] focus:border-[#555555] transition-colors"
              value={manualCode}
              onChange={(e) => setManualCode(e.target.value)}
            />
            <button
              type="button"
              onClick={handleManualExchange}
              disabled={isExchanging || !manualCode.trim()}
              className="shrink-0 px-4 py-2.5 bg-[#EDEEEF] hover:bg-[#E4E5E6] disabled:opacity-40 disabled:hover:bg-[#EDEEEF] rounded-[8px] text-sm font-medium text-[#191919] transition-colors flex items-center justify-center min-w-[88px]"
            >
              {isExchanging ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                t("codexSubmit")
              )}
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (authStatus === "authenticated") {

    return (
      <div className=" mb-5">
        <div className="flex items-center justify-between gap-3 p-5  border border-[#EDEEEF] rounded-[8px]">
          <div className="flex items-center gap-3">

            <div className="w-[40px] h-[40px] bg-[#333333] rounded-full flex items-center justify-center" >

              <img src="/providers/OpenAI-white.png" alt={t("codexLogoAlt")} className="w-[27px] h-[27px]" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 min-w-0">
                <p className="text-sm font-medium text-[#191919] truncate">
                  {username || email || (accountId ? t("codexAccountWithId", { id: accountId }) : t("codexAccountFallback"))}
                </p>

              </div>
              {email && username && (
                <p className="text-xs text-[#B3B3B3] truncate">{email}</p>
              )}
              {!email && accountId && (
                <p className="text-xs text-[#B3B3B3] truncate">ID: {accountId}</p>
              )}
              <p className="text-xs text-[#B3B3B3]">{t("codexSignedInStatus")}</p>
            </div>
          </div>
          <div className="flex gap-1.5 shrink-0">
            <button
              onClick={handleRefreshToken}
              disabled={isRefreshing}
              title={t("codexRefreshToken")}
              className="flex items-center justify-center px-3.5 py-2.5  border border-[#EDEEEF] rounded-[58px] minid:opacity-40 transition-colors"
            >
              {isRefreshing ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin text-[#191919]" />
              ) : (
                <RefreshCw className="w-3.5 h-3.5 text-[#191919]" />
              )}
            </button>
            <button
              onClick={handleSignOut}
              disabled={isLoggingOut}
              title={t("signOut")}
              className="flex items-center justify-center px-3.5 py-2.5  border border-[#EDEEEF] rounded-[58px]  disabled:opacity-40 transition-colors"
            >
              {isLoggingOut ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin text-[#191919]" />
              ) : (
                <Trash2 className="w-3.5 h-3.5 text-[#191919]" />
              )}
            </button>
          </div>
        </div>


      </div>
    );
  }

  return (
    <button
      onClick={handleSignIn}
      className=" w-full  p-5 border border-[#EDEEEF] font-syne  hover:bg-[#F7F6F9] transition-colors duration-300   rounded-[12px] flex items-center   justify-between  "
    >
      <div className="flex items-center gap-2 flex-1">
        <div className="w-[40px] h-[40px] bg-[#333333] rounded-full flex items-center justify-center" >

          <img src="/providers/OpenAI-white.png" alt={t("codexLogoAlt")} className="w-[27px] h-[27px]" />
        </div>
        <div className="text-start flex-1">
          <h4 className="text-[#191919] text-sm font-medium">{t("codexSignInWith")}</h4>
          <p className="text-[#B3B3B3]   text-xs font-normal">{t("codexNoKeyNeeded")}</p>
        </div>
      </div>
      <ArrowRight className="w-[22px] h-[22px] text-[#4C4C4C]" />
    </button>
  );
}
