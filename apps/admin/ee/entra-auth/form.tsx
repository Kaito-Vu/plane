/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { isEmpty } from "lodash-es";
import Link from "next/link";
import { Controller, useForm } from "react-hook-form";
// plane internal packages
import { API_BASE_URL } from "@plane/constants";
import { Button } from "@makeplane/propel/components/button";
import { Input } from "@makeplane/propel/components/input";
import { Switch } from "@makeplane/propel/components/switch";
import { setToast } from "@plane/blocks/toast";
import type { IFormattedInstanceConfiguration, TInstanceEntraAuthenticationConfigurationKeys } from "@plane/types";
// components
import { CodeBlock } from "@/components/common/code-block";
import { ConfirmDiscardModal } from "@/components/common/confirm-discard-modal";
import type { TControllerInputFormField } from "@/components/common/controller-input";
import { ControllerInput } from "@/components/common/controller-input";
import type { TCopyField } from "@/components/common/copy-field";
import { CopyField } from "@/components/common/copy-field";
// hooks
import { useInstance } from "@/hooks/store";

type Props = {
  config: IFormattedInstanceConfiguration;
};

type EntraConfigFormValues = Record<TInstanceEntraAuthenticationConfigurationKeys, string>;

const GUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const ENTRA_KEYS: TInstanceEntraAuthenticationConfigurationKeys[] = [
  "ENTRA_TENANT_ID",
  "ENTRA_CLIENT_ID",
  "ENTRA_CLIENT_SECRET",
  "ENTRA_PROVIDER_NAME",
  "ENTRA_ALLOWED_EMAIL_DOMAINS",
  "ENABLE_ENTRA_SYNC",
  "SSO_ONLY_LOGIN_PAGE",
];

const ENTRA_SWITCHES: { name: "ENABLE_ENTRA_SYNC" | "SSO_ONLY_LOGIN_PAGE"; label: string; description: string }[] = [
  {
    name: "ENABLE_ENTRA_SYNC",
    label: "Refresh user attributes from Microsoft Entra ID during sign in",
    description: "Sync name and photo on every login.",
  },
  {
    name: "SSO_ONLY_LOGIN_PAGE",
    label: "Show only SSO buttons on the sign-in page",
    description: "Make sure /login/internal works before enabling — email and password sign-in moves there.",
  },
];

