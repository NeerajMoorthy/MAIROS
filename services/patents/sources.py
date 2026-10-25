"""What MAIROS will and will not accept as a patent source.

This module is the safety boundary of the patent-awareness prototype, and it
is deliberately restrictive:

* **No server-side fetching.** MAIROS never retrieves a patent document itself.
  A URL is stored as a *reference* the reader can open; the text that gets
  analysed is whatever the user pasted in. That removes the server-side request
  forgery surface entirely — there is no code path where a submitted URL causes
  an outbound request — and it keeps MAIROS clear of the terms of service of
  commercial patent databases.

* **Public registries only.** A stored reference must point at a free, public
  patent registry. A link to a paywalled analytics product or an arbitrary host
  is rejected with an explanation rather than quietly accepted.

* **No legal conclusions, ever.** Every response carries ``DISCLAIMER``. The
  feature reports where a project's own vocabulary overlaps text the user
  supplied. It does not construe claims, assess novelty, or opine on
  infringement — those are legal determinations, and a retrieval system is not
  qualified to make them.
"""

from __future__ import annotations

from urllib.parse import urlparse

DISCLAIMER = (
    "Research-support only. Not legal advice or a patentability assessment."
)

# The complete wording, carried in the body of every exported or printed
# artifact. An exported file is read by people who never saw the app, so the
# short banner alone is not enough context for them. It names the conclusions
# MAIROS does *not* draw — the wording audit in ``wording.py`` treats this exact
# text as a permitted explanatory exception.
FULL_DISCLAIMER = (
    DISCLAIMER
    + " These findings are computed overlaps in wording between this research "
    "project's own sources and patent text that a user pasted in; MAIROS did not "
    "retrieve the patent document. The similarity score measures shared wording "
    "only. It is not a probability, a risk level, or an opinion on infringement, "
    "validity, or freedom to operate, and the absence of an overlap is not a "
    "clearance. Consult a qualified patent professional for any legal question."
)

# Shown whenever no overlap is found, in every surface. Kept as a constant so
# the API, the UI and the exports cannot drift into different wordings.
NO_OVERLAP_NOTE = (
    "No project concept was found in the supplied patent text. "
    "Absence of a literal overlap is not a legal clearance."
)

# Free, public patent registries. Values are the human-readable names.
PUBLIC_PATENT_DOMAINS: dict[str, str] = {
    "patents.google.com": "Google Patents",
    "worldwide.espacenet.com": "Espacenet (EPO)",
    "register.epo.org": "EPO Register",
    "patentscope.wipo.int": "PATENTSCOPE (WIPO)",
    "ppubs.uspto.gov": "USPTO Patent Public Search",
    "patft.uspto.gov": "USPTO Full-Text (legacy)",
    "patentsview.org": "PatentsView (USPTO data)",
    "api.patentsview.org": "PatentsView API",
    "iprsearch.ipindia.gov.in": "Indian Patent Advanced Search",
}

ALLOWED_SCHEMES = {"http", "https"}


class PatentSourceError(ValueError):
    """Raised when a submitted patent reference is not acceptable."""


def _host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def validate_public_url(url: str) -> tuple[str, str]:
    """Check a patent reference URL against the public-registry allowlist.

    Args:
        url: The reference the user supplied. May be empty — a patent can be
            entered by hand with no link at all.

    Returns:
        ``(normalised_url, source_name)``. Both are empty strings when *url*
        is empty, which is a valid manual-entry case.

    Raises:
        PatentSourceError: The scheme or host is not an allowed public source.
    """
    url = (url or "").strip()
    if not url:
        return "", "manual entry"

    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise PatentSourceError(
            "A patent reference must be an http(s) URL on a public patent registry."
        )

    host = _host(url)
    if host not in PUBLIC_PATENT_DOMAINS:
        raise PatentSourceError(
            f"'{host or url}' is not a recognised public patent registry. "
            "Allowed sources: " + ", ".join(sorted(PUBLIC_PATENT_DOMAINS)) + ". "
            "Paste the patent text directly if your source is not listed — MAIROS "
            "never fetches the document itself."
        )

    return url, PUBLIC_PATENT_DOMAINS[host]


def describe_sources() -> dict:
    """The allowlist and the rules, for the UI to display before input."""
    return {
        "disclaimer": DISCLAIMER,
        "full_disclaimer": FULL_DISCLAIMER,
        "fetches_documents": False,
        "sources": [
            {"domain": domain, "name": name}
            for domain, name in sorted(PUBLIC_PATENT_DOMAINS.items())
        ],
        "notes": [
            "MAIROS never downloads a patent. Paste the abstract or claims text "
            "you want compared; a URL is stored only as a reference for the reader.",
            "Findings are computed overlaps between your project's own vocabulary "
            "and the text you supplied, located to the claim or section they occur "
            "in and ranked by a similarity score over wording — not a claim "
            "construction.",
            DISCLAIMER,
        ],
    }
