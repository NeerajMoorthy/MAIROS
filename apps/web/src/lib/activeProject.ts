/**
 * The project the sidebar's project-scoped links (Workspace, Patents,
 * Knowledge Graph) open when you are not already inside one.
 *
 * Remembered in localStorage, which may be unavailable (private windows,
 * blocked storage), so every access is guarded and failure just means
 * "no remembered project".
 */

const KEY = "mairos:last-project-id";

export function getActiveProjectId(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function setActiveProjectId(projectId: string): void {
  try {
    localStorage.setItem(KEY, projectId);
  } catch {
    /* storage unavailable: nothing to remember */
  }
}

/** Forget the project — but only if it is the one remembered. */
export function forgetActiveProjectId(projectId: string): void {
  try {
    if (localStorage.getItem(KEY) === projectId) localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable */
  }
}

/** Forget whichever project is remembered (after the workspace is cleared). */
export function clearActiveProjectId(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable */
  }
}
