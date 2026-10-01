/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// plane imports
import type { TOAuthConfigs } from "@plane/types";
// ee imports
import { useSsoOAuthConfig } from "@/ee/sso/use-sso-oauth-config";

export const useExtendedOAuthConfig = (oauthActionText: string): TOAuthConfigs => useSsoOAuthConfig(oauthActionText);
