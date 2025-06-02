"""Scan social feeds for early pool or venue signals."""

from __future__ import annotations

from typing import List, Dict

import requests
from core.logger import StructuredLogger

_SESSION = requests.Session()

LOG = StructuredLogger("social_alpha")


def scrape_social_keywords(
    keywords: List[str], *, session: requests.Session | None = None
) -> List[Dict[str, str]]:
    """Stubbed scanner for Twitter/Discord keywords."""
    sess = session or _SESSION
    # placeholder network call using session for future expansion
    _ = sess
    results = [
        {"domain": "arbitrum", "pool": "0xb3f8e4262c5bfcc0a304143cfb33c7a9a64e0fe0"},
        {"domain": "l3_superchain", "pool": "0x91a502c978a60c206cd1e904af73607f99e2c1b2"},
    ]
    for r in results:
        if not isinstance(r.get("pool"), str) or not isinstance(r.get("domain"), str):
            raise ValueError("invalid social data")
    LOG.log("social_alpha_scan", keywords=keywords, found=len(results))
    return results
