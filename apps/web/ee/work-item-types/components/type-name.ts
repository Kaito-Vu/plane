/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback } from "react";
import { useTranslation } from "@plane/i18n";
import type { TIssueType } from "@plane/types";
import { presetLabelKey } from "../rules";

/** Presets still carrying their seeded name are translated by external_id; renamed presets and custom types show their name verbatim. */
export function useTypeName() {
  const { t } = useTranslation();
  return useCallback(
    (type: Pick<TIssueType, "name" | "is_preset" | "external_id" | "is_active">) => {
      const key = presetLabelKey(type);
      const name = key ? t(key) : type.name;
      return type.is_active ? name : `${name} (${t("work_item_types.ee.disabled_suffix")})`;
    },
    [t]
  );
}
