/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Button } from "@makeplane/propel/components/button";
import { useTranslation } from "@plane/i18n";

export function SettingsLoader() {
  return (
    <div className="mt-6 flex animate-pulse flex-col gap-3" role="status" aria-busy="true">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="h-10 rounded-md bg-layer-2" />
      ))}
    </div>
  );
}

export function SettingsError({ onRetry }: { onRetry: () => void }) {
  const { t } = useTranslation();
  return (
    <div role="alert" className="mt-6 flex items-center gap-3 rounded-md border border-subtle p-4">
      <p className="flex-1 text-body-xs-regular">{t("work_item_types.ee.load_failed")}</p>
      <Button variant="secondary" size="sm" stretch="auto" label={t("work_item_types.ee.retry")} onClick={onRetry} />
    </div>
  );
}
