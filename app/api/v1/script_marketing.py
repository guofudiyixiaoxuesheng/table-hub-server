"""剧本 AI 运营物料接口。"""

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.scenes.script_marketing.models import ScriptMarketingAssetStatus
from app.ai.scenes.script_marketing.schemas import (
    ScriptMarketingApproveRequest,
    ScriptMarketingGenerateImagesRequest,
    ScriptMarketingGenerateRequest,
)
from app.ai.scenes.script_marketing.service import (
    approve_script_marketing_asset,
    generate_script_marketing_assets,
    generate_script_marketing_images,
    list_script_marketing_assets,
    queue_script_marketing_images,
)
from app.common.responses import success_response
from app.core.config import settings
from app.core.database import AsyncSessionLocal, get_database
from app.core.security import StoreManagerAccess

router = APIRouter(prefix="/script-marketing", tags=["script-marketing"])
logger = logging.getLogger(__name__)


async def run_script_marketing_generation_background(
    *,
    store_id: uuid.UUID,
    document_id: uuid.UUID,
    user_id: uuid.UUID | None,
    payload_data: dict[str, object],
) -> None:
    """使用独立事务生成运营物料，避免长时间 LLM 调用占用浏览器代理连接。"""

    async with AsyncSessionLocal() as db:
        try:
            await generate_script_marketing_assets(
                store_id=store_id,
                document_id=document_id,
                user_id=user_id,
                payload=ScriptMarketingGenerateRequest.model_validate(payload_data),
                db=db,
            )
            await db.commit()
        except Exception:  # noqa: BLE001 - 后台任务必须记录所有失败，不能让异常冒出中断后续任务。
            await db.rollback()
            logger.exception(
                "script marketing generation failed in background",
                extra={"document_id": str(document_id), "store_id": str(store_id)},
            )


async def run_script_marketing_images_background(
    *,
    store_id: uuid.UUID,
    asset_id: uuid.UUID,
    generation_id: str,
    payload_data: dict[str, object],
) -> None:
    """真实生图耗时较长，必须使用独立事务在 HTTP 响应之后继续执行。"""

    async with AsyncSessionLocal() as db:
        try:
            await generate_script_marketing_images(
                store_id=store_id,
                asset_id=asset_id,
                payload=ScriptMarketingGenerateImagesRequest.model_validate(
                    payload_data
                ),
                db=db,
                generation_id=generation_id,
            )
            await db.commit()
        except Exception:
            # 业务层已把可预期的生图异常写回为 failed；提交状态，避免页面永久显示“生成中”。
            await db.commit()


@router.get("/{document_id}")
async def list_script_marketing_route(
    document_id: uuid.UUID,
    access: StoreManagerAccess,
    status_filter: ScriptMarketingAssetStatus | None = Query(
        default=None, alias="status"
    ),
    db: AsyncSession = Depends(get_database),
):
    """查询某个剧本已生成的运营物料版本。"""

    data = await list_script_marketing_assets(
        store_id=access.store_id,
        document_id=document_id,
        status=status_filter,
        db=db,
    )
    return success_response(
        data=[item.model_dump(mode="json", by_alias=True) for item in data]
    )


@router.post("/{document_id}/generate")
async def generate_script_marketing_route(
    document_id: uuid.UUID,
    payload: ScriptMarketingGenerateRequest,
    background_tasks: BackgroundTasks,
    access: StoreManagerAccess,
):
    """后台生成宣传文案和图片提示词草稿，前端由用户手动刷新查看结果。"""

    background_tasks.add_task(
        run_script_marketing_generation_background,
        store_id=access.store_id,
        document_id=document_id,
        user_id=access.user_id,
        payload_data=payload.model_dump(mode="json", by_alias=True),
    )
    return success_response(
        message="AI 运营物料任务已在后台启动，请稍后手动刷新查看结果",
        data={"documentId": str(document_id), "status": "generating"},
    )


@router.post("/assets/{asset_id}/approve")
async def approve_script_marketing_route(
    asset_id: uuid.UUID,
    payload: ScriptMarketingApproveRequest,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    """店长确认采用某个 AI 运营物料版本。"""

    data = await approve_script_marketing_asset(
        store_id=access.store_id,
        asset_id=asset_id,
        user_id=access.user_id,
        payload=payload,
        db=db,
    )
    return success_response(
        message="AI 运营物料已确认为正式版本",
        data=data.model_dump(mode="json", by_alias=True),
    )


@router.post("/assets/{asset_id}/images")
async def generate_script_marketing_images_route(
    asset_id: uuid.UUID,
    payload: ScriptMarketingGenerateImagesRequest,
    background_tasks: BackgroundTasks,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),
):
    """为正式物料生成真实图片，并保存到 OSS 供场次和移动端复用。"""

    if settings.IMAGE_GENERATION_DRY_RUN:
        data = await generate_script_marketing_images(
            store_id=access.store_id,
            asset_id=asset_id,
            payload=payload,
            db=db,
        )
        return success_response(
            message="提示词模拟完成，未调用外部生图服务",
            data=data.model_dump(mode="json", by_alias=True),
        )

    data = await queue_script_marketing_images(
        store_id=access.store_id,
        asset_id=asset_id,
        payload=payload,
        db=db,
    )
    await db.commit()
    generation_id = str(data.image_generations[0]["id"])
    background_tasks.add_task(
        run_script_marketing_images_background,
        store_id=access.store_id,
        asset_id=asset_id,
        generation_id=generation_id,
        payload_data=payload.model_dump(mode="json", by_alias=True),
    )
    return success_response(
        message="图片生成任务已在后台启动",
        data=data.model_dump(mode="json", by_alias=True),
    )
