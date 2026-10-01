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
import { setToast } from "@plane/blocks/toast";
import { API_BASE_URL } from "@plane/constants";
import { Button } from "@makeplane/propel/components/button";
import { Switch } from "@makeplane/propel/components/switch";
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
    watch,
    formState: { errors, isDirty, isSubmitting },
  } = useForm<FormValues>({
    defaultValues: Object.fromEntries(
      def.fields.map((f) => [f.field, readConfig(config, ssoConfigKey(def.id, f.field)) || f.defaultValue || ""])
    ),
  });

  const originURL = !isEmpty(API_BASE_URL) ? API_BASE_URL : typeof window !== "undefined" ? window.location.origin : "";

  const onSubmit = async (formData: FormValues) => {
    // the backend silently hides an Azure provider whose tenant is not a GUID: fail loudly here instead
    if (
      def.id === "azure_ad" &&
      !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test((formData.TENANT_ID ?? "").trim())
    ) {
      setToast({
        type: "error",
        title: "Invalid Tenant ID",
        message: "Tenant ID must be the directory (tenant) GUID.",
      });
      return;
    }
    const payload = Object.fromEntries(
      def.fields.map((f) => [ssoConfigKey(def.id, f.field), (formData[f.field] ?? "").trim()])
    );
    try {
      const response = await updateInstanceConfigurations(toConfigPayload(payload));
      // core's PATCH silently ignores keys that do not exist (plugin not enabled / not migrated): detect it
      // instead of reporting success and then wiping the form.
      if (!response.some((item) => (item.key as string) === ssoConfigKey(def.id, def.fields[0].field))) {
        throw new Error("SSO configuration keys are missing on the server");
      }
      setToast({
        type: "success",
        title: "Done!",
        message: `Your ${def.name} authentication is configured. You should test it now.`,
      });
      reset(
        Object.fromEntries(
          def.fields.map((f) => [
            f.field,
            response.find((item) => (item.key as string) === ssoConfigKey(def.id, f.field))?.value ||
              f.defaultValue ||
              "",
          ])
        )
      );
    } catch (err) {
      console.error(err);
      setToast({
        type: "error",
        title: "Error",
        message: "Could not save. Make sure the API runs with the SSO plugin enabled and migrations have completed.",
      });
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
            {def.fields
              .filter((f) => f.type !== "switch")
              .map((f) => (
                <ControllerInput
                  key={f.field}
                  control={control}
                  type={f.type === "password" ? "password" : "text"}
                  name={f.field}
                  label={f.label}
                  description={f.description}
                  placeholder={f.placeholder}
                  error={Boolean(errors[f.field])}
                  required={f.required}
                />
              ))}
            {def.fields.some((f) => f.type === "switch") && <div className="pt-2.5 text-18 font-medium">Options</div>}
            {def.fields
              .filter((f) => f.type === "switch")
              .map((f) => (
                // core's ControllerSwitch hard-codes "Refresh user attributes from <label> during sign in", so the
                // option switch is rendered directly with Controller + Switch ("1" / "0" values).
                <Controller
                  key={f.field}
                  control={control}
                  name={f.field}
                  render={({ field: { value, onChange } }) => (
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex flex-col gap-1">
                        <div className="text-13 text-secondary">{f.label}</div>
                        {f.description && <div className="text-11 text-tertiary">{f.description}</div>}
                      </div>
                      <Switch
                        aria-label={f.label}
                        checked={value === "1"}
                        onCheckedChange={() => onChange(value === "1" ? "0" : "1")}
                        size="sm"
                      />
                    </div>
                  )}
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
              {getServiceFields(def.id, originURL, watch("CALLBACK_URL")).map((field) => (
                <CopyField key={field.key} label={field.label} url={field.url} description={field.description} />
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
