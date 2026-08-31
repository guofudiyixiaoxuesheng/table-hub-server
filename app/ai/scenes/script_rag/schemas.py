"""剧本 RAG 子图结构化输出。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ScriptQuestionAnalysis(BaseModel):
    """模型解析出的剧本问题信息。"""

    question_type: Literal[
        "public_consulting",
        "player_role_question",
        "dm_opening",
        "clue_explanation",
        "mechanism_rule",
        "truth_review",
        "missing_info",
    ] = Field(default="missing_info", description="剧本问题类型")
    script_name: str | None = Field(default=None, description="用户提到的剧本名称")
    act: str | None = Field(default=None, description="用户提到的幕次，如 第一幕")
    role_name: str | None = Field(default=None, description="用户提到的角色名")
    spoiler_risk: Literal["low", "medium", "high"] = Field(default="medium", description="剧透风险")
    confidence: float = Field(default=0.5, ge=0, le=1, description="解析置信度")
    reason: str = Field(default="", description="一句话解释解析依据")

    @field_validator("script_name", "act", "role_name", mode="before")
    @classmethod
    def blank_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value
