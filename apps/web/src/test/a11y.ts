import axe from "axe-core";

/**
 * Run axe-core against a rendered container and return WCAG 2.1 AA violations.
 *
 * Only the rules that jsdom can actually decide are enabled. Colour contrast is
 * excluded here *not* because it does not matter but because jsdom does not lay
 * out or composite anything, so axe cannot read a real computed colour — the
 * contrast of every theme token is checked instead by
 * `tests/test_theme_contrast.py`, which computes the ratios from the stylesheet.
 */
export async function findViolations(container: HTMLElement) {
  const results = await axe.run(container, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] },
    rules: {
      "color-contrast": { enabled: false },
      // These assert page-level structure (one main landmark, a top-level h1,
      // and so on) that a single mounted component cannot satisfy on its own.
      region: { enabled: false },
      "page-has-heading-one": { enabled: false },
      "landmark-one-main": { enabled: false },
    },
  });

  return results.violations.map((violation) => ({
    id: violation.id,
    impact: violation.impact,
    help: violation.help,
    nodes: violation.nodes.map((node) => node.html.slice(0, 160)),
  }));
}

/** Assert a rendered container has no WCAG 2.1 AA violations axe can detect. */
export async function expectNoViolations(container: HTMLElement) {
  const violations = await findViolations(container);
  if (violations.length > 0) {
    throw new Error(
      "axe found WCAG 2.1 AA violations:\n" +
        violations
          .map((v) => `  [${v.impact}] ${v.id}: ${v.help}\n    ${v.nodes.join("\n    ")}`)
          .join("\n"),
    );
  }
}
