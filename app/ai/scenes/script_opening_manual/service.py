from __future__ import annotations

import json
import uuid
from collections.abc import Mapping

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.scenes.script_opening_manual.schemas import (
    OpeningManualGenerateRequest,
    OpeningManualResult,
    OpeningManualSectionResult,
    OpeningManualValidationResult,
    ScriptFacts,
)
from app.core.exceptions import ApplicationError
from app.modules.knowledge.models import (
    KnowledgeChunk,
    KnowledgeChunkStatus,
    KnowledgeDocument,
    KnowledgeResourceType,
    KnowledgeVersion,
)
from app.ai.scenes.script_opening_manual.models import (
    OpeningManualStatus,
    ScriptOpeningManual,
)
from app.ai.scenes.script_opening_manual.prompts import (
    MANUAL_SYSTEM_PROMPT,
    MANUAL_VALIDATION_SYSTEM_PROMPT,
    SECTION_SPECS,
    build_manual_validation_prompt,
    build_section_prompt,
    SCRIPT_FACTS_SYSTEM_PROMPT,
    build_script_facts_prompt,
)
from app.integrations.llm.client import chat_completion

from app.modules.knowledge.actions.retrieve_chunks import KnowledgeRetriever
from app.modules.knowledge.schemas import KnowledgeRetrieveRequest
from app.integrations.storage.oss import OssStorage


class OpeningManualError(ApplicationError):
    """主持人手册生成相关的可预期业务异常。"""

    status_code = 400
    code = "opening_manual_error"


class OpeningManualNotFoundError(ApplicationError):
    """主持人手册不存在。"""

    status_code = 404
    code = "opening_manual_not_found"


async def get_opening_manual_source(
    db: AsyncSession,
    *,
    store_id: uuid.UUID,
    document_id: uuid.UUID,
) -> tuple[KnowledgeDocument, KnowledgeVersion]:
    stmt = (
        select(KnowledgeDocument, KnowledgeVersion)
        .join(
            KnowledgeVersion,
            KnowledgeDocument.active_version_id == KnowledgeVersion.id,
        )
        .where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.store_id == store_id,
            KnowledgeDocument.deleted_at.is_(None),
        )
    )

    result = await db.execute(stmt)
    row = result.first()

    if row is None:
        raise OpeningManualError(
            "未找到可用的剧本知识库资料，请确认资料是否存在并已完成上传"
        )

    document, version = row

    if document.resource_type != KnowledgeResourceType.SCRIPT:
        raise OpeningManualError("只有剧本类型的知识库资料才能生成主持人手册")

    chunk_count_stmt = select(func.count()).where(
        KnowledgeChunk.document_id == document.id,
        KnowledgeChunk.version_id == version.id,
        KnowledgeChunk.status == KnowledgeChunkStatus.READY,
    )
    chunk_count_result = await db.execute(chunk_count_stmt)
    ready_chunk_count = chunk_count_result.scalar_one()
    if ready_chunk_count <= 0:
        raise OpeningManualError(
            "当前剧本资料还没有整理出可用内容，请先在知识库详情页完成文件识别和内容整理"
        )

    return document, version


async def get_next_manual_version_no(
    db: AsyncSession,
    *,
    store_id: uuid.UUID,
    document_id: uuid.UUID,
) -> int:
    stmt = select(func.max(ScriptOpeningManual.manual_version_no)).where(
        ScriptOpeningManual.store_id == store_id,
        ScriptOpeningManual.document_id == document_id,
    )

    result = await db.execute(stmt)
    current_max = result.scalar_one_or_none()

    return (current_max or 0) + 1


async def create_opening_manual_record(
    db: AsyncSession,
    *,
    store_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID | None,
    manual_version_no: int,
    title: str,
    style: str,
    target_dm_level: str,
    extra_requirement: str | None,
    created_by_user_id: uuid.UUID | None = None,
) -> ScriptOpeningManual:
    manual = ScriptOpeningManual(
        store_id=store_id,
        document_id=document_id,
        version_id=version_id,
        manual_version_no=manual_version_no,
        title=title,
        style=style,
        target_dm_level=target_dm_level,
        extra_requirement=extra_requirement,
        status=OpeningManualStatus.GENERATING,
    )

    if created_by_user_id is not None:
        manual.created_by_user_id = created_by_user_id

    db.add(manual)
    await db.flush()

    return manual


def build_manual_title(
    *,
    script_name: str,
    style: str,
    target_dm_level: str,
) -> str:
    style_label_map = {
        "professional": "专业",
        "simple": "简洁",
        "training": "培训",
    }
    dm_level_label_map = {
        "newbie": "新手DM",
        "experienced": "熟练DM",
    }

    style_label = style_label_map.get(style, "专业")
    dm_level_label = dm_level_label_map.get(target_dm_level, "DM")

    return f"《{script_name}》{style_label}{dm_level_label}主持人手册"


