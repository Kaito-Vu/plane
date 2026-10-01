/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { KeyOutline } from "@makeplane/propel/icons";
// local imports
import microsoftLogo from "./microsoft-logo.svg?url";
import type { TSsoProviderId } from "./provider-fields";

export function SsoProviderIcon({ id, size = 20 }: { id: TSsoProviderId; size?: number }) {
  if (id === "azure_ad") return <img src={microsoftLogo} height={size} width={size} alt="Microsoft Logo" />;
  return <KeyOutline className="h-6 w-6 p-0.5 text-tertiary" />;
}
