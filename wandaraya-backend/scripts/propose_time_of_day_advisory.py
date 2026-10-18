"""Create an automatically usable, evidence-tiered Groq best-time advisory.

This command never updates PostgreSQL, Qdrant, or ``opening_hours``. It is
deliberately separate from availability evaluation: language-model output is
not evidence that an attraction is open or closed. Source-supported advice is
usable automatically after structural validation; model-only advice is usable
only as an explicitly low-confidence advisory.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.attraction import Attraction
from app.models.attraction_descriptions import AttractionDescription


async def load_sources(attraction_id: int) -> tuple[str, list[dict]]:
    async with AsyncSessionLocal() as db:
        attraction = await db.scalar(select(Attraction).where(Attraction.id == attraction_id, Attraction.is_active.is_(True)))
        if attraction is None:
            raise ValueError("Active attraction not found")
        rows = (await db.execute(select(AttractionDescription).where(AttractionDescription.attraction_id == attraction_id, AttractionDescription.is_active.is_(True)))).scalars().all()
    # Stored description provenance is retained in the report. Restricting the
    # excerpt prevents an accidental large/copyright-sensitive prompt.
    excerpts = [{"title": row.title, "source_url": row.source_url, "text": (row.description or "")[:2500]} for row in rows if row.description]
    return attraction.name, excerpts[:3]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attraction-id", type=int, required=True)
    parser.add_argument("--execute", action="store_true", help="Required before the paid Groq request is made.")
    args = parser.parse_args()
    # ``Settings`` loads the application's mounted .env file.  Docker's
    # process environment can legitimately omit the value when compose does
    # not explicitly forward it, so do not rely on ``os.environ`` alone.
    groq_api_key = settings.GROQ_API_KEY or os.getenv("GROQ_API_KEY")
    name, excerpts = await load_sources(args.attraction_id)
    report = {
        "attraction_id": args.attraction_id, "attraction_name": name,
        "status": "ADVISORY_PREPARATION", "opening_hours_modified": False,
        "postgresql_writes": False, "qdrant_writes": False,
        "source_excerpts": [{"title": item["title"], "source_url": item["source_url"]} for item in excerpts],
        "limitations": ["Not opening-hours evidence.", "Must not determine OPEN/CLOSED.", "Best-time advice is not a guarantee of accessibility, safety, or weather."],
    }
    if not args.execute:
        report["status"] = "DRY_RUN_NO_GROQ_REQUEST"
    elif not groq_api_key:
        report["status"] = "BLOCKED_GROQ_API_KEY_MISSING"
    else:
        if excerpts:
            prompt = """Produce JSON only with: best_time_advisory, confidence, source_supported_claims, cited_source_urls, limitations. Use only supplied source excerpts. Do not state or infer opening/closing hours. Cite only supplied source URLs. If excerpts do not support an advisory, return null for best_time_advisory and an empty cited_source_urls list.\n\n""" + json.dumps(excerpts)
        else:
            prompt = f"""For attraction {name}, produce JSON only with: best_time_advisory, confidence, source_supported_claims, cited_source_urls, limitations. There are no supplied sources. Do not claim facts, do not state opening/closing hours, use an empty cited_source_urls list, and label the limitations as model-generated low-confidence guidance."""
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {groq_api_key}"}, json={"model": "openai/gpt-oss-20b", "temperature": 0, "response_format": {"type": "json_object"}, "messages": [{"role": "system", "content": "You are a cautious tourism evidence summarizer."}, {"role": "user", "content": prompt}]})
            response.raise_for_status()
            advisory = json.loads(response.json()["choices"][0]["message"]["content"])
            permitted_urls = {item["source_url"] for item in excerpts if item.get("source_url")}
            cited_urls = set(advisory.get("cited_source_urls") or [])
            if excerpts and not cited_urls.issubset(permitted_urls):
                report["status"] = "LLM_RESPONSE_REJECTED_UNRECOGNISED_CITATION"
                report["advisory_evidence_tier"] = "unknown"
                report["confidence"] = "unavailable"
            elif excerpts and advisory.get("best_time_advisory") and not cited_urls:
                report["status"] = "LLM_RESPONSE_REJECTED_MISSING_CITATION"
                report["advisory_evidence_tier"] = "unknown"
                report["confidence"] = "unavailable"
            else:
                report["llm_advisory"] = advisory
                report["status"] = "SOURCE_SUPPORTED_ADVISORY_AVAILABLE" if excerpts else "LLM_GENERATED_ADVISORY_AVAILABLE"
                report["advisory_evidence_tier"] = "source_supported_advisory" if excerpts else "llm_generated_advisory"
                report["confidence"] = "low"
                report["automatically_usable_for_best_time_guidance"] = True
    report["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    output = Path(f"data/reports/stage12_2_llm_best_time_advisory_{args.attraction_id}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
