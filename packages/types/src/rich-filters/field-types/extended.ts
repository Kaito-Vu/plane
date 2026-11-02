/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TFilterValue } from "../expression";
import type { TBaseFilterFieldConfig } from "./shared";

/**
 * Extended filter types
 */
// EE work item types: free-text and number inputs for attribute filters
export const EXTENDED_FILTER_FIELD_TYPE = {
  TEXT: "text",
  NUMBER: "number",
  NUMBER_RANGE: "number_range",
} as const;

/** Free-text input (e.g. `icontains`). */
export type TTextFilterFieldConfig<V extends TFilterValue> = TBaseFilterFieldConfig & {
  type: typeof EXTENDED_FILTER_FIELD_TYPE.TEXT;
  defaultValue?: V;
};

/** Number input (exact / gte / lte). */
export type TNumberFilterFieldConfig<V extends TFilterValue> = TBaseFilterFieldConfig & {
  type: typeof EXTENDED_FILTER_FIELD_TYPE.NUMBER;
  defaultValue?: V;
};

/** Two number inputs (range). */
export type TNumberRangeFilterFieldConfig<V extends TFilterValue> = TBaseFilterFieldConfig & {
  type: typeof EXTENDED_FILTER_FIELD_TYPE.NUMBER_RANGE;
  defaultValue?: V[];
};

// -------- UNION TYPES --------

/**
 * All extended filter configurations
 */
export type TExtendedFilterFieldConfigs<V extends TFilterValue = TFilterValue> =
  | TTextFilterFieldConfig<V>
  | TNumberFilterFieldConfig<V>
  | TNumberRangeFilterFieldConfig<V>;
