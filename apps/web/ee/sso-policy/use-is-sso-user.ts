/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { IUser } from "@plane/types";

// `is_sso_user` is added to /api/users/me/ by plane.ee.sso_policy; users who sign in through an
// identity provider cannot change their name or password.
export const isSsoUser = (user: IUser | undefined | null) =>
  !!(user as (IUser & { is_sso_user?: boolean }) | null)?.is_sso_user;
