/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TFilterValue } from "../expression";
import type {
  TDateFilterFieldConfig,
  TNumberFilterFieldConfig,
  TNumberRangeFilterFieldConfig,
  TSingleSelectFilterFieldConfig,
  TTextFilterFieldConfig,
} from "../field-types";
import type { EXTENDED_COMPARISON_OPERATOR, EXTENDED_EQUALITY_OPERATOR } from "../operators";

// ----------------------------- EXACT Operator -----------------------------
export type TExtendedExactOperatorConfigs =
  | TTextFilterFieldConfig<TFilterValue>
  | TNumberFilterFieldConfig<TFilterValue>;

// ----------------------------- IN Operator -----------------------------
export type TExtendedInOperatorConfigs = never;

// ----------------------------- RANGE Operator -----------------------------
export type TExtendedRangeOperatorConfigs = TNumberRangeFilterFieldConfig<TFilterValue>;

// ----------------------------- Extended Operator Specific Configs -----------------------------
export type TExtendedOperatorSpecificConfigs = {
  [EXTENDED_EQUALITY_OPERATOR.ICONTAINS]: TTextFilterFieldConfig<TFilterValue>;
  [EXTENDED_EQUALITY_OPERATOR.ISNULL]: TSingleSelectFilterFieldConfig<TFilterValue>;
  [EXTENDED_COMPARISON_OPERATOR.GTE]: TNumberFilterFieldConfig<TFilterValue> | TDateFilterFieldConfig<TFilterValue>;
  [EXTENDED_COMPARISON_OPERATOR.LTE]: TNumberFilterFieldConfig<TFilterValue> | TDateFilterFieldConfig<TFilterValue>;
};
