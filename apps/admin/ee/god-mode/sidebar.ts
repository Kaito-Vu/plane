import { LockOutline, MailOutline } from "@makeplane/propel/icons";
import type { TSidebarMenuItem } from "@/hooks/use-sidebar-menu/types";

export const adminAccessMenuItem: TSidebarMenuItem = {
  Icon: LockOutline,
  name: "Admin access",
  description: "Control who can access God Mode.",
  href: `/admin-access/`,
};

export const externalInvitesMenuItem: TSidebarMenuItem = {
  Icon: MailOutline,
  name: "External invitations",
  description: "Allow or block email invitations.",
  href: `/external-invites/`,
};
