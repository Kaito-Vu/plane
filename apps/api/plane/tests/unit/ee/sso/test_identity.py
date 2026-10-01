# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest
from django.test import RequestFactory
from django.utils import timezone

from plane.authentication.adapter.base import Adapter
from plane.authentication.adapter.error import AuthenticationException
from plane.db.models import Account, Profile
from plane.ee.sso.identity import SubjectLoginMixin, placeholder_email, subject_key
from plane.license.models import InstanceConfiguration


class _Provider(SubjectLoginMixin, Adapter):
    pass


def _provider(callback=None):
    request = RequestFactory().get("/")
    request.META["HTTP_USER_AGENT"] = "pytest"
    return _Provider(request, "sso-test", callback)


PROFILE = {"first_name": "An", "last_name": "Nguyen", "display_name": "An Nguyen"}
KEY = subject_key("https://idp.example.com", "sub-1")


@pytest.mark.unit
def test_subject_key_is_namespaced_by_issuer():
    assert subject_key("https://a", "1") != subject_key("https://b", "1")
    assert subject_key("https://a", "1") == subject_key("https://a", "1")
    assert subject_key("https://a/", "1") == subject_key("https://a", "1")


@pytest.mark.unit
@pytest.mark.parametrize("subject", ["", None, "x" * 300])
def test_subject_key_rejects_empty_or_oversized(subject):
    with pytest.raises(AuthenticationException):
        subject_key("https://a", subject)


@pytest.mark.unit
def test_placeholder_email_is_reserved_and_deterministic():
    email = placeholder_email("sso-test", KEY)
    assert email.endswith("@sso.invalid")
    assert email == placeholder_email("sso-test", KEY)


@pytest.mark.unit
@pytest.mark.django_db
def test_first_login_provisions_user_account_profile_and_runs_workflow(mocker):
    callback = mocker.Mock()
    user = _provider(callback).login_by_subject(KEY, PROFILE, "1")
    assert user.email == placeholder_email("sso-test", KEY)
    assert (user.first_name, user.last_name) == ("An", "Nguyen")
    assert Account.objects.get(user=user).provider_account_id == KEY
    assert Profile.objects.filter(user=user).exists()
    assert not user.has_usable_password() or user.is_password_autoset
    assert callback.call_args.args[1] is True  # is_signup


@pytest.mark.unit
@pytest.mark.django_db
def test_second_login_reuses_the_user_even_with_signup_off(mocker):
    first = _provider().login_by_subject(KEY, PROFILE, "1")
    callback = mocker.Mock()
    second = _provider(callback).login_by_subject(KEY, {}, "0")
    assert second.id == first.id
    assert Account.objects.count() == 1
    assert callback.call_args.args[1] is False


@pytest.mark.unit
@pytest.mark.django_db
def test_signup_off_blocks_unknown_subjects():
    with pytest.raises(AuthenticationException) as exc:
        _provider().login_by_subject(KEY, PROFILE, "0")
    assert exc.value.error_code == 5015
    assert Account.objects.count() == 0


@pytest.mark.unit
@pytest.mark.django_db
def test_instance_wide_signup_off_blocks_unknown_subjects():
    InstanceConfiguration.objects.create(key="ENABLE_SIGNUP", value="0", category="AUTHENTICATION")
    with pytest.raises(AuthenticationException) as exc:
        _provider().login_by_subject(KEY, PROFILE, "1")
    assert exc.value.error_code == 5015


@pytest.mark.unit
@pytest.mark.django_db
def test_login_after_the_link_was_removed_reuses_the_placeholder_user():
    first = _provider().login_by_subject(KEY, PROFILE, "1")
    Account.objects.all().delete()  # e.g. `sso_link --unlink`
    assert _provider().login_by_subject(KEY, PROFILE, "1").id == first.id
    assert Account.objects.count() == 1


@pytest.mark.unit
@pytest.mark.django_db
def test_deactivated_and_bot_users_are_rejected():
    user = _provider().login_by_subject(KEY, PROFILE, "1")
    user.is_active, user.last_logout_time = False, timezone.now()
    user.save()
    with pytest.raises(AuthenticationException) as exc:
        _provider().login_by_subject(KEY, PROFILE, "1")
    assert exc.value.error_code == 5019
    user.is_active, user.last_logout_time, user.is_bot = True, None, True
    user.save()
    with pytest.raises(AuthenticationException) as exc:
        _provider().login_by_subject(KEY, PROFILE, "1")
    assert exc.value.error_code == 5017
