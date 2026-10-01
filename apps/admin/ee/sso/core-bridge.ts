/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type {
  IFormattedInstanceConfiguration,
  TInstanceAuthenticationMethodKeys,
  TInstanceAuthenticationModeKeys,
} from "@plane/types";

// Core types its instance-config keys as a closed union. The EE_SSO_* keys are created at runtime by the
// backend plugin (they are plain rows in the same table), so the unavoidable casts live here and nowhere else.

export const readConfig = (config: IFormattedInstanceConfiguration | undefined, key: string): string =>
  (config as unknown as Record<string, string | undefined> | undefined)?.[key] ?? "";

/** True when the key exists at all (readConfig cannot tell "missing" from "empty"): false means the API plugin
 *  is not enabled or migrations have not seeded the EE_SSO_* rows yet. */
export const hasConfigKey = (config: IFormattedInstanceConfiguration | undefined, key: string): boolean =>
  !!config && Object.prototype.hasOwnProperty.call(config, key);

export const toConfigPayload = (payload: Record<string, string>): Partial<IFormattedInstanceConfiguration> =>
  payload as unknown as Partial<IFormattedInstanceConfiguration>;

export const asMethodKey = (key: string): TInstanceAuthenticationMethodKeys => key as TInstanceAuthenticationMethodKeys;

export const asModeKey = (key: string): TInstanceAuthenticationModeKeys => key as TInstanceAuthenticationModeKeys;
