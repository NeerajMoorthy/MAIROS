import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { TiltCard } from "./tilt-card";

describe("TiltCard", () => {
  it("renders its content and keeps it interactive", async () => {
    let clicks = 0;
    render(
      <TiltCard>
        <button type="button" onClick={() => clicks++}>
          Open workspace
        </button>
      </TiltCard>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Open workspace" }));
    expect(clicks).toBe(1);
  });

  it("hides the decorative glare from assistive technology", () => {
    const { container } = render(<TiltCard>content</TiltCard>);
    const glare = container.querySelector('[aria-hidden="true"]');
    expect(glare).not.toBeNull();
    expect(glare).toHaveClass("pointer-events-none");
  });
});
