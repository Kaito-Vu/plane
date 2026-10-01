/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { Button } from "@makeplane/propel/components/button";
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogHeading,
  DialogMain,
  DialogTitle,
} from "@makeplane/propel/components/dialog";
import { InputField } from "@makeplane/propel/components/input-field";
import { Switch } from "@makeplane/propel/components/switch";
import { EmojiPicker, Logo } from "@plane/blocks/emoji-icon-picker";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import type { TIssueType } from "@plane/types";
import { firstErrorMessage } from "../rules";

type TFormValues = Pick<TIssueType, "name" | "description" | "level" | "is_epic" | "logo_props">;

type Props = {
  isOpen: boolean;
  type?: TIssueType; // undefined = create
  onClose: () => void;
  onSubmit: (data: Partial<TIssueType>) => Promise<TIssueType>;
};

const NEW_TYPE: TFormValues = {
  name: "",
  description: "",
  level: 1,
  is_epic: false,
  logo_props: { in_use: "icon", icon: { name: "CheckSquare", color: "#3B82F6", background_color: "#FFFFFF" } },
};

export function TypeFormDialog({ isOpen, type, onClose, onSubmit }: Props) {
  const { t } = useTranslation();
  const [pickerOpen, setPickerOpen] = useState(false);
  const {
    control,
    handleSubmit,
    register,
    watch,
    setValue,
    formState: { isSubmitting, errors },
  } = useForm<TFormValues>({ values: type ? { ...NEW_TYPE, ...type } : NEW_TYPE });
  const logo = watch("logo_props");
  const isPreset = !!type?.is_preset; // presets keep their level and epic flag (server enforces too)

  const submit = async (values: TFormValues) => {
    try {
      const saved = await onSubmit({ ...values, level: Number(values.level) });
      if (saved.low_contrast) {
        setToast({ type: "warning", title: saved.name, message: t("work_item_types.ee.workspace.low_contrast") });
      }
      onClose();
    } catch (error) {
      setToast({
        type: "error",
        title: t("work_item_types.create.toast.error.title"),
        message: firstErrorMessage(error) ?? t("work_item_types.ee.workspace.save_failed"),
      });
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent size="md">
        <form onSubmit={handleSubmit(submit)} className="flex min-h-0 flex-1 flex-col">
          <DialogMain>
            <DialogHeader>
              <DialogHeading>
                <DialogTitle>
                  {type ? t("work_item_types.update.title") : t("work_item_types.create.title")}
                </DialogTitle>
              </DialogHeading>
            </DialogHeader>
            <DialogBody>
              <div className="flex flex-col gap-4">
                <div className="flex items-center gap-3">
                  <EmojiPicker
                    isOpen={pickerOpen}
                    handleToggle={setPickerOpen}
                    iconType="lucide"
                    showEmojiTab={false}
                    defaultOpen="icon"
                    defaultIconColor={logo.icon?.color ?? "#6d7b8a"}
                    label={
                      <span
                        aria-label={t("work_item_types.ee.workspace.icon")}
                        className="flex size-9 items-center justify-center rounded-md border border-subtle"
                        style={{ backgroundColor: logo.icon?.background_color }}
                      >
                        <Logo logo={logo} size={18} type="lucide" />
                      </span>
                    }
                    onChange={(value) => {
                      if (value.type !== "icon") return;
                      setValue("logo_props", {
                        in_use: "icon",
                        icon: { ...logo.icon, name: value.value.name, color: value.value.color },
                      });
                    }}
                  />
                  <label className="flex items-center gap-2 text-body-xs-regular text-secondary">
                    {t("work_item_types.ee.workspace.background")}
                    {/* native colour input: no picker dependency */}
                    <input
                      type="color"
                      value={logo.icon?.background_color ?? "#FFFFFF"}
                      onChange={(e) =>
                        setValue("logo_props", {
                          in_use: "icon",
                          icon: { ...logo.icon, background_color: e.target.value.toUpperCase() },
                        })
                      }
                    />
                  </label>
                </div>
                <Controller
                  control={control}
                  name="name"
                  rules={{ required: true, validate: (v) => v.trim().length > 0 }}
                  render={({ field: { value, onChange, ref } }) => (
                    <InputField
                      id="wit-name"
                      name="name"
                      value={value}
                      onChange={onChange}
                      ref={ref}
                      size="2xl"
                      orientation="vertical"
                      placeholder={t("work_item_types.create_update.form.name.placeholder")}
                      error={errors.name ? t("work_item_types.create_update.form.name.placeholder") : undefined}
                    />
                  )}
                />
                <textarea
                  {...register("description")}
                  rows={3}
                  className="w-full rounded-md border border-subtle bg-transparent px-3 py-2 text-body-xs-regular"
                  placeholder={t("work_item_types.create_update.form.description.placeholder")}
                />
                <Controller
                  control={control}
                  name="level"
                  rules={{ min: 0, max: 9, required: true }}
                  render={({ field: { value, onChange, ref } }) => (
                    <InputField
                      id="wit-level"
                      name="level"
                      type="number"
                      min={0}
                      max={9}
                      value={value?.toString()}
                      onChange={onChange}
                      ref={ref}
                      size="2xl"
                      orientation="vertical"
                      disabled={isPreset}
                      placeholder={t("work_item_types.ee.workspace.level")}
                      error={errors.level ? t("work_item_types.ee.workspace.level_hint") : undefined}
                    />
                  )}
                />
                <p className="text-body-xs-regular text-tertiary">{t("work_item_types.ee.workspace.level_hint")}</p>
                <Controller
                  control={control}
                  name="is_epic"
                  render={({ field: { value, onChange } }) => (
                    <label className="flex items-center gap-2 text-body-xs-regular">
                      <Switch size="sm" checked={value} disabled={isPreset} onCheckedChange={onChange} />
                      {t("work_item_types.ee.workspace.is_epic")}
                    </label>
                  )}
                />
              </div>
            </DialogBody>
          </DialogMain>
          <DialogActions>
            <Button variant="secondary" size="md" stretch="auto" label={t("cancel")} onClick={onClose} />
            <Button
              variant="primary"
              size="md"
              stretch="auto"
              type="submit"
              loading={isSubmitting}
              label={type ? t("work_item_types.update.button") : t("work_item_types.create.button")}
            />
          </DialogActions>
        </form>
      </DialogContent>
    </Dialog>
  );
}
