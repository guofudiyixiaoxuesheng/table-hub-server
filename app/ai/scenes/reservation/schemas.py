from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ReservationQuery(BaseModel):
    date_expression: str | None = Field(
        default=None,
        description="用户明确提到的日期，如 今天、周六、下周末、2026-09-19",
    )
    time_period: Literal["any", "morning", "afternoon", "evening"] = "any"
    player_count: int | None = Field(default=None, ge=1, le=20)
    script_keyword: str | None = None
    needs_clarification: bool = False
    clarification: str | None = None
