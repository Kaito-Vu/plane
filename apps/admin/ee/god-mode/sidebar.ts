import { LockOutline } from "@makeplane/propel/icons";
import type { TSidebarMenuItem } from "@/hooks/use-sidebar-menu/types";

export const adminAccessMenuItem: TSidebarMenuItem = {
  Icon: LockOutline,
  name: "Admin access",
  description: "Control who can access God Mode.",
  href: `/admin-access/`,
};
