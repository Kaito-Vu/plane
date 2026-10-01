# EE SSO Plugin — Phase 4: Admin (God Mode) Configuration Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an instance admin enable, configure and test OIDC / Azure AD / OAuth2 / SAML from the God Mode "Authentication" page, using one generic form driven by a field table.

**Architecture:** All new admin code lives in `apps/admin/ee/sso/` (components) and `apps/admin/app/ee/` (route table). The pages talk to the **existing** core instance-configuration store (`useInstance().formattedConfig` / `updateInstanceConfigurations`) because Phase 1 seeds the `EE_SSO_*` keys into `InstanceConfiguration`; no new API. The only core edits are two small, additive edits at the places where admin has no EE seam yet: `apps/admin/app/routes.ts` (spread EE routes) and `apps/admin/hooks/oauth/index.ts` (spread EE auth modes). The EE keys are not in core's `TInstanceConfigurationKeys` union, so every cast lives in one file (`core-bridge.ts`).

**Tech Stack:** React Router 7 (framework mode), MobX, SWR, react-hook-form, `@makeplane/propel`, `@plane/blocks/toast`.

**Spec:** `docs/superpowers/specs/2026-10-01-ee-sso-plugin-design.md`
**Depends on:** Phase 1 (seeded keys) and Phase 2 (for the SAML keys; SAML card simply shows "Configure" even before that, but saving would fail because rows do not exist — do Phase 2 first).

## Global Constraints

