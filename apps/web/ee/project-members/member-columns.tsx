// Allocation (start/end date) and Remove columns for the project Members table. Builds on the core columns
// (useProjectColumns) instead of editing them: the name cell is swapped for one without the hover menu, and
// the date and Actions columns are appended.
import Link from "next/link";
import useSWR from "swr";
import { Avatar } from "@makeplane/propel/components/avatar";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@makeplane/propel/components/menu";
import { MoreHorizontalOutline, UserMinusOutline } from "@makeplane/propel/icons";
import { setToast } from "@plane/blocks/toast";
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { getFileURL, renderFormattedDate } from "@plane/utils";
// hooks
import { useMember } from "@/hooks/store/use-member";
import { useUser, useUserPermissions } from "@/hooks/store/user";
// core columns
import { useProjectColumns } from "@/components/projects/settings/useProjectColumns";
import type { RowData } from "@/components/projects/settings/useProjectColumns";
// local
import { projectMemberAllocationService } from "./services/project-member-allocation.service";
import type { TAllocationMap } from "./services/project-member-allocation.service";

type TProps = { projectId: string; workspaceSlug: string };

const today = () => new Date().toLocaleDateString("sv-SE");

export const useEeProjectColumns = ({ projectId, workspaceSlug }: TProps) => {
  const core = useProjectColumns({ projectId, workspaceSlug });
  const { t } = useTranslation();
  const { data: currentUser } = useUser();
  const { allowPermissions } = useUserPermissions();
  const {
    project: { getProjectMemberDetails },
  } = useMember();
  const isAdmin = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.PROJECT, workspaceSlug, projectId);

  const { data: allocations, mutate } = useSWR<TAllocationMap>(
    `PROJECT_MEMBER_ALLOCATIONS_${workspaceSlug}_${projectId}`,
    () => projectMemberAllocationService.list(workspaceSlug, projectId)
  );

  const nameColumn = (rowData: RowData) => {
    const { avatar_url, display_name, email, first_name, id, last_name } = rowData.member;
    return (
      <div className="flex w-72 min-w-0 items-center gap-2">
        <Link href={`/${workspaceSlug}/profile/${id}`} className="flex shrink-0">
          <Avatar size="sm" src={getFileURL(avatar_url ?? "")} alt={display_name || email} />
        </Link>
        <span className="truncate">
          {first_name} {last_name}
        </span>
      </div>
    );
  };

  const dateColumn = (rowData: RowData, field: "start_date" | "end_date") => {
    const projectMemberId = getProjectMemberDetails(rowData.member.id, projectId)?.id;
    const value = (projectMemberId && allocations?.[projectMemberId]?.[field]) || "";
    // informational: an ended allocation does not revoke access, an admin removes the member
    const ended = field === "end_date" && !!value && value < today();
    if (!isAdmin || !projectMemberId)
      return (
        <div className="w-32">
          {value ? renderFormattedDate(value) : "—"}
          {ended && <span className="ml-2 text-danger-primary">Ended</span>}
        </div>
      );
    const other = allocations?.[projectMemberId]?.[field === "end_date" ? "start_date" : "end_date"];
    return (
      <div className="flex w-44 items-center gap-2">
        <input
          type="date"
          key={value}
          defaultValue={value}
          min={field === "end_date" ? (other ?? undefined) : undefined}
          max={field === "start_date" ? (other ?? undefined) : undefined}
          aria-label={field === "start_date" ? "Start date" : "End date"}
          className="rounded-md border border-subtle bg-layer-2 px-2 py-1"
          onChange={(e) => {
            const next = e.target.value || null;
            projectMemberAllocationService
              .update(workspaceSlug, projectId, projectMemberId, { [field]: next })
              .then(() => mutate())
              .catch((err) =>
                setToast({
                  type: "error",
                  title: "You can’t change this date yet.",
                  message: err?.error ?? "Something went wrong. Please try again.",
                })
              );
          }}
        />
        {ended && <span className="text-danger-primary">Ended</span>}
      </div>
    );
  };

  const actionsColumn = (rowData: RowData) => {
    const isSelf = rowData.member.id === currentUser?.id;
    if (!isAdmin && !isSelf) return null;
    return (
      <div className="flex justify-end">
        <Menu>
          <MenuTrigger
            render={
              <IconButton
                variant="secondary"
                size="md"
                aria-label={t("aria_labels.common.more_actions")}
                icon={<Icon icon={MoreHorizontalOutline} />}
              />
            }
          />
          <MenuContent side="bottom" align="end">
            <MenuItem
              variant="danger"
              icon={<Icon icon={UserMinusOutline} />}
              label={isSelf ? t("leave") : t("remove")}
              onClick={() => core.setRemoveMemberModal(rowData)}
            />
          </MenuContent>
        </Menu>
      </div>
    );
  };

  const columns = [
    ...core.columns.map((column) => (column.key === "Full Name" ? { ...column, tdRender: nameColumn } : column)),
    { key: "Start Date", content: "Start date", tdRender: (row: RowData) => dateColumn(row, "start_date") },
    { key: "End Date", content: "End date", tdRender: (row: RowData) => dateColumn(row, "end_date") },
    { key: "Actions", content: "", tdRender: actionsColumn },
  ];

  return { columns, removeMemberModal: core.removeMemberModal, setRemoveMemberModal: core.setRemoveMemberModal };
};
