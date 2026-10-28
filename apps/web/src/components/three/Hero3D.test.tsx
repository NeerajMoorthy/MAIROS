import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const reducedMotion = vi.hoisted(() => ({ value: false }));

vi.mock("framer-motion", async (importOriginal) => ({
  ...(await importOriginal<typeof import("framer-motion")>()),
  useReducedMotion: () => reducedMotion.value,
}));

// The real scene needs WebGL, which jsdom lacks; a marker stands in for it.
vi.mock("next/dynamic", () => ({
  default: () =>
    function SceneStub({ active }: { active: boolean }) {
      return <div data-testid="scene" data-active={String(active)} />;
    },
}));

import { Hero3D, supportsWebGL } from "./Hero3D";

function fakeWebGL() {
  return vi
    .spyOn(HTMLCanvasElement.prototype, "getContext")
    .mockImplementation(((type: string) => (type.startsWith("webgl") ? {} : null)) as never);
}

describe("Hero3D", () => {
  afterEach(() => {
    reducedMotion.value = false;
    vi.restoreAllMocks();
  });

  it("renders nothing when WebGL is unavailable", () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    render(<Hero3D />);
    expect(screen.getByTestId("hero-3d")).toHaveAttribute("data-state", "off");
    expect(screen.queryByTestId("scene")).not.toBeInTheDocument();
  });

  it("renders the scene when WebGL is available", () => {
    fakeWebGL();
    expect(supportsWebGL()).toBe(true);
    render(<Hero3D />);
    expect(screen.getByTestId("hero-3d")).toHaveAttribute("data-state", "on");
    expect(screen.getByTestId("scene")).toBeInTheDocument();
  });

  it("skips the scene for users who prefer reduced motion", () => {
    fakeWebGL();
    reducedMotion.value = true;
    render(<Hero3D />);
    expect(screen.getByTestId("hero-3d")).toHaveAttribute("data-state", "off");
    expect(screen.queryByTestId("scene")).not.toBeInTheDocument();
  });

  it("is hidden from assistive technology", () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    render(<Hero3D />);
    expect(screen.getByTestId("hero-3d")).toHaveAttribute("aria-hidden", "true");
  });
});
