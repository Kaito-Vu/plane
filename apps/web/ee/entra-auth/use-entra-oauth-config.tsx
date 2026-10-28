/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useSearchParams } from "next/navigation";
import { API_BASE_URL } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import type { TOAuthConfigs } from "@plane/types";
// hooks
import { useInstance } from "@/hooks/store/use-instance";

// generic key icon, no new asset
const EntraIcon = (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
    <circle cx="8" cy="15" r="4" />
    <path d="M11 12l9-9M16 7l3 3" />
  </svg>
);

// next_path is encoded here (core providers pass it raw)
export const getEntraLoginUrl = (nextPath: string | null) =>
  `${API_BASE_URL}/auth/entra/${nextPath ? `?next_path=${encodeURIComponent(nextPath)}` : ``}`;

export const useEntraOAuthConfig = (_oauthActionText: string): TOAuthConfigs => {
  const searchParams = useSearchParams();
  const next_path = searchParams.get("next_path");
  const { config } = useInstance();
  const { t } = useTranslation();
  const isOAuthEnabled = !!config?.is_entra_enabled;
  return {
    isOAuthEnabled,
    oAuthOptions: [
      {
        id: "entra",
        text: t("auth.entra.sign_in_with", { name: config?.entra_provider_name || "Microsoft" }),
        icon: EntraIcon,
        onClick: () => {
          window.location.assign(getEntraLoginUrl(next_path));
        },
        enabled: config?.is_entra_enabled,
      },
    ],
  };
};
