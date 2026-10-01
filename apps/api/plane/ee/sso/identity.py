# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import hashlib
import os
import uuid

from django.db import IntegrityError, transaction
from django.utils import timezone

from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES, AuthenticationException
from plane.db.models import Account, Profile, User
from plane.ee.sso.flow import provider_error
from plane.license.utils.instance_value import get_configuration_value

# RFC 2606 reserved TLD: can never be a real mailbox (see the Task 4 decision text).
PLACEHOLDER_DOMAIN = "sso.invalid"


def issuer_fingerprint(issuer):
    # a trailing "/" is not significant (Auth0 publishes it, admins often omit it)
    return hashlib.sha256(issuer.rstrip("/").encode()).hexdigest()[:12]


def subject_key(issuer, subject):
    """`sub` is only unique per issuer (OIDC Core 2): namespace it. Never built from an e-mail."""
    subject = "" if subject is None else str(subject)
    key = f"{issuer_fingerprint(issuer)}:{subject}"
    if not subject or len(key) > 255:  # Account.provider_account_id is 255 chars
        raise provider_error("SSO_PROVIDER_ERROR: missing or oversized subject")
    return key


def placeholder_email(provider, key):
    return f"{hashlib.sha256(f'{provider}|{key}'.encode()).hexdigest()[:32]}@{PLACEHOLDER_DOMAIN}"


def _clip(value):
    return str(value or "").strip()[:255]


def _reject(code):
    return AuthenticationException(error_code=AUTHENTICATION_ERROR_CODES[code], error_message=code)


class SubjectLoginMixin:
    """For core `Adapter` subclasses: log in through (provider, stable subject), never through e-mail."""

    def login_by_subject(self, key, profile, allow_signup):
        account = Account.objects.select_related("user").filter(provider=self.provider, provider_account_id=key).first()
        is_signup = account is None
        if account is not None:
            user = account.user
        else:
            self._check_signup(allow_signup)
            try:
                with transaction.atomic():
                    user = self._provision(key, profile)
                    Account.objects.create(user=user, provider=self.provider, provider_account_id=key, access_token="")
            except IntegrityError:
                # concurrent first login for the same subject (the other request won), or a placeholder user whose
                # link was removed (`sso_link --unlink`): re-use that user and (re)create the link
                account = (
                    Account.objects.select_related("user")
                    .filter(provider=self.provider, provider_account_id=key)
                    .first()
                )
                user = account.user if account else User.objects.get(email=placeholder_email(self.provider, key))
                if account is None:
                    Account.objects.get_or_create(
                        provider=self.provider, provider_account_id=key, defaults={"user": user, "access_token": ""}
                    )
                is_signup = False
        if not user.is_active and user.last_logout_time is not None:
            raise _reject("USER_ACCOUNT_DEACTIVATED")  # explicitly deactivated (same rule as core)
        if user.is_bot:
            raise _reject("BOT_USER_LOGIN_FORBIDDEN")
        Account.objects.filter(provider=self.provider, provider_account_id=key).update(last_connected_at=timezone.now())
        user = self.save_user_data(user)
        if self.callback:
            self.callback(user, is_signup, self.request)
        return user

    def _check_signup(self, allow_signup):
        (enable_signup,) = get_configuration_value(
            [{"key": "ENABLE_SIGNUP", "default": os.environ.get("ENABLE_SIGNUP", "1")}]
        )
        if allow_signup != "1" or enable_signup == "0":
            raise _reject("SIGNUP_DISABLED")

    def _provision(self, key, profile):
        email = placeholder_email(self.provider, key)
        user = User(
            email=email,
            username=uuid.uuid4().hex,
            first_name=_clip(profile.get("first_name")),
            last_name=_clip(profile.get("last_name")),
            display_name=_clip(profile.get("display_name")) or email.split("@")[0][:12],
        )
        user.set_password(uuid.uuid4().hex)
        user.is_password_autoset = True
        user.is_email_verified = False  # the placeholder is not a mailbox
        user.save()
        Profile.objects.create(user=user)
        return user