export function InstanceEntraConfigForm(props: Props) {
  const { config } = props;
  // states
  const [isDiscardChangesModalOpen, setIsDiscardChangesModalOpen] = useState(false);
  // store hooks
  const { updateInstanceConfigurations } = useInstance();
  // form data
  const {
    handleSubmit,
    control,
    reset,
    formState: { errors, isDirty, isSubmitting, isValid },
  } = useForm<EntraConfigFormValues>({
    mode: "onChange",
    defaultValues: {
      ENTRA_TENANT_ID: config["ENTRA_TENANT_ID"] ?? "",
      ENTRA_CLIENT_ID: config["ENTRA_CLIENT_ID"] ?? "",
      ENTRA_CLIENT_SECRET: config["ENTRA_CLIENT_SECRET"] ?? "",
      ENTRA_PROVIDER_NAME: config["ENTRA_PROVIDER_NAME"] ?? "",
      ENTRA_ALLOWED_EMAIL_DOMAINS: config["ENTRA_ALLOWED_EMAIL_DOMAINS"] ?? "",
      ENABLE_ENTRA_SYNC: config["ENABLE_ENTRA_SYNC"] || "0",
      SSO_ONLY_LOGIN_PAGE: config["SSO_ONLY_LOGIN_PAGE"] || "0",
    },
  });

  const originURL = !isEmpty(API_BASE_URL) ? API_BASE_URL : typeof window !== "undefined" ? window.location.origin : "";

  const ENTRA_FORM_FIELDS: TControllerInputFormField<EntraConfigFormValues>[] = [
    {
      key: "ENTRA_CLIENT_ID",
      type: "text",
      label: "Client ID",
      description: <>Application (client) ID of your app registration in Microsoft Entra ID.</>,
      placeholder: "00000000-0000-0000-0000-000000000000",
      error: Boolean(errors.ENTRA_CLIENT_ID),
      required: true,
    },
    {
      key: "ENTRA_CLIENT_SECRET",
      type: "password",
      label: "Client secret",
      description: <>Client secret value created under Certificates &amp; secrets of your app registration.</>,
      placeholder: "Client secret value",
      error: Boolean(errors.ENTRA_CLIENT_SECRET),
      required: true,
    },
    {
      key: "ENTRA_PROVIDER_NAME",
      type: "text",
      label: "Button label (provider name)",
      description: (
        <>Shown on the sign-in button, e.g. &quot;Sign in with Contoso&quot;. Leave empty for the default.</>
      ),
      placeholder: "Microsoft",
      error: Boolean(errors.ENTRA_PROVIDER_NAME),
      required: false,
    },
    {
      key: "ENTRA_ALLOWED_EMAIL_DOMAINS",
      type: "text",
      label: "Allowed email domains",
      description: <>Comma-separated, e.g. &quot;contoso.com, fabrikam.com&quot;. Leave empty for no restriction.</>,
      placeholder: "contoso.com, fabrikam.com",
      error: Boolean(errors.ENTRA_ALLOWED_EMAIL_DOMAINS),
      required: false,
    },
  ];

  const ENTRA_SERVICE_FIELD: TCopyField[] = [
    {
      key: "Redirect_URI",
      label: "Redirect URI",
      url: `${originURL}/auth/entra/callback`,
      description: (
        <>
          We will auto-generate this. Add it as a <CodeBlock darkerShade>Web</CodeBlock> redirect URI under
          Authentication of your app registration in the{" "}
          <a
            href="https://entra.microsoft.com"
            target="_blank"
            className="text-accent-primary hover:underline"
            rel="noreferrer"
            aria-label="Microsoft Entra admin center"
          >
            Entra admin center.
          </a>
        </>
      ),
    },
  ];

  const onSubmit = async (formData: EntraConfigFormValues) => {
    const payload: Partial<EntraConfigFormValues> = {
      ...formData,
      ENTRA_TENANT_ID: formData.ENTRA_TENANT_ID.trim().toLowerCase(),
      ENTRA_ALLOWED_EMAIL_DOMAINS: (formData.ENTRA_ALLOWED_EMAIL_DOMAINS ?? "").trim(),
    };

    try {
      const response = await updateInstanceConfigurations(payload);
      setToast({
        type: "success",
        title: "Done!",
        message: "Your Microsoft Entra ID authentication is configured. You should test it now.",
      });
      reset(
        Object.fromEntries(
          ENTRA_KEYS.map((key) => [key, response.find((item) => item.key === key)?.value ?? ""])
        ) as EntraConfigFormValues
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
            <div className="pt-2.5 text-18 font-medium">Microsoft Entra ID-provided details for Plane</div>
            <div className="flex flex-col gap-1">
              <label htmlFor="ENTRA_TENANT_ID" className="text-13 text-tertiary">
                Tenant ID
              </label>
              <Controller
                control={control}
                name="ENTRA_TENANT_ID"
                rules={{
                  required: "Tenant ID is required.",
                  validate: (value) => GUID_REGEX.test((value ?? "").trim()) || "Tenant ID must be a valid GUID.",
                }}
                render={({ field: { value, onChange, ref } }) => (
                  <Input
                    size="lg"
                    id="ENTRA_TENANT_ID"
                    name="ENTRA_TENANT_ID"
                    type="text"
                    value={value}
                    onChange={onChange}
                    ref={ref}
                    aria-invalid={Boolean(errors.ENTRA_TENANT_ID)}
                    placeholder="00000000-0000-0000-0000-000000000000"
                  />
                )}
              />
              {errors.ENTRA_TENANT_ID ? (
                <p className="pt-0.5 text-11 text-danger-primary">{errors.ENTRA_TENANT_ID.message}</p>
              ) : (
                <p className="pt-0.5 text-11 text-tertiary">Directory (tenant) ID of your app registration.</p>
              )}
            </div>
            {ENTRA_FORM_FIELDS.map((field) => (
              <ControllerInput
                key={field.key}
                control={control}
                type={field.type}
                name={field.key}
                label={field.label}
                description={field.description}
                placeholder={field.placeholder}
                error={field.error}
                required={field.required}
              />
            ))}
            {ENTRA_SWITCHES.map((sw) => (
              <div key={sw.name} className="flex items-center justify-between gap-4">
                <div>
                  <h4 id={`${sw.name}-label`} className="text-13 text-tertiary">
                    {sw.label}
                  </h4>
                  <p className="text-11 text-tertiary">{sw.description}</p>
                </div>
                <Controller
                  control={control}
                  name={sw.name}
                  render={({ field: { value, onChange } }) => (
                    <Switch
                      checked={value === "1"}
                      onCheckedChange={() => onChange(value === "1" ? "0" : "1")}
                      size="sm"
                      aria-labelledby={`${sw.name}-label`}
                    />
                  )}
                />
              </div>
            ))}
            <div className="flex flex-col gap-1 pt-4">
              <div className="flex items-center gap-4">
                <Button
                  variant="primary"
                  size="md"
                  stretch="auto"
                  onClick={(e) => void handleSubmit(onSubmit)(e)}
                  loading={isSubmitting}
                  disabled={!isDirty || !isValid}
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
              <div className="pt-2 text-18 font-medium">Plane-provided details for Microsoft Entra ID</div>
              {ENTRA_SERVICE_FIELD.map((field) => (
                <CopyField key={field.key} label={field.label} url={field.url} description={field.description} />
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
