"""News item entity."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NewsItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    headline: str
    source: str
    published_at: datetime
    url: str | None = None
    summary: str | None = None


__all__ = ["NewsItem"]
