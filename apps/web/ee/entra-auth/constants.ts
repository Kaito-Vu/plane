/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

export const INTERNAL_LOGIN_PATH = "/login/internal";

export const isInternalLoginPath = (pathname: string): boolean =>
  pathname === INTERNAL_LOGIN_PATH || pathname === `${INTERNAL_LOGIN_PATH}/`;
