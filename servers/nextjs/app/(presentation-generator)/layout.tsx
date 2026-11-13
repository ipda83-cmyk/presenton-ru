import React from "react";

import { requireAppSession } from "@/utils/serverAuth";
import { ConfigurationInitializer } from "../ConfigurationInitializer";
import OnboardingTips from "@/components/user-onboarding/OnboardingTips";

export default async function Layout({ children }: { children: React.ReactNode }) {
  await requireAppSession();
  return (
    <div>
      <ConfigurationInitializer>
        {children}
        <OnboardingTips />
      </ConfigurationInitializer>
    </div>
  );
}
