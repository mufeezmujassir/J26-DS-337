"""Discover visible public LankaEvents detail links without fetching them."""
from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from app.holiday_event.http_client import RequestsAsyncClient
from app.holiday_event.source_access import load_terms_reviews, runtime_access_check
from app.holiday_event.sources.lanka_events import LankaEventsExtractor


async def main(args: argparse.Namespace) -> None:
    review = load_terms_reviews(args.terms_policy).get("lanka_events")
    async with RequestsAsyncClient(timeout_seconds=30) as client:
        access = await runtime_access_check("lanka_events", LankaEventsExtractor.base_url, client, terms_review=review)
        if not access["permitted"]:
            result = {"status": "ACCESS_BLOCKED", "access": access, "listing_requests": 0, "urls": []}
        else:
            listing = await LankaEventsExtractor().fetch_public_listing(client)
            records = LankaEventsExtractor().parse(listing)
            urls = sorted({item.source_url for item in records})
            prefixes = Counter(urlparse(url).path for url in urls)
            result = {
                "status": "PUBLIC_LISTING_DISCOVERED",
                "access": access,
                "listing_requests": 1,
                "listing_url": listing.url,
                "event_urls": urls,
                "candidate_path_prefixes_from_visible_links": sorted(prefixes),
                "detail_requests": 0,
                "note": "Candidate prefixes are observed links only. They are not automatically written to policy or treated as approved detail-fetch paths.",
            }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terms-policy", required=True)
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(main(parser.parse_args()))
