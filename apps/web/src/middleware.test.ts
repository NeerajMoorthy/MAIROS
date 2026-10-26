import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { middleware } from "@/middleware";

const forwarded = (response: Response, name: string) =>
  response.headers.get(`x-middleware-request-${name}`);

describe("middleware", () => {
  it("adds ngrok's skip-warning header to proxied API calls", () => {
    const response = middleware(
      new NextRequest("https://mairos.vercel.app/api/projects", {
        headers: { "user-agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/130" },
      }),
    );

    expect(forwarded(response, "ngrok-skip-browser-warning")).toBe("1");
    // The visitor's own headers still reach the backend.
    expect(forwarded(response, "user-agent")).toContain("Mozilla/5.0");
  });

  it("leaves pages alone when sign-in is off", () => {
    const response = middleware(new NextRequest("https://mairos.vercel.app/projects/p1"));

    expect(forwarded(response, "ngrok-skip-browser-warning")).toBeNull();
  });
});
