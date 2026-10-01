/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
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
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import type { TIssueType, TIssueTypeConflict } from "@plane/types";
import { firstErrorMessage } from "../rules";
import { useTypeName } from "./type-name";

type Props = {
  type: TIssueType | null;
  candidates: TIssueType[]; // other types the issues may move to
  onClose: () => void;
  onDelete: (migrateTo?: string) => Promise<void>;
};

export function TypeDeleteDialog({ type, candidates, onClose, onDelete }: Props) {
  const { t } = useTranslation();
  const typeName = useTypeName();
  const [inUse, setInUse] = useState<number | null>(null); // set after a 409 with a count
  const [migrateTo, setMigrateTo] = useState("");
  const [busy, setBusy] = useState(false);
  const close = () => {
    setInUse(null);
    setMigrateTo("");
    onClose();
  };

  const confirm = async () => {
    setBusy(true);
    try {
      await onDelete(migrateTo || undefined);
      close();
    } catch (error) {
      const conflict = error as TIssueTypeConflict | undefined;
      if (typeof conflict?.count === "number" && conflict.count > 0 && !migrateTo) setInUse(conflict.count);
      else
        setToast({
          type: "error",
          title: t("work_item_types.settings.item_delete_confirmation.toast.error.title"),
          message: firstErrorMessage(error) ?? t("work_item_types.ee.workspace.delete_failed"),
        });
    } finally {
      setBusy(false);
    }
  };

  if (!type) return null;
  return (
    <Dialog open onOpenChange={(open) => !open && close()}>
      <DialogContent size="sm">
        <DialogMain>
          <DialogHeader>
            <DialogHeading>
              <DialogTitle>{t("work_item_types.ee.workspace.delete_title", { name: typeName(type) })}</DialogTitle>
            </DialogHeading>
          </DialogHeader>
          <DialogBody>
            <p className="text-body-xs-regular text-secondary">
              {t("work_item_types.ee.workspace.delete_description")}
            </p>
            {inUse !== null && (
              <label className="mt-3 flex flex-col gap-1 text-body-xs-regular">
                {t("work_item_types.ee.workspace.delete_in_use", { count: inUse })}
                <select
                  value={migrateTo}
                  onChange={(e) => setMigrateTo(e.target.value)}
                  className="rounded-md border border-subtle bg-transparent px-2 py-1"
                >
                  <option value="">{t("work_item_types.ee.workspace.migrate_placeholder")}</option>
                  {candidates.map((c) => (
                    <option key={c.id} value={c.id}>
                      {typeName(c)}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </DialogBody>
        </DialogMain>
        <DialogActions>
          <Button variant="secondary" size="md" stretch="auto" label={t("cancel")} onClick={close} />
          <Button
            variant="danger"
            size="md"
            stretch="auto"
            loading={busy}
            disabled={inUse !== null && !migrateTo}
            label={t("work_item_types.settings.item_delete_confirmation.primary_button")}
            onClick={confirm}
          />
        </DialogActions>
      </DialogContent>
    </Dialog>
  );
}
