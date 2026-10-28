/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import Link from "next/link";
// icons
import { SettingsOutline } from "@makeplane/propel/icons";
// plane internal packages
import { AnchorButton } from "@makeplane/propel/components/anchor-button";
import { Button } from "@makeplane/propel/components/button";
import { Switch } from "@makeplane/propel/components/switch";
import type { TInstanceAuthenticationMethodKeys } from "@plane/types";
// hooks
import { useInstance } from "@/hooks/store";

type Props = {
  disabled: boolean;
  updateConfig: (key: TInstanceAuthenticationMethodKeys, value: string) => void;
};

export const EntraConfiguration = observer(function EntraConfiguration(props: Props) {
  const { disabled, updateConfig } = props;
  // store
  const { formattedConfig } = useInstance();
  // derived values
  const EntraConfig = formattedConfig?.IS_ENTRA_ENABLED ?? "";
  const EntraConfigured =
    !!formattedConfig?.ENTRA_TENANT_ID && !!formattedConfig?.ENTRA_CLIENT_ID && !!formattedConfig?.ENTRA_CLIENT_SECRET;

  return (
    <>
      {EntraConfigured ? (
        <div className="flex items-center gap-4">
          <AnchorButton variant="primary" size="sm" render={<Link href="/authentication/entra" />} label="Edit" />
          <Switch
            checked={Boolean(parseInt(EntraConfig))}
            onCheckedChange={() => updateConfig("IS_ENTRA_ENABLED", Boolean(parseInt(EntraConfig)) ? "0" : "1")}
            size="sm"
            aria-label="Enable Entra"
            disabled={disabled}
          />
        </div>
      ) : (
        <Button
          variant="secondary"
          size="sm"
          stretch="auto"
          nativeButton={false}
          render={<Link href="/authentication/entra" />}
          icon={<SettingsOutline className="h-4 w-4 p-0.5 text-tertiary" />}
          label="Configure"
        />
      )}
    </>
  );
});
