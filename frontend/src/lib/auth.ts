export interface AuthenticatedUser {
  id: number;
  email: string;
  username: string;
  auth_provider: string;
  is_active: boolean;
  is_superuser: boolean;
}

export function sanitizeNextPath(
  nextPath: string | null | undefined,
  fallback: string,
): string {
  if (!nextPath) {
    return fallback;
  }
  if (!nextPath.startsWith("/") || nextPath.startsWith("//")) {
    return fallback;
  }
  return nextPath;
}

export function getPostAuthDestination(
  user: AuthenticatedUser,
  nextPath: string,
): string {
  void user;
  return nextPath;
}
