/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { useLocation } from "react-router";
import useSWR from "swr";
// plane internal packages
import { setPromiseToast } from "@plane/blocks/toast";
import { Switch } from "@makeplane/propel/components/switch";
// components
import { AuthenticationMethodCard } from "@/components/authentication/authentication-method-card";
import { PageWrapper } from "@/components/common/page-wrapper";
import { Skeleton } from "@/components/common/skeleton";
// hooks
import { useInstance } from "@/hooks/store";
// ee
import { hasConfigKey, readConfig, toConfigPayload } from "@/ee/sso/core-bridge";
import { SsoProviderForm } from "@/ee/sso/provider-form";
import { SSO_PROVIDERS, providerIdFromPath, ssoConfigKey } from "@/ee/sso/provider-fields";
import { SsoProviderIcon } from "@/ee/sso/provider-icon";

const SsoProviderPage = observer(function SsoProviderPage() {
  const { pathname } = useLocation();
  const providerId = providerIdFromPath(pathname);
  // store
  const { fetchInstanceConfigurations, formattedConfig, updateInstanceConfigurations } = useInstance();
  // state
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  useSWR("INSTANCE_CONFIGURATIONS", () => fetchInstanceConfigurations());

  if (!providerId) return <PageWrapper header={{ title: "Unknown provider", description: "" }}>{null}</PageWrapper>;

  const def = SSO_PROVIDERS[providerId];
  const enabledKey = ssoConfigKey(providerId, "ENABLED");
  const isEnabled = readConfig(formattedConfig, enabledKey) === "1";

  if (formattedConfig && !hasConfigKey(formattedConfig, enabledKey)) {
    return (
      <PageWrapper
        header={{
          title: def.name,
          description:
            "Single sign-on is not available on this server. Make sure the API runs with the EE settings and that migrations have completed, then reload this page.",
        }}
      >
        {null}
      </PageWrapper>
    );
  }

  const updateEnabled = async (value: string) => {
    setIsSubmitting(true);
    const updateConfigPromise = updateInstanceConfigurations(toConfigPayload({ [enabledKey]: value })).then(
      (response) => {
        if (!response.some((item) => (item.key as string) === enabledKey)) {
          throw new Error("SSO configuration keys are missing on the server");
        }
        return response;
      }
    );
    setPromiseToast(updateConfigPromise, {
      loading: "Saving Configuration",
      success: {
        title: "Configuration saved",
        message: () => `${def.name} authentication is now ${value === "1" ? "active" : "disabled"}.`,
      },
      error: { title: "Error", message: () => "Failed to save configuration" },
    });
    await updateConfigPromise.catch((err) => console.error(err)).finally(() => setIsSubmitting(false));
  };

  return (
    <PageWrapper
      customHeader={
        <AuthenticationMethodCard
          name={def.name}
          description={def.description}
          icon={<SsoProviderIcon id={providerId} size={24} />}
          config={
            <Switch
              aria-label={`Enable ${def.name} authentication`}
              checked={isEnabled}
              onCheckedChange={() => void updateEnabled(isEnabled ? "0" : "1")}
              size="sm"
              disabled={isSubmitting || !formattedConfig}
            />
          }
          disabled={isSubmitting || !formattedConfig}
          withBorder={false}
        />
      }
    >
      {formattedConfig ? (
        <SsoProviderForm key={providerId} def={def} config={formattedConfig} />
      ) : (
        <Skeleton className="space-y-8">
          <Skeleton.Item height="50px" width="25%" />
          <Skeleton.Item height="50px" />
          <Skeleton.Item height="50px" />
          <Skeleton.Item height="50px" width="50%" />
        </Skeleton>
      )}
    </PageWrapper>
  );
});

export const meta = () => [{ title: "Single sign-on - God Mode" }];

export default SsoProviderPage;
