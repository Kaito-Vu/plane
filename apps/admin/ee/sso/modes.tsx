/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TInstanceAuthenticationModes } from "@plane/types";
// hooks
import type { TGetAuthenticationModeProps } from "@/hooks/oauth/types";
// local imports
import { asMethodKey, asModeKey } from "./core-bridge";
import { SsoModeConfiguration } from "./mode-config";
import { SSO_PROVIDERS, SSO_PROVIDER_IDS, ssoConfigKey } from "./provider-fields";
import { SsoProviderIcon } from "./provider-icon";

export const getExtendedAuthenticationModes = ({
  disabled,
  updateConfig,
}: TGetAuthenticationModeProps): TInstanceAuthenticationModes[] =>
  SSO_PROVIDER_IDS.map((id) => ({
    key: asModeKey(`sso-${id}`),
    name: SSO_PROVIDERS[id].name,
    description: SSO_PROVIDERS[id].description,
    icon: <SsoProviderIcon id={id} />,
    config: <SsoModeConfiguration providerId={id} disabled={disabled} updateConfig={updateConfig} />,
    enabledConfigKey: asMethodKey(ssoConfigKey(id, "ENABLED")),
  }));
