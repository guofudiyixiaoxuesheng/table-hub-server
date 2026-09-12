"""剧本 AI 视觉素材生产线 Prompt。

这里不直接生成图片，而是负责生成：
1. 剧本视觉档案
2. 最终生图 Prompt

真正调用图片模型的逻辑放在 service.py。
"""

from __future__ import annotations

from app.modules.knowledge.models import KnowledgeDocument
from app.modules.script_profile.models import ScriptProfile

VISUAL_PROFILE_SYSTEM_PROMPT = (
    "你是剧本杀门店的 AI 视觉策划助手，擅长把剧本资料提炼成可复用的视觉档案。"
    "你的目标不是写宣传文案，而是整理这个剧本的视觉 DNA：时代、场景、色彩、符号、人物公开视觉和安全边界。"
    "必须避免剧透，不要暴露凶手、隐藏身份、最终反转、谜底和 DM 专属答案。"
    "必须注意版权安全：不要要求复刻发行海报、不要照搬已有封面构图、不要出现原发行 logo、不要模仿真实明星或受保护 IP。"
    "只返回 JSON 对象。"
)


IMAGE_PROMPT_SYSTEM_PROMPT = (
    "你是商业海报级 AI 生图 Prompt 设计师。"
    "你会根据剧本视觉档案、视觉风格模板和具体用途，生成适合图片模型使用的中文生图 Prompt。"
    "Prompt 要描述画面主体、人物关系、构图、镜头、光影、色彩、材质、氛围和安全禁忌。"
    "对于拼车主图、详情图、朋友圈海报，必须优先生成有人物主体或人物剪影的海报级画面，不要退化成桌面道具静物。"
    "不要直接生成带中文文字的海报，中文标题和价格信息应交给系统后期排版。"
    "不要复刻发行海报，不要出现真实 logo、二维码、水印和版权文本。"
    "只返回 JSON 对象。"
)


def format_script_profile_context(profile: ScriptProfile | None) -> str:
    """把剧本档案压缩成视觉生成可用的上下文。"""

    if profile is None:
        return "暂无结构化剧本档案，请更多依据 RAG 上下文提炼视觉信息，并标注需要人工确认的部分。"

    return f"""
【剧本档案】
剧本名称：{profile.name}
剧本类型：{", ".join(profile.genres or []) or "暂无"}
人数：{profile.player_count_min or "?"}-{profile.player_count_max or "?"}
时长：{profile.duration_minutes or "暂无"}
故事背景：{profile.story_background or profile.summary or "暂无"}
玩家卖点：{", ".join(profile.selling_points or []) or "暂无"}
适合玩家：{", ".join(profile.suitable_players or []) or "暂无"}
核心机制：{", ".join(profile.core_mechanics or []) or "暂无"}
人物关系：{profile.relationships or "暂无"}
开本风险：{profile.opening_risks or "暂无"}
剧透提醒：{profile.spoiler_notes or "暂无"}
""".strip()


def build_visual_profile_prompt(
    *,
    document: KnowledgeDocument,
    profile: ScriptProfile | None,
    rag_context: str,
    reference_image_urls: list[str],
    extra_requirement: str | None,
) -> str:
    """构建生成视觉档案的用户 Prompt。"""

    return f"""
请为剧本《{document.name}》生成一份【剧本视觉档案】。

{format_script_profile_context(profile)}

【RAG 原始资料】
{rag_context}

【参考图】
{chr(10).join(f"- {url}" for url in reference_image_urls) if reference_image_urls else "暂无"}

【店长补充要求】
{extra_requirement or "无"}

请只返回 JSON，对象字段必须包含：
name, era, world_setting, main_scenes, visual_symbols, color_palette,
atmosphere_keywords, character_visuals, spoiler_safe_rules, copyright_safe_rules,
reference_image_urls, confidence_score。

字段要求：
- name：剧本名称
- era：时代背景，例如民国上海、现代都市、古风王朝
- world_setting：世界观/主要空间的视觉描述
- main_scenes：核心场景数组
- visual_symbols：可用于画面的视觉符号数组
- color_palette：推荐主色调数组
- atmosphere_keywords：氛围关键词数组
- character_visuals：角色公开视觉数组，每项包含 name, publicIdentity, gender, outfit, props, emotionKeywords, visualPrompt, spoilerLevel
- spoiler_safe_rules：剧透安全规则数组
- copyright_safe_rules：版权安全规则数组
- reference_image_urls：参考图 URL 数组
- confidence_score：0-100，表示视觉档案完整度

特别注意：
- 不要写出凶手、隐藏身份、最终真相。
- 如果资料不足，可以写“需人工确认”，但不要编造关键设定。
- 人物视觉只写玩家可见或宣传安全的信息。
""".strip()


def usage_instruction(usage_type: str, usage_label: str) -> str:
    """根据图片用途生成不同的画面要求。"""

    mapping = {
        "session_cover": "用于玩家端拼车卡片主图，必须有明确人物主体、人物剪影或强情绪关系，移动端小图也能识别；不要只画桌子、灯笼、账本、骰子等道具静物；构图留有安全裁切空间。",
        "session_detail": "用于玩家端详情页氛围图，要求更沉浸、更有场景叙事；可以展示人物背影、门缝窥视、窗前剪影、关键空间与少量道具；不要剧透，不要只堆道具。",
        "moments_poster": "用于朋友圈海报背景图，要求竖版友好，必须有强海报主体和情绪钩子；可用人物剪影、背影、对峙、相拥、窥视等构图；画面上方和下方保留干净区域，方便系统后期叠加标题、时间、价格和门店信息。",
        "character_portrait": "用于人物详情图，要求单角色半身像或立绘感，突出服装、身份、情绪和代表道具，不暴露隐藏身份。",
    }
    return mapping.get(
        usage_type, f"用于{usage_label}，请保证画面适合门店宣传和玩家浏览。"
    )


def build_image_prompt_prompt(
    *,
    visual_profile: str,
    style_preset_name: str,
    style_prompt_template: str,
    negative_prompt: str | None,
    usage_type: str,
    usage_label: str,
    aspect_ratio: str,
    extra_requirement: str | None,
) -> str:
    """构建最终生图 Prompt 的用户 Prompt。"""

    return f"""
请基于以下信息，生成一条中文生图 Prompt。

【剧本视觉档案】
{visual_profile}

【选择的视觉风格】
风格名称：{style_preset_name}
风格模板：{style_prompt_template}
负向提示：{negative_prompt or "无"}

【图片用途】
用途：{usage_label}（{usage_type}）
用途要求：{usage_instruction(usage_type, usage_label)}
图片比例：{aspect_ratio}

【店长补充要求】
{extra_requirement or "无"}

请只返回 JSON，对象字段必须包含：
prompt, negative_prompt。

要求：
- prompt 用中文，适合直接传给图片生成模型。
- 如果用途是拼车主图、详情图或朋友圈海报，画面必须有“人”或“人物剪影/背影/对峙/相拥/群像”等可识别主体。
- 不要生成单纯桌面静物，不要只堆放道具，不要让画面主体变成灯笼、账本、骰子、手牌、钞票、麦克风。
- 明确写出构图，例如“中央窗前剪影”“门缝窥视构图”“前景帘幕遮挡”“左右留白给后期排版”“移动端小图可识别”。
- 不要要求生成可读中文文字，不要生成 logo、水印、二维码。
- 不要复刻发行海报，不要照搬参考图构图。
- 画面可以借鉴时代感、色调、氛围和符号，但必须形成新的原创构图。
- 如果是朋友圈海报背景，要明确“无文字海报背景，留白区域供后期排版”。
""".strip()
