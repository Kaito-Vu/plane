/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect } from "react";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
// plane imports
import { KeyOutline } from "@makeplane/propel/icons";
import { setToast } from "@plane/blocks/toast";
import { API_BASE_URL } from "@plane/constants";
import type { TOAuthConfigs, TOAuthOption } from "@plane/types";
// assets
import microsoftLogo from "./microsoft-logo.svg?url";

type TSsoProvider = { id: string; label: string; protocol: "oidc" | "oauth2" | "saml" };

const SSO_ERROR_MESSAGES: Record<string, string> = {
  "6000": "Single sign-on is not configured. Contact your administrator.",
  "6001": "Sign-in with your identity provider failed. Please try again.",
};

const fetchProviders = async (): Promise<TSsoProvider[]> => {
  const response = await fetch(`${API_BASE_URL}/auth/sso/providers/`, { credentials: "include" });
  if (!response.ok) return [];
  const data: unknown = await response.json();
  return Array.isArray(data) ? (data as TSsoProvider[]) : [];
};

export const useSsoOAuthConfig = (oauthActionText: string, basePath: string = "/auth/sso/"): TOAuthConfigs => {
  const searchParams = useSearchParams();
  const nextPath = searchParams.get("next_path");
  const errorCode = searchParams.get("error_code");
  // Plugin not installed (404) or API down: resolve to no providers instead of surfacing an error.
  const { data: providers } = useSWR("EE_SSO_PROVIDERS", () => fetchProviders().catch(() => []), {
    revalidateOnFocus: false,
  });

  useEffect(() => {
    const message = errorCode ? SSO_ERROR_MESSAGES[errorCode] : undefined;
    if (message) setToast({ type: "error", title: "Single sign-on failed", message });
  }, [errorCode]);

  const oAuthOptions: TOAuthOption[] = (providers ?? []).map((provider) => ({
    id: `sso-${provider.id}`,
    text: `${oauthActionText} with ${provider.label}`,
    icon:
      provider.id === "azure_ad" ? (
        <img src={microsoftLogo} height={18} width={18} alt="Microsoft Logo" />
      ) : (
        <KeyOutline className="h-[18px] w-[18px] text-tertiary" />
      ),
    onClick: () => {
      const query = nextPath ? `?next_path=${encodeURIComponent(nextPath)}` : "";
      window.location.assign(`${API_BASE_URL}${basePath}${provider.id}/${query}`);
    },
    enabled: true,
  }));

  return { isOAuthEnabled: oAuthOptions.length > 0, oAuthOptions };
};
