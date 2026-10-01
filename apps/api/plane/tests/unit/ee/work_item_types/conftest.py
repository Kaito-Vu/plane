# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest

from plane.db.models import Project, ProjectMember


@pytest.fixture
def project(db, workspace, create_user):
    p = Project.objects.create(name="P", identifier="P", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=p, member=create_user, workspace=workspace, role=20)
    return p
