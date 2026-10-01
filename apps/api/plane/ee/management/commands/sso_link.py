# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.core.management.base import BaseCommand, CommandError

from plane.db.models import Account, User
from plane.ee.sso.config import GUID_RE, PROVIDER_IDS
from plane.ee.sso.identity import subject_key


def _key(provider, subject):
    if provider == "azure_ad":
        tenant, _, oid = subject.strip().lower().partition(":")
        if not GUID_RE.fullmatch(tenant) or not oid:
            raise CommandError("azure_ad subject must be <tenant-guid>:<object-id>")
        return f"{tenant}:{oid}"
    # `sub` may itself contain pipes (Auth0: `auth0|123`); issuers / entity ids / URLs never do
    issuer, _, sub = subject.partition("|")
    if not issuer or not sub:
        raise CommandError("subject must be <issuer / token URL / IdP entity id>|<subject>")
    try:
        return subject_key(issuer, sub)
    except Exception as e:
        raise CommandError(str(e))


class Command(BaseCommand):
    help = "Link (or --unlink) an EXISTING Plane user to an SSO subject. E-mail is never used to link automatically."

    def add_arguments(self, parser):
        parser.add_argument("--provider", required=True, choices=PROVIDER_IDS)
        parser.add_argument("--email", required=True, help="e-mail of the existing Plane user")
        parser.add_argument(
            "--subject",
            required=True,
            help=(
                "azure_ad: <tenant-guid>:<oid>; oidc: <issuer>|<sub>; oauth2: <token URL>|<id>; "
                "saml: <IdP entity id>|<NameID>"
            ),
        )
        parser.add_argument("--unlink", action="store_true")
        parser.add_argument(
            "--move",
            action="store_true",
            help="re-point a subject that is already linked to another (e.g. auto-created) user",
        )

    def handle(self, *args, provider, email, subject, unlink=False, move=False, **options):
        user = User.objects.filter(email=email.strip().lower()).first()
        if user is None:
            raise CommandError(f"no Plane user with e-mail {email}")
        name, key = f"sso-{provider}", _key(provider, subject)
        if unlink:
            deleted, _ = Account.objects.filter(user=user, provider=name, provider_account_id=key).delete()
            self.stdout.write(self.style.SUCCESS("unlinked" if deleted else "nothing to unlink"))
            return
        account, created = Account.objects.get_or_create(
            provider=name, provider_account_id=key, defaults={"user": user, "access_token": ""}
        )
        if account.user_id != user.id:
            if not move:
                raise CommandError(
                    "that subject is already linked to a different Plane user (it logged in before being linked? "
                    "use --move to re-point it)"
                )
            account.user = user
            account.save(update_fields=["user"])
            created = None
        self.stdout.write(self.style.SUCCESS("moved" if created is None else "linked" if created else "already linked"))
