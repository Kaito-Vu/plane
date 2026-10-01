# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.core.management.base import BaseCommand, CommandError

from plane.db.models import Account, Workspace, WorkspaceMember
from plane.ee.management.commands.sso_link import _key
from plane.ee.sso.config import PROVIDER_IDS


class Command(BaseCommand):
    help = "Add the Plane user behind an SSO subject to a workspace (e-mail invitations cannot reach SSO users)."

    def add_arguments(self, parser):
        parser.add_argument("--provider", required=True, choices=PROVIDER_IDS)
        parser.add_argument("--subject", required=True, help="same format as sso_link")
        parser.add_argument("--workspace", required=True, help="workspace slug")
        parser.add_argument("--role", type=int, choices=[5, 15, 20], default=15, help="5 guest, 15 member, 20 admin")

    def handle(self, *args, provider, subject, workspace, role=15, **options):
        account = (
            Account.objects.select_related("user")
            .filter(provider=f"sso-{provider}", provider_account_id=_key(provider, subject))
            .first()
        )
        if account is None:
            raise CommandError("no user has logged in or been linked with that subject yet")
        target = Workspace.objects.filter(slug=workspace).first()
        if target is None:
            raise CommandError(f"no workspace with slug {workspace}")
        member, created = WorkspaceMember.objects.get_or_create(
            workspace=target, member=account.user, defaults={"role": role}
        )
        if not created and member.role != role:
            member.role = role
            member.save(update_fields=["role"])
        self.stdout.write(self.style.SUCCESS("added" if created else "already a member (role updated if it differed)"))
