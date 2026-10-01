# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES

EE_SSO_ERROR_CODES = {
    "SSO_NOT_CONFIGURED": 6000,
    "SSO_PROVIDER_ERROR": 6001,
}

# Register into the core dict so AuthenticationException lookups work unchanged.
AUTHENTICATION_ERROR_CODES.update(EE_SSO_ERROR_CODES)
