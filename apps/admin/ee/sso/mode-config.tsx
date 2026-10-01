/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import Link from "next/link";
// plane internal packages
import { AnchorButton } from "@makeplane/propel/components/anchor-button";
import { Button } from "@makeplane/propel/components/button";
import { Switch } from "@makeplane/propel/components/switch";
import { SettingsOutline } from "@makeplane/propel/icons";
import type { TInstanceAuthenticationMethodKeys } from "@plane/types";
// hooks
import { useInstance } from "@/hooks/store";
// local imports
import { asMethodKey, readConfig } from "./core-bridge";
import type { TSsoProviderId } from "./provider-fields";
import { SSO_PROVIDERS, isSsoConfigured, ssoConfigKey } from "./provider-fields";

type Props = {
  providerId: TSsoProviderId;
  disabled: boolean;
  updateConfig: (key: TInstanceAuthenticationMethodKeys, value: string) => void;
};

export const SsoModeConfiguration = observer(function SsoModeConfiguration(props: Props) {
  const { providerId, disabled, updateConfig } = props;
  const { formattedConfig } = useInstance();
  const def = SSO_PROVIDERS[providerId];
  const enabledKey = ssoConfigKey(providerId, "ENABLED");
  const isEnabled = readConfig(formattedConfig, enabledKey) === "1";
  const href = `/authentication/sso-${providerId}`;

  return isSsoConfigured(def, formattedConfig) ? (
    <div className="flex items-center gap-4">
      <AnchorButton variant="primary" size="sm" render={<Link href={href} />} label="Edit" />
      <Switch
        checked={isEnabled}
        onCheckedChange={() => updateConfig(asMethodKey(enabledKey), isEnabled ? "0" : "1")}
        size="sm"
        aria-label={`Enable ${def.name}`}
        disabled={disabled}
      />
    </div>
  ) : (
    <Button
      variant="secondary"
      size="sm"
      stretch="auto"
      nativeButton={false}
      render={<Link href={href} />}
      icon={<SettingsOutline className="h-4 w-4 p-0.5 text-tertiary" />}
      label="Configure"
    />
  );
});
