"use client";

import { LogOut, UserRound } from "lucide-react";

import { Button } from "@/components/ui/button";
import { authClient, signOut } from "@/lib/auth-client";

/** The signed-in user and a sign-out button. Rendered only when auth is enabled. */
export function UserMenu() {
  const { data, isPending } = authClient.useSession();
  const user = data?.user;

  return (
    <div className="flex items-center gap-2 rounded-lg border border-frozen/20 bg-black-iris/80 p-2 text-xs">
      <UserRound className="h-4 w-4 shrink-0 text-frozen" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-foreground">
          {isPending ? "Checking session…" : (user?.name || user?.email || "Signed out")}
        </p>
        {user?.email && user.name && <p className="truncate text-muted-foreground">{user.email}</p>}
      </div>
      {user && (
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 shrink-0"
          aria-label="Sign out"
          onClick={() => void signOut()}
        >
          <LogOut />
        </Button>
      )}
    </div>
  );
}

export default UserMenu;
