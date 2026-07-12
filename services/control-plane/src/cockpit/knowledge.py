"""Knowledge index — SQLite FTS5 over local Markdown. Files stay canonical (BUILD_BRIEF).

A RetrievalProvider interface wraps it so Qdrant/LightRAG can slot in later without touching
callers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from cockpit.workspace import allowed_roots_for


class RetrievalProvider(Protocol):
    async def reindex(self, session: AsyncSession, workspace_id: str) -> int: ...
    async def search(
        self, session: AsyncSession, workspace_id: str, query: str, limit: int = 20
    ) -> list[dict[str, Any]]: ...


class FTS5RetrievalProvider:
    async def ensure_table(self, session: AsyncSession) -> None:
        await session.execute(
            text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts "
                "USING fts5(workspace_id, path, title, content)"
            )
        )

    async def reindex(self, session: AsyncSession, workspace_id: str) -> int:
        await self.ensure_table(session)
        await session.execute(
            text("DELETE FROM knowledge_fts WHERE workspace_id = :ws"), {"ws": workspace_id}
        )
        count = 0
        for root in await allowed_roots_for(workspace_id):
            if not root.exists():
                continue
            for path in root.rglob("*.md"):
                if any(part.startswith(".") for part in path.parts):
                    continue
                try:
                    content = path.read_bytes()[:200_000].decode("utf-8", errors="replace")
                except OSError:
                    continue
                await session.execute(
                    text(
                        "INSERT INTO knowledge_fts (workspace_id, path, title, content) "
                        "VALUES (:ws, :path, :title, :content)"
                    ),
                    {
                        "ws": workspace_id,
                        "path": str(path),
                        "title": _title(path, content),
                        "content": content,
                    },
                )
                count += 1
        await session.commit()
        return count

    async def search(
        self, session: AsyncSession, workspace_id: str, query: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        await self.ensure_table(session)
        sanitized = " ".join(f'"{term}"' for term in query.replace('"', " ").split() if term)
        if not sanitized:
            return []
        rows = await session.execute(
            text(
                "SELECT path, title, snippet(knowledge_fts, 3, '⟪', '⟫', '…', 18) AS snip "
                "FROM knowledge_fts WHERE knowledge_fts MATCH :q AND workspace_id = :ws "
                "ORDER BY rank LIMIT :limit"
            ),
            {"q": sanitized, "ws": workspace_id, "limit": limit},
        )
        return [{"path": r.path, "title": r.title, "snippet": r.snip} for r in rows]


def _title(path: Path, content: str) -> str:
    for line in content.splitlines()[:10]:
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


_provider: RetrievalProvider = FTS5RetrievalProvider()


def get_retrieval_provider() -> RetrievalProvider:
    return _provider