async def create_opening_manual_generation(
    db: AsyncSession,
    *,
    store_id: uuid.UUID,
    document_id: uuid.UUID,
    payload: OpeningManualGenerateRequest,
    created_by_user_id: uuid.UUID | None = None,
) -> ScriptOpeningManual:
    document, version = await get_opening_manual_source(
        db,
        store_id=store_id,
        document_id=document_id,
    )

    manual_version_no = await get_next_manual_version_no(
        db,
        store_id=store_id,
        document_id=document_id,
    )

    title = build_manual_title(
        script_name=document.name,
        style=payload.style,
        target_dm_level=payload.target_dm_level,
    )

    manual = await create_opening_manual_record(
        db,
        store_id=store_id,
        document_id=document.id,
        version_id=version.id,
        manual_version_no=manual_version_no,
        title=title,
        style=payload.style,
        target_dm_level=payload.target_dm_level,
        extra_requirement=payload.extra_requirement,
        created_by_user_id=created_by_user_id,
    )
    # manual = await generate_opening_manual_content(
    #     db,
    #     manual=manual,
    #     document=document,
    #     version=version,
    # )

    return manual


def to_opening_manual_result(
    manual: ScriptOpeningManual,
    *,
    markdown: str | None = None,
) -> OpeningManualResult:
    def to_int(value: object, default: int = 0) -> int:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value.strip():
            return int(value)
        return default

    sections = [
        OpeningManualSectionResult(
            key=str(item.get("key", "")),
            title=str(item.get("title", "")),
            summary=str(item.get("summary", "")),
            sourceCount=to_int(item.get("sourceCount", item.get("source_count", 0))),
        )
        for item in manual.sections
    ]

    return OpeningManualResult(
        id=manual.id,
        documentId=manual.document_id,
        versionId=manual.version_id,
        manualVersionNo=manual.manual_version_no,
        title=manual.title,
        style=manual.style,
        targetDmLevel=manual.target_dm_level,
        status=manual.status.value,
        sections=sections,
        sources=manual.sources,
        markdownPreview=manual.markdown_preview,
        markdown=markdown,
        validationResult=manual.validation_result,
        errorMessage=manual.error_message,
        createdAt=manual.created_at,
        updatedAt=manual.updated_at,
        approvedAt=manual.approved_at,
    )


"""创建一个空的手册框架"""