- Core files edited: exactly `apps/admin/app/routes.ts` and `apps/admin/hooks/oauth/index.ts`. Nothing else outside `apps/admin/ee/`, `apps/admin/app/ee/`.
- No `package.json` / `pnpm-lock.yaml` changes.
- Every new `.ts/.tsx` starts with the 5-line license block comment used in core.
- Config key format: `EE_SSO_<PROVIDER_ID_UPPER>_<FIELD>`, field names exactly as in the backend (`apps/api/plane/ee/sso/config.py` `PROVIDERS`).
- Provider ids and routes: `oidc`, `azure_ad`, `oauth2`, `saml` → page path `/authentication/sso-<id>` (single path segment after `authentication` so core's breadcrumb needs no extra label and never links to a non-existent `/authentication/sso`).
- Mode keys passed to core types are `sso-<id>`; the enabled switch key is `EE_SSO_<ID>_ENABLED`.
- Core's "at least one auth method must stay enabled" guard (`canDisableAuthMethod`) must keep working: modes returned by the EE hook are included in the list core inspects.
- Verification: `pnpm --filter admin check:types`, `pnpm --filter admin check:lint`, `pnpm --filter admin check:format` (admin has no unit-test runner; behavior is verified in Task 4).

## File Structure

```
apps/admin/ee/sso/core-bridge.ts           # the only place that casts to core's narrow key types
apps/admin/ee/sso/provider-fields.ts       # field table, ids, helpers
apps/admin/ee/sso/provider-icon.tsx
apps/admin/ee/sso/microsoft-logo.svg
apps/admin/ee/sso/mode-config.tsx          # Configure/Edit + switch cell for the auth modes list
apps/admin/ee/sso/modes.tsx                # getExtendedAuthenticationModes()
apps/admin/ee/sso/provider-form.tsx        # generic form + "Plane-provided details" panel
apps/admin/app/ee/routes.ts                # eeRoutes (route table)
apps/admin/app/ee/sso/provider-page.tsx    # route module (page)
apps/admin/app/routes.ts                   # (modify, 2 lines)
apps/admin/hooks/oauth/index.ts            # (modify, 2 lines)
```

---

### Task 1: Core bridge, field table, icon

**Files:**

- Create: `apps/admin/ee/sso/core-bridge.ts`, `provider-fields.ts`, `provider-icon.tsx`, `microsoft-logo.svg`

**Interfaces:**

- Produces (`core-bridge.ts`):
  - `readConfig(config: IFormattedInstanceConfiguration | undefined, key: string): string`
  - `toConfigPayload(payload: Record<string, string>): Partial<IFormattedInstanceConfiguration>`
  - `asMethodKey(key: string): TInstanceAuthenticationMethodKeys`
  - `asModeKey(key: string): TInstanceAuthenticationModeKeys`
- Produces (`provider-fields.ts`):
  - `type TSsoProviderId = "oidc" | "azure_ad" | "oauth2" | "saml"`
  - `SSO_PROVIDER_IDS: TSsoProviderId[]`
  - `type TSsoField = { field: string; label: string; type: "text" | "password"; required: boolean; placeholder: string; description?: string }`
  - `type TSsoProviderDef = { id: TSsoProviderId; name: string; description: string; fields: TSsoField[] }`
  - `SSO_PROVIDERS: Record<TSsoProviderId, TSsoProviderDef>`
  - `ssoConfigKey(id: TSsoProviderId, field: string): string`
  - `providerIdFromPath(pathname: string): TSsoProviderId | undefined`
  - `isSsoConfigured(def: TSsoProviderDef, config: IFormattedInstanceConfiguration | undefined): boolean`
  - `getServiceFields(id: TSsoProviderId, origin: string): { key: string; label: string; url: string; description: string }[]`
- Produces (`provider-icon.tsx`): `SsoProviderIcon({ id, size })`.

- [ ] **Step 1: `core-bridge.ts`**

```ts
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type {
  IFormattedInstanceConfiguration,
  TInstanceAuthenticationMethodKeys,
  TInstanceAuthenticationModeKeys,
} from "@plane/types";

// Core types its instance-config keys as a closed union. The EE_SSO_* keys are created at runtime by the
// backend plugin (they are plain rows in the same table), so the unavoidable casts live here and nowhere else.

export const readConfig = (config: IFormattedInstanceConfiguration | undefined, key: string): string =>
  (config as unknown as Record<string, string | undefined> | undefined)?.[key] ?? "";

export const toConfigPayload = (payload: Record<string, string>): Partial<IFormattedInstanceConfiguration> =>
  payload as unknown as Partial<IFormattedInstanceConfiguration>;

export const asMethodKey = (key: string): TInstanceAuthenticationMethodKeys => key as TInstanceAuthenticationMethodKeys;

export const asModeKey = (key: string): TInstanceAuthenticationModeKeys => key as TInstanceAuthenticationModeKeys;
```

- [ ] **Step 2: `provider-fields.ts`**

```ts
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { IFormattedInstanceConfiguration } from "@plane/types";
import { readConfig } from "./core-bridge";

export type TSsoProviderId = "oidc" | "azure_ad" | "oauth2" | "saml";

export type TSsoField = {
  field: string;
  label: string;
  type: "text" | "password";
  required: boolean;
  placeholder: string;
  description?: string;
};

export type TSsoProviderDef = {
  id: TSsoProviderId;
  name: string;
  description: string;
  fields: TSsoField[];
};

export const SSO_PROVIDER_IDS: TSsoProviderId[] = ["oidc", "azure_ad", "oauth2", "saml"];

const LABEL: TSsoField = {
  field: "LABEL",
  label: "Button label",
  type: "text",
  required: false,
  placeholder: "Company SSO",
  description: "Shown on the sign-in button as “Sign in with <label>”. Leave empty to use the default.",
};
const CLIENT_ID: TSsoField = {
  field: "CLIENT_ID",
  label: "Client ID",
  type: "text",
  required: true,
  placeholder: "plane",
};
const CLIENT_SECRET: TSsoField = {
  field: "CLIENT_SECRET",
  label: "Client secret",
  type: "password",
  required: true,
  placeholder: "••••••••",
};
const SCOPE: TSsoField = {
  field: "SCOPE",
  label: "Scopes",
  type: "text",
  required: false,
  placeholder: "openid email profile",
  description: "Space-separated. Leave empty for the default.",
};

export const SSO_PROVIDERS: Record<TSsoProviderId, TSsoProviderDef> = {
  oidc: {
    id: "oidc",
    name: "OpenID Connect",
    description: "Allow members to log in or sign up with any OpenID Connect identity provider.",
    fields: [
      LABEL,
      {
        field: "ISSUER",
        label: "Issuer URL",
        type: "text",
        required: true,
        placeholder: "https://idp.example.com",
        description: "We read <issuer>/.well-known/openid-configuration to discover the endpoints.",
      },
      CLIENT_ID,
      CLIENT_SECRET,
      SCOPE,
    ],
  },
  azure_ad: {
    id: "azure_ad",
    name: "Microsoft (Azure AD / Entra ID)",
    description: "Allow members to log in or sign up with their Microsoft work accounts.",
    fields: [
      { ...LABEL, placeholder: "Microsoft" },
      {
        field: "TENANT_ID",
        label: "Directory (tenant) ID",
        type: "text",
        required: true,
        placeholder: "00000000-0000-0000-0000-000000000000",
        description: "Single-tenant only. Find it on the app registration overview page.",
      },
      { ...CLIENT_ID, label: "Application (client) ID" },
      CLIENT_SECRET,
      SCOPE,
    ],
  },
  oauth2: {
    id: "oauth2",
    name: "OAuth2",
    description: "Allow members to log in or sign up with a generic OAuth2 provider.",
    fields: [
      LABEL,
      {
        field: "AUTH_URL",
        label: "Authorization URL",
        type: "text",
        required: true,
        placeholder: "https://idp.example.com/oauth/authorize",
      },
      {
        field: "TOKEN_URL",
        label: "Token URL",
        type: "text",
        required: true,
        placeholder: "https://idp.example.com/oauth/token",
      },
      {
        field: "USERINFO_URL",
        label: "User info URL",
        type: "text",
        required: true,
        placeholder: "https://idp.example.com/oauth/userinfo",
        description: "Must return email and a stable id (sub or id).",
      },
      CLIENT_ID,
      CLIENT_SECRET,
      SCOPE,
    ],
  },
  saml: {
    id: "saml",
    name: "SAML 2.0",
    description: "Allow members to log in or sign up through a SAML 2.0 identity provider (SP-initiated).",
    fields: [
      { ...LABEL, placeholder: "SAML" },
      {
        field: "IDP_ENTITY_ID",
        label: "IdP entity ID",
        type: "text",
        required: true,
        placeholder: "https://idp.example.com/metadata",
      },
      {
        field: "IDP_SSO_URL",
        label: "IdP single sign-on URL",
        type: "text",
        required: true,
        placeholder: "https://idp.example.com/sso",
      },
      {
        field: "IDP_X509CERT",
        label: "IdP signing certificate",
        type: "text",
        required: true,
        placeholder: "MIIC…",
        description: "Paste the X.509 certificate (with or without the BEGIN/END lines).",
      },
      {
        field: "SP_ENTITY_ID",
        label: "Service provider entity ID",
        type: "text",
        required: false,
        placeholder: "Defaults to the metadata URL",
      },
      { field: "ATTR_EMAIL", label: "Email attribute", type: "text", required: false, placeholder: "email" },
      {
        field: "ATTR_FIRST_NAME",
        label: "First name attribute",
        type: "text",
        required: false,
        placeholder: "firstName",
      },
      { field: "ATTR_LAST_NAME", label: "Last name attribute", type: "text", required: false, placeholder: "lastName" },
    ],
  },
};

export const ssoConfigKey = (id: TSsoProviderId, field: string): string => `EE_SSO_${id.toUpperCase()}_${field}`;

/** `/authentication/sso-azure_ad` → `azure_ad` */
export const providerIdFromPath = (pathname: string): TSsoProviderId | undefined => {
  const last = pathname.replace(/\/+$/, "").split("/").pop() ?? "";
  const id = last.replace(/^sso-/, "");
  return SSO_PROVIDER_IDS.find((candidate) => candidate === id);
};

export const isSsoConfigured = (def: TSsoProviderDef, config: IFormattedInstanceConfiguration | undefined): boolean =>
  def.fields.filter((f) => f.required).every((f) => !!readConfig(config, ssoConfigKey(def.id, f.field)));

export const getServiceFields = (id: TSsoProviderId, origin: string) =>
  id === "saml"
    ? [
        {
          key: "acs_url",
          label: "ACS (Assertion Consumer Service) URL",
          url: `${origin}/auth/sso/saml/acs/`,
          description: "Paste this as the reply / ACS URL in your identity provider. Binding: HTTP-POST.",
        },
        {
          key: "entity_id",
          label: "Entity ID / metadata URL",
          url: `${origin}/auth/sso/saml/metadata/`,
          description: "Use as the SP entity ID, or import it as SP metadata. NameID format: email address.",
        },
      ]
    : [
        {
          key: "callback_uri",
          label: "Redirect (callback) URI",
          url: `${origin}/auth/sso/${id}/callback/`,
          description: "Paste this as an allowed redirect URI in your identity provider.",
        },
      ];
```

- [ ] **Step 3: `microsoft-logo.svg`** (same file as Phase 3)

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 23 23" width="23" height="23"><path fill="#f35325" d="M1 1h10v10H1z"/><path fill="#81bc06" d="M12 1h10v10H12z"/><path fill="#05a6f0" d="M1 12h10v10H1z"/><path fill="#ffba08" d="M12 12h10v10H12z"/></svg>
```

- [ ] **Step 4: `provider-icon.tsx`**

```tsx
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
```

- [ ] **Step 5: Verify**

Run: `pnpm --filter admin check:types && pnpm --filter admin check:lint && pnpm --filter admin fix:format && pnpm --filter admin check:format`
Expected: PASS. If `*.svg?url` is not typed for files outside `app/`, mirror the import style in `apps/admin/hooks/oauth/core.tsx`; if `KeyOutline` rejects `className`, copy the usage from the same file (it is used there for the "Passwords" mode).

- [ ] **Step 6: Commit**

```bash
git add apps/admin/ee
git commit -m "feat(ee): admin SSO field table, core bridge and icon"
```

---

### Task 2: Generic provider form and page

**Files:**

- Create: `apps/admin/ee/sso/provider-form.tsx`, `apps/admin/app/ee/sso/provider-page.tsx`, `apps/admin/app/ee/routes.ts`

**Interfaces:**

- Consumes: Task 1 exports; core `useInstance()` (`fetchInstanceConfigurations`, `formattedConfig`, `updateInstanceConfigurations`), `PageWrapper`, `AuthenticationMethodCard`, `Skeleton`, `ControllerInput`, `CopyField`, `ConfirmDiscardModal`, `Switch`, `Button`.
- Produces: `SsoProviderForm({ def, config })`; default-exported route module; `eeRoutes: RouteConfigEntry[]` containing one route per provider at `authentication/sso-<id>` (route ids `ee-sso-<id>`).

- [ ] **Step 1: `provider-form.tsx`**

```tsx
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { isEmpty } from "lodash-es";
import Link from "next/link";
import { useForm } from "react-hook-form";
// plane internal packages
import { setToast } from "@plane/blocks/toast";
import { API_BASE_URL } from "@plane/constants";
import { Button } from "@makeplane/propel/components/button";
import type { IFormattedInstanceConfiguration } from "@plane/types";
// components
import { ConfirmDiscardModal } from "@/components/common/confirm-discard-modal";
import { ControllerInput } from "@/components/common/controller-input";
import { CopyField } from "@/components/common/copy-field";
// hooks
import { useInstance } from "@/hooks/store";
// local imports
import { readConfig, toConfigPayload } from "./core-bridge";
import type { TSsoProviderDef } from "./provider-fields";
import { getServiceFields, ssoConfigKey } from "./provider-fields";

type Props = {
  def: TSsoProviderDef;
  config: IFormattedInstanceConfiguration;
};

type FormValues = Record<string, string>;

export function SsoProviderForm(props: Props) {
  const { def, config } = props;
  // states
  const [isDiscardChangesModalOpen, setIsDiscardChangesModalOpen] = useState(false);
  // store hooks
  const { updateInstanceConfigurations } = useInstance();
  // form
  const {
    handleSubmit,
    control,
    reset,
    formState: { errors, isDirty, isSubmitting },
  } = useForm<FormValues>({
    defaultValues: Object.fromEntries(
      def.fields.map((f) => [f.field, readConfig(config, ssoConfigKey(def.id, f.field))])
    ),
  });

  const originURL = !isEmpty(API_BASE_URL) ? API_BASE_URL : typeof window !== "undefined" ? window.location.origin : "";

  const onSubmit = async (formData: FormValues) => {
    const payload = Object.fromEntries(
      def.fields.map((f) => [ssoConfigKey(def.id, f.field), (formData[f.field] ?? "").trim()])
    );
    try {
      const response = await updateInstanceConfigurations(toConfigPayload(payload));
      setToast({
        type: "success",
        title: "Done!",
        message: `Your ${def.name} authentication is configured. You should test it now.`,
      });
      reset(
        Object.fromEntries(
          def.fields.map((f) => [
            f.field,
            response.find((item) => (item.key as string) === ssoConfigKey(def.id, f.field))?.value ?? "",
          ])
        )
      );
    } catch (err) {
      console.error(err);
    }
  };

  const handleGoBack = (e: React.MouseEvent<HTMLAnchorElement, MouseEvent>) => {
    if (isDirty) {
      e.preventDefault();
      setIsDiscardChangesModalOpen(true);
    }
  };

  return (
    <>
      <ConfirmDiscardModal
        isOpen={isDiscardChangesModalOpen}
        onDiscardHref="/authentication"
        handleClose={() => setIsDiscardChangesModalOpen(false)}
      />
      <div className="flex flex-col gap-8">
        <div className="grid w-full grid-cols-2 gap-x-12 gap-y-8">
          <div className="col-span-2 flex flex-col gap-y-4 pt-1 md:col-span-1">
            <div className="pt-2.5 text-18 font-medium">{def.name} details for Plane</div>
            {def.fields.map((f) => (
              <ControllerInput
                key={f.field}
                control={control}
                type={f.type}
                name={f.field}
                label={f.label}
                description={f.description}
                placeholder={f.placeholder}
                error={Boolean(errors[f.field])}
                required={f.required}
              />
            ))}
            <div className="flex flex-col gap-1 pt-4">
              <div className="flex items-center gap-4">
                <Button
                  variant="primary"
                  size="md"
                  stretch="auto"
                  onClick={(e) => void handleSubmit(onSubmit)(e)}
                  loading={isSubmitting}
                  disabled={!isDirty}
                  label={isSubmitting ? "Saving" : "Save changes"}
                />
                <Button
                  variant="secondary"
                  size="md"
                  stretch="auto"
                  nativeButton={false}
                  render={<Link href="/authentication" onClick={handleGoBack} />}
                  label="Go back"
                />
              </div>
            </div>
          </div>
          <div className="col-span-2 md:col-span-1">
            <div className="flex flex-col gap-y-4 rounded-lg bg-layer-1 px-6 pt-1.5 pb-4">
              <div className="pt-2 text-18 font-medium">Plane-provided details for {def.name}</div>
              {getServiceFields(def.id, originURL).map((field) => (
                <CopyField key={field.key} label={field.label} url={field.url} description={field.description} />
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
```

- [ ] **Step 2: `app/ee/sso/provider-page.tsx`**

```tsx
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
import { readConfig, toConfigPayload } from "@/ee/sso/core-bridge";
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

  const updateEnabled = async (value: string) => {
    setIsSubmitting(true);
    const updateConfigPromise = updateInstanceConfigurations(toConfigPayload({ [enabledKey]: value }));
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
```

Note: the switch here does not enforce core's "keep one method enabled" rule (the Gitea page does not either); the list page does, via `updateConfig`.

- [ ] **Step 3: `app/ee/routes.ts`**

```ts
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
```

- [ ] **Step 4: Verify types**

Run: `pnpm --filter admin check:types`
Expected: PASS. (`react-router typegen` runs first; the route module is not registered in `routes.ts` until Task 3, so typegen ignores it for now — a type error inside `provider-page.tsx` would still be reported by `tsc`.)

- [ ] **Step 5: Commit**

```bash
git add apps/admin/ee apps/admin/app/ee
git commit -m "feat(ee): admin SSO provider form and page"
```

---

### Task 3: Auth-modes list and the two core seam edits

**Files:**

- Create: `apps/admin/ee/sso/mode-config.tsx`, `apps/admin/ee/sso/modes.tsx`
- Modify: `apps/admin/app/routes.ts`, `apps/admin/hooks/oauth/index.ts`

**Interfaces:**

- Consumes: `TGetAuthenticationModeProps` (`@/hooks/oauth/types`: `{ disabled, updateConfig(key: TInstanceAuthenticationMethodKeys, value: string), resolvedTheme }`); Task 1/2 exports.
- Produces: `getExtendedAuthenticationModes(props: TGetAuthenticationModeProps): TInstanceAuthenticationModes[]` returning one entry per provider (`key: "sso-<id>"`, `enabledConfigKey: "EE_SSO_<ID>_ENABLED"`).

- [ ] **Step 1: `mode-config.tsx`** (same behavior as core's `GiteaConfiguration`: "Configure" until required fields exist, then "Edit" + switch)

```tsx
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
```

- [ ] **Step 2: `modes.tsx`**

```tsx
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
```

- [ ] **Step 3: Edit `apps/admin/hooks/oauth/index.ts`** — add the import and spread into the array.

```ts
import { getExtendedAuthenticationModes } from "@/ee/sso/modes";
...
    authenticationModes["gitea"],
    ...getExtendedAuthenticationModes(props),
  ];
```

- [ ] **Step 4: Edit `apps/admin/app/routes.ts`** — add the import under the existing imports and spread after the Gitea route inside the dashboard layout array.

```ts
import { eeRoutes } from "./ee/routes";
...
    route("authentication/gitea", "./(all)/(dashboard)/authentication/gitea/page.tsx"),
    ...eeRoutes,
```

(`react-router` evaluates `routes.ts` with its own loader; the relative import `./ee/routes` resolves inside `app/`. If the CLI rejects TypeScript path aliases there, that is why `routes.ts` uses relative imports only.)

- [ ] **Step 5: Verify**

Run: `pnpm --filter admin check:types && pnpm --filter admin check:lint && pnpm --filter admin fix:format && pnpm --filter admin check:format`
Expected: PASS. `react-router typegen` should now pick up the four `ee-sso-*` route ids.

- [ ] **Step 6: Commit**

```bash
git add apps/admin/ee apps/admin/app/ee apps/admin/app/routes.ts apps/admin/hooks/oauth/index.ts
git commit -m "feat(ee): admin SSO modes on the authentication page"
```

---

### Task 4: Manual end-to-end check

No automated frontend runner exists for admin, so this is a recorded manual check. If the stack cannot be started, say so rather than claiming it passed.

- [ ] **Step 1:** Run the API with the plugin enabled (see Phase 5 compose override, or set `DJANGO_SETTINGS_MODULE=plane.settings.ee` on api/migrator and run `migrate` so the keys are seeded), then `pnpm dev` (admin on :3001).
- [ ] **Step 2:** Open God Mode → Authentication. Expected: four new cards (OpenID Connect, Microsoft, OAuth2, SAML 2.0) after Gitea, each with "Configure".
- [ ] **Step 3:** Open OpenID Connect → fill issuer/client id/secret → Save. Expected: success toast; back on the list the card shows "Edit" + switch; switch on → web login page shows the button (Phase 3).
- [ ] **Step 4:** Disable every other method then try to disable the last one (SSO). Expected: core's "at least one authentication method must remain enabled" toast (proves the modes are in core's list).
- [ ] **Step 5:** Reload the page: saved values persist (secret field shows the stored value like Gitea's). Open SAML: the right-hand panel shows ACS URL and metadata URL; saving certificate text with and without BEGIN/END lines both work (backend normalizes).
- [ ] **Step 6:** Check the breadcrumb on `/authentication/sso-oidc` shows only "Authentication" (no broken link).
- [ ] **Step 7:** Record what was run/seen in the PR description.

---

## Self-Review (done against the spec)

- Spec coverage: admin config pages for all four protocols (generic form + field table), enable switches integrated with core's disable-guard, callback/ACS/metadata values for the admin to copy.
- Spec deviations: no `packages/ee-sso` (admin pages need `@/` app internals, and a new package would force `package.json`/lockfile edits); no EE admin API endpoint (core configurations endpoint is reused); route per provider instead of `:provider` so core's breadcrumb needs no label (the `header/extended.ts` seam stays untouched). Update the spec.
- Core files touched: only `apps/admin/app/routes.ts` and `apps/admin/hooks/oauth/index.ts` (2 lines each).
- Field names match backend `PROVIDERS` (`ISSUER`, `TENANT_ID`, `AUTH_URL`, `TOKEN_URL`, `USERINFO_URL`, `CLIENT_ID`, `CLIENT_SECRET`, `SCOPE`, `IDP_ENTITY_ID`, `IDP_SSO_URL`, `IDP_X509CERT`, `SP_ENTITY_ID`, `ATTR_EMAIL`, `ATTR_FIRST_NAME`, `ATTR_LAST_NAME`, plus `ENABLED`, `LABEL`) — checked.
- Risks: `*.svg?url` / `KeyOutline` prop typing; `routes.ts` import resolution of `./ee/routes`; whether the configuration serializer returns decrypted secrets (assumed, as for Gitea); the duplicated provider-id list in `app/ee/routes.ts` must be kept in sync with `SSO_PROVIDER_IDS` (add a note when adding providers).
- Not verified by running: written from code reading only.
