/**
 * Entry point for the Better Auth CLI only (`npm run auth:migrate`), which
 * expects a module exporting `auth`. The app itself uses `getAuth()`.
 */
import { createAuth } from "./auth";

export const auth = createAuth();