def build_empty_manual_markdown(
    *,
    title: str,
    script_name: str,
    manual_version_no: int,
    target_dm_level: str,
    style: str,
) -> str:
    lines: list[str] = []

    lines.append(f"# {title}")
    lines.append("")
    lines.append("## 文档信息")
    lines.append("")
    lines.append(f"- 剧本名称：{script_name}")
    lines.append(f"- 手册版本：第 {manual_version_no} 版")
    lines.append(f"- 生成风格：{style}")
    lines.append(f"- 适用 DM：{target_dm_level}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for section in SECTION_SPECS:
        lines.append(f"## {section['title']}")
        lines.append("")
        lines.append("> 这里后续会由 RAG + LLM 根据剧本资料生成内容。")
        lines.append("")

    return "\n".join(lines)


async def generate_opening_manual_content(
    db: AsyncSession,
    *,
    manual: ScriptOpeningManual,
    document: KnowledgeDocument,
    version: KnowledgeVersion,
) -> ScriptOpeningManual:

    script_facts = await extract_script_facts(
        db,
        store_id=manual.store_id,
        document=document,
        version=version,
    )
    section_results = []
    all_sources = []
    lines = []

    lines.append(f"# {manual.title}")
    lines.append("")
    lines.append("## 文档信息")
    lines.append("")
    lines.append(f"- 剧本名称：{document.name}")
    lines.append(f"- 手册版本：第 {manual.manual_version_no} 版")
    lines.append(f"- 生成风格：{manual.style}")
    lines.append(f"- 适用 DM：{manual.target_dm_level}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for section in SECTION_SPECS:
        context_text, sources = await retrieve_manual_section_context(
            db,
            store_id=manual.store_id,
            document=document,
            version=version,
            section=section,
        )

        for source in sources:
            if source not in all_sources:
                all_sources.append(source)

        section_markdown = await generate_manual_section_markdown(
            script_name=document.name,
            section=section,
            context=context_text,
            target_dm_level=manual.target_dm_level,
            extra_requirement=manual.extra_requirement,
            script_facts=script_facts,
        )

        lines.append(section_markdown)
        lines.append("")

        if sources:
            lines.append("### 本章参考来源")
            lines.append("")
            for source in sources:
                lines.append(f"- {source}")
            lines.append("")

        section_results.append(
            {
                "key": str(section["key"]),
                "title": str(section["title"]),
                "summary": summarize_section_markdown(section_markdown),
                "sourceCount": len(sources),
            }
        )

    markdown = "\n".join(lines)

    markdown_key = build_manual_markdown_key(
        store_id=manual.store_id,
        document_id=document.id,
        manual_id=manual.id,
    )

    await OssStorage().put_text(markdown_key, markdown)

    manual.markdown_key = markdown_key

    manual.markdown_preview = markdown[:1200]
    manual.sections = section_results
    manual.sources = all_sources
    validation_result = await validate_opening_manual(
        script_name=document.name,
        manual_markdown=markdown,
        target_dm_level=manual.target_dm_level,
        sources=all_sources,
    )

    manual.validation_result = {
        "scriptFacts": script_facts,
        "overall": validation_result,
    }
    manual.status = OpeningManualStatus.READY

    await db.flush()

    return manual


async def list_opening_manuals(
    db: AsyncSession,
    *,
    store_id: uuid.UUID,
    document_id: uuid.UUID,
) -> list[OpeningManualResult]:
    """查询某个剧本资料下已经生成过的主持人手册版本。"""

    stmt = (
        select(ScriptOpeningManual)
        .where(
            ScriptOpeningManual.store_id == store_id,
            ScriptOpeningManual.document_id == document_id,
        )
        .order_by(
            ScriptOpeningManual.manual_version_no.desc(),
            ScriptOpeningManual.created_at.desc(),
        )
    )
    result = await db.execute(stmt)
    return [to_opening_manual_result(item) for item in result.scalars().all()]


async def get_opening_manual(
    db: AsyncSession,
    *,
    store_id: uuid.UUID,
    manual_id: uuid.UUID,
) -> OpeningManualResult:
    """查询单个主持人手册详情。"""

    stmt = select(ScriptOpeningManual).where(
        ScriptOpeningManual.id == manual_id,
        ScriptOpeningManual.store_id == store_id,
    )
    result = await db.execute(stmt)
    manual = result.scalar_one_or_none()
    if manual is None:
        raise OpeningManualNotFoundError("主持人手册不存在")

    markdown = None

    if manual.markdown_key:
        markdown = await OssStorage().get_text(manual.markdown_key)

    return to_opening_manual_result(
        manual,
        markdown=markdown or manual.markdown_preview,
    )


async def delete_opening_manual(
    db: AsyncSession,
    *,
    store_id: uuid.UUID,
    manual_id: uuid.UUID,
) -> None:
    """删除一个主持人手册版本。"""

    stmt = delete(ScriptOpeningManual).where(
        ScriptOpeningManual.id == manual_id,
        ScriptOpeningManual.store_id == store_id,
    )
    result = await db.execute(stmt)
    if result.rowcount == 0:
        raise OpeningManualNotFoundError("主持人手册不存在")


def build_section_query(
    *,
    script_name: str,
    section: Mapping[str, object],
) -> str:
    return f"《{script_name}》 {section['title']} {section.get('query', '')}"


def format_retrieval_context(results: list[object]) -> tuple[str, list[str]]:
    context_blocks: list[str] = []
    sources: list[str] = []

    for index, item in enumerate(results, start=1):
        relative_path = str(getattr(item, "relative_path", "") or "未知来源")
        title = str(getattr(item, "title", "") or "无标题")
        act = str(getattr(item, "act", "") or "未分幕")
        role_name = str(getattr(item, "role_name", "") or "未识别角色")
        content = str(getattr(item, "content", "") or "")

        if relative_path not in sources:
            sources.append(relative_path)

        context_blocks.append(
            "\n".join(
                [
                    f"[资料 {index}]",
                    f"来源：{relative_path}",
                    f"标题：{title}",
                    f"角色：{role_name}",
                    f"幕：{act}",
                    "内容：",
                    content,
                ]
            )
        )

    return "\n\n".join(context_blocks), sources


def summarize_section_markdown(markdown: str) -> str:
    """从章节 Markdown 中提取一小段摘要，用于前端章节列表展示。"""

    for raw_line in markdown.splitlines():
        line = raw_line.strip().lstrip("#").strip()
        if not line or line.startswith(("---", ">", "|")):
            continue
        return line[:80]
    return "已生成章节内容"


async def retrieve_manual_section_context(
    db: AsyncSession,
    *,
    store_id: uuid.UUID,
    document: KnowledgeDocument,
    version: KnowledgeVersion,
    section: Mapping[str, object],
) -> tuple[str, list[str]]:
    query = build_section_query(
        script_name=document.name,
        section=section,
    )

    result = await KnowledgeRetriever(db).retrieve(
        document.id,
        version.id,
        store_id,
        KnowledgeRetrieveRequest(
            query=query,
            mode="hybrid",
            topK=8,
        ),
    )

    return format_retrieval_context(result.results)


async def generate_manual_section_markdown(
    *,
    script_name: str,
    section: Mapping[str, object],
    context: str,
    target_dm_level: str,
    extra_requirement: str | None,
    script_facts: dict[str, object],
) -> str:
    if not context.strip():
        return (
            f"## {section['title']}\n\n"
            "> 当前章节没有召回到足够资料，需人工确认后补充。\n"
        )

    prompt = build_section_prompt(
        script_name=script_name,
        section=section,
        context=context,
        target_dm_level=target_dm_level,
        extra_requirement=extra_requirement,
        script_facts=script_facts,
    )

    max_tokens = 4200 if section.get("key") == "act_flow" else 2200

    content = await chat_completion(
        messages=[
            {"role": "system", "content": MANUAL_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=max_tokens,
    )

    return content.strip()


async def validate_opening_manual(
    *,
    script_name: str,
    manual_markdown: str,
    target_dm_level: str,
    sources: list[str],
) -> dict[str, object]:
    prompt = build_manual_validation_prompt(
        script_name=script_name,
        manual_markdown=manual_markdown,
        target_dm_level=target_dm_level,
        sources=sources,
    )

    try:
        raw = await chat_completion(
            messages=[
                {"role": "system", "content": MANUAL_VALIDATION_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=1200,
            response_format={"type": "json_object"},
        )

        data = json.loads(raw)
        result = OpeningManualValidationResult.model_validate(data)
        return result.model_dump(mode="json", by_alias=True)

    except Exception as error:
        return {
            "passed": False,
            "score": 0.0,
            "completeness": 0.0,
            "actionability": 0.0,
            "faithfulness": 0.0,
            "spoilerSafety": 0.0,
            "missingSections": ["LLM 审核失败，未能确认手册完整性"],
            "riskNotes": [f"审核调用失败：{error}"],
            "suggestions": ["请人工检查手册内容，或稍后重新生成"],
            "reason": "LLM 审核失败，已降级为本地失败结果。",
        }


async def run_opening_manual_generation(
    db: AsyncSession,
    *,
    store_id: uuid.UUID,
    manual_id: uuid.UUID,
) -> None:
    stmt = (
        select(ScriptOpeningManual, KnowledgeDocument, KnowledgeVersion)
        .join(
            KnowledgeDocument, ScriptOpeningManual.document_id == KnowledgeDocument.id
        )
        .join(KnowledgeVersion, ScriptOpeningManual.version_id == KnowledgeVersion.id)
        .where(
            ScriptOpeningManual.id == manual_id,
            ScriptOpeningManual.store_id == store_id,
        )
    )

    result = await db.execute(stmt)
    row = result.first()
    if row is None:
        return

    manual, document, version = row

    try:
        await generate_opening_manual_content(
            db,
            manual=manual,
            document=document,
            version=version,
        )
    except Exception as error:
        manual.status = OpeningManualStatus.FAILED
        manual.error_message = str(error)
        await db.flush()

    await db.commit()


def build_manual_markdown_key(
    *,
    store_id: uuid.UUID,
    document_id: uuid.UUID,
    manual_id: uuid.UUID,
) -> str:
    return (
        f"stores/{store_id}/script-opening-manuals/"
        f"{document_id}/manuals/{manual_id}/manual.md"
    )


async def extract_script_facts(
    db: AsyncSession,
    *,
    store_id: uuid.UUID,
    document: KnowledgeDocument,
    version: KnowledgeVersion,
) -> dict[str, object]:
    result = await KnowledgeRetriever(db).retrieve(
        document.id,
        version.id,
        store_id,
        KnowledgeRetrieveRequest(
            query=f"《{document.name}》 真相 凶手 关键人物关系 时间线 结局 机制规则 DM手册 组织者手册",
            mode="hybrid",
            topK=16,
        ),
    )

    context, _ = format_retrieval_context(result.results)

    try:
        raw = await chat_completion(
            messages=[
                {"role": "system", "content": SCRIPT_FACTS_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_script_facts_prompt(
                        script_name=document.name, context=context
                    ),
                },
            ],
            temperature=0.1,
            max_tokens=1800,
            response_format={"type": "json_object"},
        )
        data = json.loads(raw)
        facts = ScriptFacts.model_validate(data)
        return facts.model_dump(mode="json", by_alias=True)

    except Exception as error:
        return {
            "scriptName": document.name,
            "playerCount": "需人工确认",
            "duration": "需人工确认",
            "genre": "需人工确认",
            "coreMechanics": [],
            "truthSummary": "需人工确认",
            "killerOrCulprit": "需人工确认",
            "keyRelationships": [],
            "timeline": [],
            "endingConditions": [],
            "spoilerWarnings": [],
            "conflicts": [f"全局事实抽取失败：{error}"],
            "unknowns": ["请人工核对剧本真相、凶手、人物关系和结算条件"],
        }
