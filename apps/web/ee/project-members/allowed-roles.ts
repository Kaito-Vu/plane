// Mirrors the backend rules for POST project members (ee views + core): role 20 needs a workspace Admin requester,
// never above the requester's own project role, a workspace Admin target can only be project Admin, a workspace
// Guest target can only be project Guest. Workspace role null/15 (provisioned by the backend) allows any role.
const ADMIN = 20;
const MEMBER = 15;
const GUEST = 5;

export const allowedRoles = (args: {
  requesterProjectRole: number | undefined;
  requesterIsWorkspaceAdmin: boolean;
  targetWorkspaceRole: number | null | undefined;
}): number[] => {
  const { requesterProjectRole, requesterIsWorkspaceAdmin, targetWorkspaceRole } = args;
  let roles = [ADMIN, MEMBER, GUEST].filter((r) => r <= (requesterProjectRole ?? GUEST));
  if (!requesterIsWorkspaceAdmin) roles = roles.filter((r) => r !== ADMIN);
  if (targetWorkspaceRole === ADMIN) roles = roles.filter((r) => r === ADMIN);
  else if (targetWorkspaceRole === GUEST) roles = roles.filter((r) => r === GUEST);
  return roles;
};

// Member when allowed, else the highest allowed role; undefined when nothing is allowed.
export const defaultRole = (allowed: number[]): number | undefined =>
  allowed.includes(MEMBER) ? MEMBER : allowed.length ? Math.max(...allowed) : undefined;
