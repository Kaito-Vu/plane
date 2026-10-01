# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from urllib.parse import urlencode, urljoin

from django.http import HttpResponseRedirect

from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES, AuthenticationException
from plane.authentication.utils.login import user_login
from plane.authentication.utils.redirection_path import get_redirection_path
from plane.ee.sso import errors  # noqa: F401
from plane.utils.path_validator import validate_next_path


def redirect_error(host, exc, next_path=None):
    params = exc.get_error_dict()
    if next_path:
        params["next_path"] = str(validate_next_path(next_path))
    return HttpResponseRedirect(urljoin(host, "?" + urlencode(params)))


def provider_error(message="SSO_PROVIDER_ERROR"):
    return AuthenticationException(error_code=AUTHENTICATION_ERROR_CODES["SSO_PROVIDER_ERROR"], error_message=message)


def complete_login(request, user, host, next_path):
    """Log the user in and redirect into the app (Phase 3 adds the space target here)."""
    user_login(request=request, user=user, is_app=True)
    path = str(validate_next_path(next_path)) if next_path else get_redirection_path(user=user)
    return HttpResponseRedirect(urljoin(host, path))
