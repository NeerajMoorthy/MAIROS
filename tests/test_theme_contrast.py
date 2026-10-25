"""WCAG AA contrast of the theme tokens, computed from the stylesheet itself.

axe-core cannot judge contrast under jsdom — nothing is laid out or
composited, so every computed colour comes back unresolved. That left the
palette unchecked: `text-success` sat at 3.31:1 on the page background and the
offline banner rendered at 1.12:1 in dark mode, both well under AA, and no test
in the suite could have noticed.

So the ratios are computed here instead, straight from `globals.css`. The OKLCH
values are converted to sRGB and scored with the WCAG 2.1 formula, with no
third-party colour library — the conversion is about forty lines and pinning it
here means the check has no dependency that could drift.

Each pair below corresponds to a real pairing in the components, named in its
comment. A failure is a genuine accessibility regression, not a style opinion.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

GLOBALS_CSS = (
    Path(__file__).resolve().parents[1] / "apps" / "web" / "src" / "app" / "globals.css"
)

# WCAG 2.1: 4.5:1 for text below 18.66px bold / 24px regular, 3:1 for larger
# text, icons and other non-text content that conveys meaning.
AA_TEXT = 4.5
AA_NON_TEXT = 3.0


# ---------------------------------------------------------------------------
# Colour maths
# ---------------------------------------------------------------------------
def oklch_to_srgb(lightness: float, chroma: float, hue_deg: float) -> tuple[float, float, float]:
    """Convert OKLCH to linear-light sRGB components (may fall outside 0-1)."""
    hue = math.radians(hue_deg)
    a = chroma * math.cos(hue)
    b = chroma * math.sin(hue)

    # OKLab -> LMS (cube of the intermediate), per Björn Ottosson's definition.
    l_ = lightness + 0.3963377774 * a + 0.2158037573 * b
    m_ = lightness - 0.1055613458 * a - 0.0638541728 * b
    s_ = lightness - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_**3, m_**3, s_**3

    return (
        +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    )


def relative_luminance(lightness: float, chroma: float, hue: float) -> float:
    """WCAG relative luminance. The sRGB values are already linear-light here."""
    r, g, b = (min(1.0, max(0.0, c)) for c in oklch_to_srgb(lightness, chroma, hue))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(first: tuple, second: tuple) -> float:
    """WCAG 2.1 contrast ratio between two OKLCH triples."""
    a, b = relative_luminance(*first), relative_luminance(*second)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


# ---------------------------------------------------------------------------
# Reading the stylesheet
# ---------------------------------------------------------------------------
_TOKEN = re.compile(r"--([a-z-]+):\s*oklch\(([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\)\s*;")


def _tokens() -> tuple[dict, dict]:
    """The light and dark token tables, parsed out of globals.css."""
    css = GLOBALS_CSS.read_text(encoding="utf-8")
    dark_start = css.index(".dark {")
    light_block, dark_block = css[:dark_start], css[dark_start:]

    def parse(block: str) -> dict:
        return {
            name: (float(l), float(c), float(h))
            for name, l, c, h in _TOKEN.findall(block)
        }

    light, dark = parse(light_block), parse(dark_block)
    # Dark mode only overrides some tokens; the rest are inherited from :root.
    return light, {**light, **dark}


LIGHT, DARK = _tokens()


def _pair(theme: dict, foreground: str, background: str) -> float:
    return contrast(theme[foreground], theme[background])


# ---------------------------------------------------------------------------
# The pairings the UI actually renders
# ---------------------------------------------------------------------------
# (foreground token, background token, minimum ratio, where it appears)
TEXT_PAIRS = [
    ("foreground", "background", AA_TEXT, "body copy"),
    ("foreground", "card", AA_TEXT, "card copy"),
    ("muted-foreground", "background", AA_TEXT, "secondary copy, citation quotes"),
    ("muted-foreground", "card", AA_TEXT, "secondary copy inside cards"),
    ("muted-foreground", "muted", AA_TEXT, "expanded citation passage on bg-muted"),
    ("muted-foreground", "sidebar", AA_TEXT, "sidebar subtitle"),
    ("foreground", "sidebar", AA_TEXT, "sidebar title"),
    ("secondary-foreground", "secondary", AA_TEXT, "secondary badge"),
    ("accent-foreground", "accent", AA_TEXT, "hovered nav item"),
    ("sidebar-accent-foreground", "sidebar-accent", AA_TEXT, "active nav item"),
    ("primary-foreground", "primary", AA_TEXT, "primary button"),
    ("destructive-foreground", "destructive", AA_TEXT, "destructive badge and button"),
    ("success-foreground", "success", AA_TEXT, "success badge"),
    ("warning-foreground", "warning", AA_TEXT, "warning badge"),
    # Semantic colours used directly as text, e.g. PipelineTrace's stage labels
    # and the error lines in SearchUpload / WorkflowPanel.
    ("primary", "background", AA_TEXT, "text-primary links and 'Show full passage'"),
    ("destructive", "background", AA_TEXT, "text-destructive error copy"),
    ("success", "background", AA_TEXT, "text-success stage label"),
]

# Icons and status dots: meaningful non-text content, so the 3:1 bar applies.
NON_TEXT_PAIRS = [
    ("warning", "background", AA_NON_TEXT, "warning icon on the evaluation page"),
    ("warning", "card", AA_NON_TEXT, "warning icon inside a card"),
    ("success", "card", AA_NON_TEXT, "success tick in SearchUpload"),
    ("ring", "background", AA_NON_TEXT, "focus ring"),
    ("ring", "card", AA_NON_TEXT, "focus ring over a card"),
]


@pytest.mark.parametrize("theme_name", ["light", "dark"])
@pytest.mark.parametrize("foreground,background,minimum,usage", TEXT_PAIRS)
def test_text_pairs_meet_aa(theme_name, foreground, background, minimum, usage):
    theme = LIGHT if theme_name == "light" else DARK
    ratio = _pair(theme, foreground, background)
    assert ratio >= minimum, (
        f"{theme_name}: {foreground} on {background} is {ratio:.2f}:1, "
        f"below the {minimum}:1 needed for {usage}"
    )


@pytest.mark.parametrize("theme_name", ["light", "dark"])
@pytest.mark.parametrize("foreground,background,minimum,usage", NON_TEXT_PAIRS)
def test_non_text_pairs_meet_aa(theme_name, foreground, background, minimum, usage):
    theme = LIGHT if theme_name == "light" else DARK
    ratio = _pair(theme, foreground, background)
    assert ratio >= minimum, (
        f"{theme_name}: {foreground} on {background} is {ratio:.2f}:1, "
        f"below the {minimum}:1 needed for {usage}"
    )


class TestTheConversionItself:
    """The check is only worth having if the maths underneath it is right."""

    def test_white_and_black_give_the_maximum_ratio(self):
        assert contrast((1.0, 0.0, 0.0), (0.0, 0.0, 0.0)) == pytest.approx(21.0, abs=0.1)

    def test_a_colour_against_itself_is_one(self):
        assert contrast((0.55, 0.19, 259), (0.55, 0.19, 259)) == pytest.approx(1.0)

    def test_oklch_white_round_trips_to_srgb_white(self):
        r, g, b = oklch_to_srgb(1.0, 0.0, 0.0)
        assert (r, g, b) == pytest.approx((1.0, 1.0, 1.0), abs=1e-3)

    def test_a_neutral_grey_matches_its_known_srgb_luminance(self):
        """Anchored against sRGB #808080, converted independently.

        #808080 is OKLab L ≈ 0.5981, and its linear-light luminance by the sRGB
        transfer function is ((128/255 + 0.055) / 1.055) ** 2.4 = 0.2159. Going
        the other way through this module must land in the same place, which is
        what makes the ratios above trustworthy rather than merely consistent.
        """
        expected = ((128 / 255 + 0.055) / 1.055) ** 2.4
        assert relative_luminance(0.5981, 0.0, 0.0) == pytest.approx(expected, abs=0.005)

    def test_an_achromatic_colour_is_its_lightness_cubed(self):
        """With zero chroma the OKLab pipeline reduces to L³ — a cheap invariant."""
        for lightness in (0.2, 0.5, 0.8):
            assert relative_luminance(lightness, 0.0, 0.0) == pytest.approx(
                lightness**3, abs=1e-6
            )


class TestTheStylesheetIsActuallyBeingRead:
    """A parser that silently returns nothing would make every test above pass."""

    def test_both_themes_were_parsed(self):
        assert len(LIGHT) > 15 and len(DARK) > 15

    def test_dark_mode_overrides_the_background(self):
        assert LIGHT["background"] != DARK["background"]

    def test_every_token_the_pairs_reference_exists(self):
        referenced = {
            token
            for pair in TEXT_PAIRS + NON_TEXT_PAIRS
            for token in (pair[0], pair[1])
        }
        assert referenced <= set(LIGHT), referenced - set(LIGHT)
        assert referenced <= set(DARK), referenced - set(DARK)
