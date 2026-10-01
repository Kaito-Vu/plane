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
  type: "text" | "password" | "switch";
  required: boolean;
  placeholder: string;
  description?: string;
  /** used when the stored value is empty (switches: "1" = on) */
  defaultValue?: string;
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
  placeholder: "openid profile",
  description: "Space-separated. Leave empty for the default.",
};

const ALLOW_SIGNUP: TSsoField = {
  field: "ALLOW_SIGNUP",
  label: "Allow sign-up",
  type: "switch",
  required: false,
  placeholder: "",
  defaultValue: "1",
  description:
    "On: a user that is not linked yet is created at first login. Off: only users linked by an administrator (`sso_link`) can log in with this provider. The instance-wide sign-up setting still applies on top.",
};

const CALLBACK_URL: TSsoField = {
  field: "CALLBACK_URL",
  label: "Callback URL (optional)",
  type: "text",
  required: false,
  placeholder: "Leave empty to use the URL shown on the right",
  description:
    "Override only if your identity provider must use a different public URL. It must be an absolute http(s) URL that still reaches this server's /auth/sso/... endpoint.",
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
      CALLBACK_URL,
      ALLOW_SIGNUP,
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
        label: "Tenant ID",
        type: "text",
        required: true,
        placeholder: "00000000-0000-0000-0000-000000000000",
        description:
          "The tenant (GUID) of your directory. Plane accepts sign-ins from this one tenant only (it must be the tenant GUID, not a domain name; the `tid` claim is always checked). Users are identified by their Entra object id (`oid`, with `tid`), never by e-mail or UPN; guest accounts are rejected. Enable Assignment required on the enterprise application in Entra to control who may sign in.",
      },
      { ...CALLBACK_URL, label: "Callback URL" },
      {
        field: "ISSUER",
        label: "Issuer URL (optional)",
        type: "text",
        required: false,
        placeholder: "https://login.microsoftonline.com/<tenant-id>/v2.0",
        description: "Leave empty to use the v2.0 issuer of the tenant above. Override only for a sovereign cloud.",
      },
      { ...CLIENT_ID, label: "Client ID" },
      { ...CLIENT_SECRET, label: "Client Secret" },
      ALLOW_SIGNUP,
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
        description: "Must return a stable user id (`sub` or `id`). No e-mail is needed or used.",
      },
      CLIENT_ID,
      CLIENT_SECRET,
      SCOPE,
      CALLBACK_URL,
      ALLOW_SIGNUP,
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
      {
        field: "ATTR_FIRST_NAME",
        label: "First name attribute",
        type: "text",
        required: false,
        placeholder: "firstName",
      },
      { field: "ATTR_LAST_NAME", label: "Last name attribute", type: "text", required: false, placeholder: "lastName" },
      { ...CALLBACK_URL, label: "ACS URL (optional)" },
      ALLOW_SIGNUP,
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

export const getServiceFields = (id: TSsoProviderId, origin: string, callbackOverride?: string) => {
  const custom = (callbackOverride ?? "").trim();
  const override = custom.startsWith("http://") || custom.startsWith("https://") ? custom : undefined;
  return id === "saml"
    ? [
        {
          key: "acs_url",
          label: "ACS (Assertion Consumer Service) URL",
          url: override ?? `${origin}/auth/sso/saml/acs/`,
          description: "Paste this as the reply / ACS URL in your identity provider. Binding: HTTP-POST.",
        },
        {
          key: "entity_id",
          label: "Entity ID / metadata URL",
          url: `${origin}/auth/sso/saml/metadata/`,
          description:
            "Use as the SP entity ID, or import it as SP metadata. NameID format: Persistent (Entra: user.objectid).",
        },
      ]
    : [
        {
          key: "callback_uri",
          label: "Redirect (callback) URI",
          url: override ?? `${origin}/auth/sso/${id}/callback/`,
          description:
            "Paste this as an allowed redirect URI in your identity provider. Shown for this site's address; the server uses WEB_URL / APP_BASE_URL unless you set a callback URL override.",
        },
      ];
};
