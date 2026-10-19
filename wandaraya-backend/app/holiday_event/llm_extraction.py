"""Optional, evidence-bound Groq extraction fallback for public event HTML.

The service is deliberately opt-in. It never runs merely because a key exists,
and it never promotes an LLM value unless its supplied evidence is a literal
substring of the supplied public page content.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from .schemas import LLMEventExtraction

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-20b"
MAX_PAGE_CHARS = 12_000
MAX_RETRIES = 1
_CACHE: dict[str, dict] = {}


@dataclass(frozen=True)
class LLMExtractionResult:
    status: str
    extraction: LLMEventExtraction | None
    accepted_fields: dict[str, str]
    rejected_fields: list[str]
    request_count: int = 0


def public_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return " ".join(soup.get_text(" ", strip=True).split())[:MAX_PAGE_CHARS]


def validate_evidence(extraction: LLMEventExtraction, page_text: str) -> tuple[dict[str, str], list[str]]:
    accepted: dict[str, str] = {}
    rejected: list[str] = []
    normalized_page = " ".join(page_text.split())
    for field, item in extraction.model_dump().items():
        value, evidence = item["value"], item["evidence"]
        if value is None:
            continue
        if not evidence or " ".join(evidence.split()) not in normalized_page:
            rejected.append(field)
            continue
        accepted[field] = value
    return accepted, rejected


async def extract_with_groq(html: str, *, enabled: bool) -> LLMExtractionResult:
    if not enabled:
        return LLMExtractionResult("LLM_DISABLED", None, {}, [], 0)
    api_key = settings.GROQ_API_KEY or os.getenv("GROQ_API_KEY")
    if not api_key:
        return LLMExtractionResult("GROQ_API_KEY_MISSING", None, {}, [], 0)
    text = public_text(html)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    response_payload = _CACHE.get(digest)
    requests_made = 0
    if response_payload is None:
        prompt = (
            "Extract only facts explicitly present in the PUBLIC event page text. "
            "Return JSON matching this schema: each field is {value, evidence}; "
            "use null for unsupported fields. Evidence must be an exact short excerpt. "
            "Never infer dates, locations, prices, organisers, or URLs.\n\n" + text
        )
        payload = {"model": MODEL, "temperature": 0, "max_tokens": 1200, "response_format": {"type": "json_object"}, "messages": [{"role": "system", "content": "You are a precise information extractor."}, {"role": "user", "content": prompt}]}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
                response = await client.post(GROQ_URL, headers={"Authorization": f"Bearer {api_key}"}, json=payload)
                response.raise_for_status()
            response_payload = json.loads(response.json()["choices"][0]["message"]["content"])
            _CACHE[digest] = response_payload
            requests_made = 1
        except (httpx.HTTPError, KeyError, ValueError, TypeError):
            return LLMExtractionResult("GROQ_REQUEST_FAILED", None, {}, [], requests_made)
    try:
        extraction = LLMEventExtraction.model_validate(response_payload)
    except Exception:
        return LLMExtractionResult("GROQ_RESPONSE_SCHEMA_REJECTED", None, {}, [], requests_made)
    accepted, rejected = validate_evidence(extraction, text)
    return LLMExtractionResult("LLM_EXTRACTION_AVAILABLE", extraction, accepted, rejected, requests_made)
