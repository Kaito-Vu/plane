/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useEffect, useState } from "react";
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
import type { TIssueType, TIssueTypeConflict, TIssueTypeUsage } from "@plane/types";
import { firstErrorMessage } from "../rules";
import { useTypeName } from "./type-name";

type Props = {
  type: TIssueType | null;
  /** Active types with the same level and epic flag: the only valid migration targets. */
  candidates: TIssueType[];
  onClose: () => void;
  onDelete: (migrateTo?: string) => Promise<void>;
  fetchUsage: (typeId: string) => Promise<TIssueTypeUsage>;
};

export function TypeDeleteDialog({ type, candidates, onClose, onDelete, fetchUsage }: Props) {
  const { t } = useTranslation();
  const typeName = useTypeName();
  const [usage, setUsage] = useState<TIssueTypeUsage | null>(null);
  const [usageFailed, setUsageFailed] = useState(false);
  const [migrateTo, setMigrateTo] = useState("");
  const [busy, setBusy] = useState(false);
  const typeId = type?.id;

  const loadUsage = useCallback(() => {
    if (!typeId) return;
    setUsageFailed(false);
    fetchUsage(typeId).then(setUsage, () => setUsageFailed(true));
    // oxlint-disable-next-line eslint-plugin-react-hooks/exhaustive-deps
  }, [typeId]);

  // usage is fetched up-front so the counts are visible before confirming
  useEffect(() => {
    setUsage(null);
    setMigrateTo("");
    loadUsage();
  }, [loadUsage]);

  const needsMigration = (usage?.count ?? 0) > 0;
  const noCandidates = needsMigration && candidates.length === 0;

  const confirm = async () => {
    setBusy(true);
    try {
      await onDelete(needsMigration ? migrateTo || undefined : undefined);
      onClose();
    } catch (error) {
      if (typeof (error as TIssueTypeConflict | undefined)?.count === "number") loadUsage(); // usage changed meanwhile
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
    <Dialog open onOpenChange={(open) => !open && onClose()}>
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
            <div className="mt-3 text-body-xs-regular" aria-live="polite">
              {usageFailed ? (
                <div className="flex items-center gap-2">
                  <span>{t("work_item_types.ee.workspace.delete_usage_failed")}</span>
                  <Button
                    variant="secondary"
                    size="sm"
                    stretch="auto"
                    label={t("work_item_types.ee.retry")}
                    onClick={loadUsage}
                  />
                </div>
              ) : usage === null ? null : needsMigration ? (
                <>
                  <p>
                    {t("work_item_types.ee.workspace.delete_usage", { issues: usage.issues, drafts: usage.drafts })}
                  </p>
                  {noCandidates ? (
                    <p className="mt-2 text-danger-primary">{t("work_item_types.ee.workspace.delete_no_candidates")}</p>
                  ) : (
                    <label className="mt-2 flex flex-col gap-1">
                      {t("work_item_types.ee.workspace.delete_migrate_to")}
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
                </>
              ) : (
                <p>{t("work_item_types.ee.workspace.delete_no_usage")}</p>
              )}
            </div>
          </DialogBody>
        </DialogMain>
        <DialogActions>
          <Button variant="secondary" size="md" stretch="auto" label={t("cancel")} onClick={onClose} />
          <Button
            variant="danger"
            size="md"
            stretch="auto"
            loading={busy}
            disabled={usage === null || (needsMigration && (noCandidates || !migrateTo))}
            label={t("work_item_types.settings.item_delete_confirmation.primary_button")}
            onClick={confirm}
          />
        </DialogActions>
      </DialogContent>
    </Dialog>
  );
}
