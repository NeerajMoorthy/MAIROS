"use client";

import { Suspense, useId, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AlertCircle, BrainCircuit, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { authClient } from "@/lib/auth-client";
import { AUTH_ENABLED, SOCIAL_PROVIDERS } from "@/lib/config";

/** Only same-site paths may be returned to after sign-in — never a full URL. */
function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return "/";
  return raw;
}

function SignInForm() {
  const uid = useId();
  const next = safeNext(useSearchParams().get("next"));
  const [mode, setMode] = useState<"sign-in" | "sign-up">("sign-in");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const result =
      mode === "sign-in"
        ? await authClient.signIn.email({ email, password })
        : await authClient.signUp.email({ email, password, name: name.trim() || email.split("@")[0] });
    if (result.error) {
      setError(result.error.message || "That did not work. Check your details and try again.");
      setPending(false);
      return;
    }
    window.location.assign(next);
  }

  async function social(provider: "github" | "google") {
    setPending(true);
    setError(null);
    const result = await authClient.signIn.social({ provider, callbackURL: next });
    if (result?.error) {
      setError(result.error.message || "Sign-in with that provider failed.");
      setPending(false);
    }
  }

  const id = (key: string) => `${uid}-${key}`;

  return (
    <Card className="w-full max-w-sm border-frozen/25 bg-black-iris/85 backdrop-blur-xl">
      <CardHeader className="space-y-3">
        <div className="flex items-center gap-2">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-frozen/30 text-frozen">
            <BrainCircuit className="h-5 w-5" aria-hidden="true" />
          </span>
          <span className="text-sm font-semibold tracking-wide">MAIROS</span>
        </div>
        <CardTitle className="text-xl">
          <h1>{mode === "sign-in" ? "Sign in" : "Create an account"}</h1>
        </CardTitle>
        <CardDescription>
          Your projects, documents and agent runs are private to your account.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <p role="alert" className="flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-2.5 text-sm">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden="true" />
            {error}
          </p>
        )}

        <form onSubmit={submit} className="space-y-3">
          {mode === "sign-up" && (
            <div className="space-y-1">
              <label htmlFor={id("name")} className="text-sm font-medium">
                Name
              </label>
              <Input id={id("name")} value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" disabled={pending} />
            </div>
          )}
          <div className="space-y-1">
            <label htmlFor={id("email")} className="text-sm font-medium">
              Email
            </label>
            <Input
              id={id("email")}
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
              disabled={pending}
            />
          </div>
          <div className="space-y-1">
            <label htmlFor={id("password")} className="text-sm font-medium">
              Password
            </label>
            <Input
              id={id("password")}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "sign-in" ? "current-password" : "new-password"}
              minLength={mode === "sign-up" ? 10 : undefined}
              required
              disabled={pending}
              aria-describedby={mode === "sign-up" ? id("password-hint") : undefined}
            />
            {mode === "sign-up" && (
              <p id={id("password-hint")} className="text-xs text-muted-foreground">
                At least 10 characters.
              </p>
            )}
          </div>
          <Button type="submit" className="w-full" disabled={pending}>
            {pending && <Loader2 className="animate-spin" />}
            {mode === "sign-in" ? "Sign in" : "Create account"}
          </Button>
        </form>

        {SOCIAL_PROVIDERS.length > 0 && (
          <div className="space-y-2">
            <p className="text-center text-xs text-muted-foreground">or continue with</p>
            {SOCIAL_PROVIDERS.map((provider) => (
              <Button
                key={provider}
                variant="outline"
                className="w-full capitalize"
                disabled={pending}
                onClick={() => void social(provider)}
              >
                {provider}
              </Button>
            ))}
          </div>
        )}

        <p className="text-center text-sm text-muted-foreground">
          {mode === "sign-in" ? "New to MAIROS?" : "Already have an account?"}{" "}
          <button
            type="button"
            className="focus-ring rounded-sm font-medium text-primary hover:underline"
            onClick={() => {
              setMode(mode === "sign-in" ? "sign-up" : "sign-in");
              setError(null);
            }}
          >
            {mode === "sign-in" ? "Create an account" : "Sign in instead"}
          </button>
        </p>
      </CardContent>
    </Card>
  );
}

export default function SignInPage() {
  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      {AUTH_ENABLED ? (
        <Suspense fallback={null}>
          <SignInForm />
        </Suspense>
      ) : (
        <Card className="max-w-sm">
          <CardHeader>
            <CardTitle>
              <h1>Sign-in is not enabled</h1>
            </CardTitle>
            <CardDescription>
              This MAIROS runs in local single-user mode, so there is nothing to sign in to.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild>
              <Link href="/">Go to your projects</Link>
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
