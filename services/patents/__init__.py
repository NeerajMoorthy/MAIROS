"""Patent-awareness support — public sources, manual input, no legal advice.

* ``sources``      — the allowlist, the never-fetch rule, and the disclaimers
* ``segmentation`` — abstract / description / numbered claims, with dependencies
* ``scoring``      — the explainable similarity score
* ``findings``     — the one computation every surface reports
* ``metadata``     — local validation of hand-entered bibliographic fields
* ``export``       — Markdown and CSV, each carrying the full disclaimer
* ``wording``      — the audit for language implying a legal conclusion
"""

from .sources import (
    DISCLAIMER,
    FULL_DISCLAIMER,
    NO_OVERLAP_NOTE,
    PUBLIC_PATENT_DOMAINS,
    PatentSourceError,
    describe_sources,
    validate_public_url,
)

__all__ = [
    "DISCLAIMER",
    "FULL_DISCLAIMER",
    "NO_OVERLAP_NOTE",
    "PUBLIC_PATENT_DOMAINS",
    "PatentSourceError",
    "describe_sources",
    "validate_public_url",
]
