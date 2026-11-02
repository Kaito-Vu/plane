from django.core.management.base import BaseCommand

from plane.db.models import Project, Workspace
from plane.ee.work_item_types.seed import seed_project, seed_workspace


class Command(BaseCommand):
    help = "Idempotently seed the 6 agile work item types into existing workspaces and projects"

    def add_arguments(self, parser):
        parser.add_argument("--workspace", help="Only seed the workspace with this slug")

    def handle(self, *args, **options):
        workspaces = Workspace.objects.all()
        if options["workspace"]:
            workspaces = workspaces.filter(slug=options["workspace"])
        for workspace in workspaces:
            seed_workspace(workspace)
            for project in Project.objects.filter(workspace=workspace):
                seed_project(project)
            self.stdout.write(f"Seeded work item types for workspace {workspace.slug}")
