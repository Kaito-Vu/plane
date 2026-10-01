/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { route } from "@react-router/dev/routes";
import type { RouteConfigEntry } from "@react-router/dev/routes";

// Mirrors SSO_PROVIDER_IDS (apps/admin/ee/sso/provider-fields.ts). Duplicated on purpose: the route table is
// evaluated by the React Router CLI at build time and must stay import-free of app code.
const SSO_PROVIDER_IDS = ["oidc", "azure_ad", "oauth2", "saml"];

// One route per provider to keep the URL a single segment (`/authentication/sso-oidc`), which keeps core's
// breadcrumb generator from producing a link to a non-existent `/authentication/sso`.
export const eeRoutes: RouteConfigEntry[] = SSO_PROVIDER_IDS.map((id) =>
  route(`authentication/sso-${id}`, "./ee/sso/provider-page.tsx", { id: `ee-sso-${id}` })
);
