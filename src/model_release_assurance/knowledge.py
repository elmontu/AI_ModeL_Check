from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

from .integrity import sha256_bytes, sha256_file


TOKEN_RE = re.compile(r"[a-z0-9]+")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
DEFAULT_PATTERNS = ("docs/**/*.md", "schemas/*.json")


def _tokens(value: str) -> list[str]:
    return TOKEN_RE.findall(value.lower())


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    source: str
    source_sha256: str
    title: str
    section: str
    ordinal: int
    text: str


@dataclass(frozen=True)
class SearchHit:
    chunk_id: str
    source: str
    source_sha256: str
    title: str
    section: str
    ordinal: int
    score: float
    text: str


class KnowledgeIndex:
    """Deterministic, local lexical index for advisory assurance retrieval.

    Results are context for a reviewer. They are not scientific evidence,
    assessment decisions, or release authorizations.
    """

    FORMAT_VERSION = "mra-knowledge-index/1"

    def __init__(self, chunks: Sequence[KnowledgeChunk]):
        self.chunks = tuple(chunks)
        self._term_counts = []
        for chunk in self.chunks:
            counts = Counter(_tokens(chunk.text))
            # Source and heading terms are compact, trustworthy ranking signals.
            # Weight them without changing or interpreting the indexed content.
            counts.update(_tokens(f"{chunk.source} {chunk.title} {chunk.section}") * 2)
            self._term_counts.append(counts)
        self._lengths = [sum(counts.values()) for counts in self._term_counts]
        self._average_length = (
            sum(self._lengths) / len(self._lengths) if self._lengths else 0.0
        )
        self._document_frequency: Counter[str] = Counter()
        for counts in self._term_counts:
            self._document_frequency.update(counts.keys())

    @classmethod
    def build(
        cls,
        root: Path,
        patterns: Sequence[str] = DEFAULT_PATTERNS,
        *,
        max_chunk_chars: int = 4_000,
    ) -> "KnowledgeIndex":
        root = root.resolve(strict=True)
        paths = sorted(
            {path.resolve() for pattern in patterns for path in root.glob(pattern) if path.is_file()}
        )
        chunks: list[KnowledgeChunk] = []
        for path in paths:
            relative = path.relative_to(root).as_posix()
            text = path.read_text(encoding="utf-8")
            digest = sha256_file(path)
            title = path.stem
            if path.suffix.lower() == ".md":
                chunks.extend(_chunk_markdown(text, relative, digest, title, max_chunk_chars))
            elif path.suffix.lower() == ".json":
                chunks.extend(_chunk_json(text, relative, digest, title, max_chunk_chars))
        return cls(chunks)

    def search(self, query: str, *, limit: int = 5) -> list[SearchHit]:
        if not query.strip():
            raise ValueError("query must not be empty")
        if not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20")
        query_counts = Counter(_tokens(query))
        if not query_counts or not self.chunks:
            return []
        population = len(self.chunks)
        k1, b = 1.5, 0.75
        ranked: list[tuple[float, int]] = []
        for index, counts in enumerate(self._term_counts):
            score = 0.0
            length = self._lengths[index]
            for term, query_frequency in query_counts.items():
                frequency = counts.get(term, 0)
                if not frequency:
                    continue
                document_frequency = self._document_frequency[term]
                inverse_frequency = math.log(
                    1 + (population - document_frequency + 0.5) / (document_frequency + 0.5)
                )
                normalization = frequency + k1 * (
                    1 - b + b * length / max(self._average_length, 1.0)
                )
                score += query_frequency * inverse_frequency * frequency * (k1 + 1) / normalization
            if score > 0:
                ranked.append((score, index))
        ranked.sort(key=lambda item: (-item[0], self.chunks[item[1]].source, item[1]))
        return [
            SearchHit(**asdict(self.chunks[index]), score=round(score, 8))
            for score, index in ranked[:limit]
        ]

    def save(self, path: Path) -> None:
        payload = {
            "format": self.FORMAT_VERSION,
            "chunks": [asdict(chunk) for chunk in self.chunks],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "KnowledgeIndex":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("format") != cls.FORMAT_VERSION:
            raise ValueError("unsupported knowledge-index format")
        return cls([KnowledgeChunk(**chunk) for chunk in payload["chunks"]])


def _make_chunk(
    source: str,
    source_sha256: str,
    title: str,
    section: str,
    ordinal: int,
    text: str,
) -> KnowledgeChunk:
    normalized = text.strip()
    material = f"{source}\n{section}\n{ordinal}\n{normalized}".encode("utf-8")
    return KnowledgeChunk(
        chunk_id=sha256_bytes(material),
        source=source,
        source_sha256=source_sha256,
        title=title,
        section=section,
        ordinal=ordinal,
        text=normalized,
    )


def _split_blocks(text: str, max_chars: int) -> Iterable[str]:
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", text) if item.strip()]
    current = ""
    for paragraph in paragraphs:
        if current and len(current) + len(paragraph) + 2 > max_chars:
            yield current
            current = ""
        if len(paragraph) <= max_chars:
            current = f"{current}\n\n{paragraph}".strip()
        else:
            if current:
                yield current
                current = ""
            for start in range(0, len(paragraph), max_chars):
                yield paragraph[start : start + max_chars]
    if current:
        yield current


def _chunk_markdown(
    text: str, source: str, digest: str, title: str, max_chars: int
) -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []
    section = title
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        for block in _split_blocks(body, max_chars):
            chunks.append(_make_chunk(source, digest, title, section, len(chunks), block))
        buffer.clear()

    for line in text.splitlines():
        match = HEADING_RE.match(line)
        if match:
            flush()
            section = match.group(2).strip()
        else:
            buffer.append(line)
    flush()
    return chunks


def _chunk_json(
    text: str, source: str, digest: str, title: str, max_chars: int
) -> list[KnowledgeChunk]:
    value = json.loads(text)
    rendered = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True)
    return [
        _make_chunk(source, digest, title, "JSON schema", ordinal, block)
        for ordinal, block in enumerate(_split_blocks(rendered, max_chars))
    ]
