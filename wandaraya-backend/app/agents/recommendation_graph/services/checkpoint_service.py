from __future__ import annotations

import asyncio
import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from langgraph.checkpoint.memory import MemorySaver


class SessionOwnershipError(PermissionError):
    pass


@dataclass
class SessionRecord:
    owner_hash: str
    checkpoint_thread_id: str
    awaiting_clarification: bool
    expires_at: datetime


class DevelopmentCheckpointService:
    """Process-local checkpointing for research/dev only; not a production store."""

    def __init__(self, ttl_seconds: int):
        self.checkpointer = MemorySaver()
        self.ttl_seconds = ttl_seconds
        self._sessions: dict[str, SessionRecord] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def hash_owner(owner: str) -> str:
        return hashlib.sha256(owner.strip().encode("utf-8")).hexdigest()

    async def claim(self, session_id: str, owner: str) -> SessionRecord:
        owner_hash = self.hash_owner(owner)
        now = datetime.now(timezone.utc)
        async with self._lock:
            expired = [key for key, value in self._sessions.items() if value.expires_at <= now]
            for key in expired:
                expired_record = self._sessions.pop(key, None)
                if expired_record is not None:
                    await self.checkpointer.adelete_thread(expired_record.checkpoint_thread_id)
            record = self._sessions.get(session_id)
            if record is not None and record.owner_hash != owner_hash:
                raise SessionOwnershipError("The session belongs to another research owner.")
            if record is None:
                record = SessionRecord(owner_hash=owner_hash, checkpoint_thread_id=uuid.uuid4().hex,
                                       awaiting_clarification=False,
                                       expires_at=now + timedelta(seconds=self.ttl_seconds))
                self._sessions[session_id] = record
            else:
                record.expires_at = now + timedelta(seconds=self.ttl_seconds)
            return record

    async def set_awaiting(self, session_id: str, awaiting: bool) -> None:
        async with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].awaiting_clarification = awaiting
