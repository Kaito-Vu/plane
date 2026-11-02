# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import os

# (key, default, is_encrypted)
_VARS = (
    ("IS_ENTRA_ENABLED", "0", False),
    ("ENTRA_TENANT_ID", None, False),
    ("ENTRA_CLIENT_ID", None, False),
    ("ENTRA_CLIENT_SECRET", None, True),
    ("ENTRA_PROVIDER_NAME", "Microsoft", False),
    ("ENTRA_ALLOWED_EMAIL_DOMAINS", "", False),
    ("ENABLE_ENTRA_SYNC", "0", False),
    ("SSO_ONLY_LOGIN_PAGE", "0", False),
)

ENTRA_CONFIG_KEYS = tuple(key for key, _, _ in _VARS)

entra_config_variables = [
    {"key": key, "value": os.environ.get(key, default), "category": "ENTRA", "is_encrypted": enc}
    for key, default, enc in _VARS
]
