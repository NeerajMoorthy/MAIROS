"use client";

/** Better Auth — browser side. Same origin, so no base URL is needed. */

import { createAuthClient } from "better-auth/react";

import { clearApiToken } from "@/lib/authToken";

export const authClient = createAuthClient();

export async function signOut(): Promise<void> {
  clearApiToken();
  await authClient.signOut();
  window.location.assign("/sign-in");
}
