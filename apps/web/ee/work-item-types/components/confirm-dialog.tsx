/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
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
import { useTranslation } from "@plane/i18n";

type Props = {
  title: string;
  confirmLabel: string;
  busy?: boolean;
  danger?: boolean;
  onConfirm: () => void;
  onClose: () => void;
  children: ReactNode;
};

/** Small confirmation dialog; render it only while something is pending confirmation. */
export function ConfirmDialog({ title, confirmLabel, busy, danger, onConfirm, onClose, children }: Props) {
  const { t } = useTranslation();
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent size="sm">
        <DialogMain>
          <DialogHeader>
            <DialogHeading>
              <DialogTitle>{title}</DialogTitle>
            </DialogHeading>
          </DialogHeader>
          <DialogBody>{children}</DialogBody>
        </DialogMain>
        <DialogActions>
          <Button variant="secondary" size="md" stretch="auto" label={t("cancel")} onClick={onClose} />
          <Button
            variant={danger ? "danger" : "primary"}
            size="md"
            stretch="auto"
            loading={busy}
            label={confirmLabel}
            onClick={onConfirm}
          />
        </DialogActions>
      </DialogContent>
    </Dialog>
  );
}
