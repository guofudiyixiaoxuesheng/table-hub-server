"""剧本 RAG 子图状态。"""

from __future__ import annotations

from typing import Literal, TypedDict

from app.ai.state import ParentGraphState

ScriptQuestionType = Literal[
    "public_consulting",
    "player_role_question",
    "dm_opening",
    "clue_explanation",
    "mechanism_rule",
    "truth_review",
    "missing_info",
]
ScriptPermissionLevel = Literal["guest", "player", "dm", "manager", "admin"]
SpoilerRisk = Literal["low", "medium", "high"]


class ScriptRagState(ParentGraphState, total=False):
    """剧本 RAG 子图内部状态。

    父图只识别 script_rag；进入子图后再细分剧本、角色、幕、问题类型和权限。
    """

    script_id: str | None
    script_name: str | None
    act: str | None
    role_name: str | None
    question_type: ScriptQuestionType
    permission_level: ScriptPermissionLevel
    spoiler_risk: SpoilerRisk
    allowed_filters: dict[str, object]
    context_rewritten_query: str
    context_rewrite_reason: str
    retrieved_chunks: list[dict[str, object]]
    safe_context: str
    answer_validation: dict[str, object]
    answer_validated: bool


class ScriptQuestionParseResult(TypedDict):
    question_type: ScriptQuestionType
    script_name: str | None
    act: str | None
    role_name: str | None
    spoiler_risk: SpoilerRisk
    confidence: float
    reason: str
