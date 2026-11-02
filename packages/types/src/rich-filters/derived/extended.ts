/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TFilterValue } from "../expression";
import type { EXTENDED_COMPARISON_OPERATOR } from "../operators";

// -------- DATE FILTER OPERATORS --------

/**
 * Union type representing all extended operators that support date filter types.
 */
// EE: gte/lte on date attributes
export type TExtendedSupportedDateFilterOperators<_V extends TFilterValue = TFilterValue> =
  | typeof EXTENDED_COMPARISON_OPERATOR.GTE
  | typeof EXTENDED_COMPARISON_OPERATOR.LTE;

export type TExtendedAllAvailableDateFilterOperatorsForDisplay<V extends TFilterValue = TFilterValue> =
  TExtendedSupportedDateFilterOperators<V>;

// -------- SELECT FILTER OPERATORS --------

/**
 * Union type representing all extended operators that support select filter types.
 */
export type TExtendedSupportedSelectFilterOperators<_V extends TFilterValue = TFilterValue> = never;

export type TExtendedAllAvailableSelectFilterOperatorsForDisplay<_V extends TFilterValue = TFilterValue> = never;
