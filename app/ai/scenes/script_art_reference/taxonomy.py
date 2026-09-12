"""剧本杀美术参考分析标签体系。

MVP 阶段先用代码内置枚举，保证产品可以快速跑起来。
后续如果标签增长很快，再升级成数据库可维护标签表。
"""

from __future__ import annotations

from typing import TypedDict


class TaxonomyOption(TypedDict):
    label: str
    value: str
    description: str


TaxonomyAliases = dict[str, dict[str, str]]


SCRIPT_TAG_OPTIONS: list[TaxonomyOption] = [
    {"label": "推理", "value": "reasoning", "description": "盘逻辑、找凶、解谜"},
    {"label": "硬核", "value": "hardcore", "description": "强逻辑、强推理门槛"},
    {"label": "还原", "value": "restoration", "description": "重点还原故事真相"},
    {"label": "欢乐", "value": "comedy", "description": "轻松搞笑、适合团建"},
    {"label": "情感", "value": "emotional", "description": "代入、哭点、关系线"},
    {"label": "恐怖", "value": "horror", "description": "惊悚氛围、NPC、音效"},
    {"label": "阵营", "value": "camp", "description": "分队博弈、对抗"},
    {"label": "机制", "value": "mechanism", "description": "规则博弈、小游戏、资源"},
    {
        "label": "刑侦",
        "value": "criminal_investigation",
        "description": "案件、证据、侦查",
    },
    {"label": "豪门", "value": "wealthy_family", "description": "家族、宅邸、利益关系"},
]

USAGE_TYPE_OPTIONS: list[TaxonomyOption] = [
    {"label": "主海报", "value": "main_poster", "description": "发行/宣传主视觉"},
    {"label": "拼车卡片图", "value": "cover", "description": "玩家端列表卡片主图"},
    {"label": "详情氛围图", "value": "detail", "description": "玩家详情页场景/氛围图"},
    {"label": "人物图", "value": "character", "description": "角色立绘/半身像/身份图"},
    {"label": "朋友圈图", "value": "moments", "description": "微信私域传播素材"},
    {"label": "横版 Banner", "value": "banner", "description": "平台横向展示图"},
    {"label": "Logo/标题字", "value": "logo", "description": "标题字、发行标识参考"},
    {"label": "道具/线索图", "value": "prop", "description": "道具、线索、物料图"},
    {"label": "其他", "value": "other", "description": "暂未分类素材"},
]

STYLE_TYPE_OPTIONS: list[TaxonomyOption] = [
    {
        "label": "电影写实风",
        "value": "cinematic_realistic",
        "description": "电影海报、写实光影、商业质感",
    },
    {
        "label": "电影插画风",
        "value": "cinematic_collage_illustration",
        "description": "电影海报构图、平面拼贴、插画笔触与强烈视觉叙事",
    },
    {
        "label": "国风插画风",
        "value": "chinese_illustration",
        "description": "国潮、古风、民俗、中式装饰语言",
    },
    {
        "label": "幻想插画风",
        "value": "fantasy_illustration",
        "description": "奇幻冒险、神话世界、欧美幻想与桌游封面感",
    },
    {
        "label": "二次元插画风",
        "value": "anime_illustration",
        "description": "日系/国漫角色向插画",
    },
    {
        "label": "网文封面风",
        "value": "webnovel_cover",
        "description": "甜宠、霸总、强标题、强情绪封面",
    },
    {
        "label": "卡通漫画风",
        "value": "cartoon_comic",
        "description": "夸张表情、欢乐、轻松、综艺感",
    },
    {
        "label": "极简设计风",
        "value": "minimal_design",
        "description": "留白、符号化、平面设计感",
    },
    {"label": "未识别", "value": "unknown", "description": "暂未判断画风"},
]

ERA_TYPE_OPTIONS: list[TaxonomyOption] = [
    {"label": "古代", "value": "ancient", "description": "古代、宫廷、江湖、传统世界"},
    {
        "label": "民国/近代",
        "value": "republic_modern",
        "description": "民国、近代、旧上海、战争年代",
    },
    {"label": "现代", "value": "modern", "description": "当代都市、校园、职场、生活"},
    {
        "label": "未来/科幻",
        "value": "future_sci_fi",
        "description": "未来科技、赛博、太空、实验",
    },
    {
        "label": "架空/奇幻",
        "value": "fictional_fantasy",
        "description": "架空世界、魔法、异世界、神话",
    },
    {
        "label": "民俗/乡村",
        "value": "folk_rural",
        "description": "村落、民俗仪式、乡土、禁忌",
    },
    {
        "label": "西方复古",
        "value": "western_vintage",
        "description": "欧式庄园、古堡、宴会、复古西方",
    },
    {"label": "未识别", "value": "unknown", "description": "暂未判断时代"},
]

REGION_TYPE_OPTIONS: list[TaxonomyOption] = [
    {"label": "中国", "value": "china", "description": "中国背景或中式审美"},
    {"label": "日本", "value": "japan", "description": "日本背景或日式审美"},
    {"label": "欧美", "value": "western", "description": "欧洲、美国或西式审美"},
    {
        "label": "东南亚",
        "value": "southeast_asia",
        "description": "东南亚地域与文化元素",
    },
    {
        "label": "中东/沙漠",
        "value": "middle_east_desert",
        "description": "中东、沙漠、楼兰、异域风格",
    },
    {
        "label": "架空世界",
        "value": "fictional_world",
        "description": "非真实国家地域的架空世界",
    },
    {"label": "未知", "value": "unknown", "description": "暂不判断国家/地域"},
]

MOOD_TYPE_OPTIONS: list[TaxonomyOption] = [
    {"label": "悬疑", "value": "suspense", "description": "未知、谜团、危险感"},
    {"label": "惊悚", "value": "thriller", "description": "紧张、刺激、心理压迫与不安"},
    {"label": "危险", "value": "dangerous", "description": "威胁、冲突、失控风险"},
    {"label": "诡异", "value": "eerie", "description": "反常、幽暗、不合常理"},
    {"label": "冷峻", "value": "austere", "description": "克制、疏离、冷色调张力"},
    {"label": "暧昧", "value": "ambiguous", "description": "关系张力、秘密情感"},
    {"label": "压抑", "value": "oppressive", "description": "低气压、沉重、束缚"},
    {"label": "欢乐", "value": "joyful", "description": "轻松、搞笑、活跃"},
    {"label": "轻松", "value": "relaxed", "description": "舒缓、亲切、低压力"},
    {
        "label": "热闹",
        "value": "lively",
        "description": "多人互动、喧闹、活跃、有现场感",
    },
    {"label": "治愈", "value": "healing", "description": "温柔、安抚、希望与情绪修复"},
    {"label": "梦幻", "value": "dreamy", "description": "幻想、童话、轻盈、超现实"},
    {
        "label": "夸张",
        "value": "exaggerated",
        "description": "强表情、强动作、戏剧化反差",
    },
    {"label": "喜剧", "value": "comedic", "description": "幽默、闹剧、综艺感"},
    {"label": "荒诞", "value": "absurd", "description": "黑色幽默、闹剧、反差"},
    {"label": "热血", "value": "passionate", "description": "燃、对抗、行动感"},
    {"label": "冒险", "value": "adventurous", "description": "探索、未知、旅程与挑战"},
    {
        "label": "史诗",
        "value": "epic_adventure",
        "description": "传奇、英雄、宏大叙事与命运感",
    },
    {"label": "催泪", "value": "tearjerker", "description": "伤感、离别、情绪释放"},
    {"label": "孤独", "value": "lonely", "description": "空镜、背影、疏离"},
    {"label": "恐惧", "value": "fear", "description": "惊悚、压迫、阴影"},
    {"label": "宏大", "value": "epic", "description": "家国、史诗、命运感"},
    {"label": "浪漫", "value": "romantic", "description": "爱情、温柔、亲密"},
    {"label": "紧张", "value": "tense", "description": "冲突、倒计时、对峙"},
]

COMPOSITION_TYPE_OPTIONS: list[TaxonomyOption] = [
    {"label": "中心人物", "value": "center_character", "description": "主体人物居中"},
    {"label": "人物群像", "value": "group_portrait", "description": "多人角色关系展示"},
    {"label": "单人半身", "value": "single_bust", "description": "单角色半身/卡片图"},
    {
        "label": "双人剪影",
        "value": "couple_silhouette",
        "description": "双人关系、剪影主体",
    },
    {
        "label": "窗前逆光",
        "value": "window_backlight",
        "description": "窗户背景、人物轮廓光",
    },
    {"label": "门缝窥视", "value": "door_peeking", "description": "门/窗/帘形成窥视感"},
    {
        "label": "长廊透视",
        "value": "corridor_perspective",
        "description": "空间纵深和压迫",
    },
    {
        "label": "桌面道具",
        "value": "tabletop_props",
        "description": "俯视桌面、道具线索",
    },
    {"label": "大场景", "value": "wide_scene", "description": "环境优先、人物较小"},
    {"label": "分割构图", "value": "split_screen", "description": "阵营/双线/对照关系"},
    {"label": "侧边留白", "value": "side_blank", "description": "左/右侧留出文字区"},
    {
        "label": "上下留白",
        "value": "top_bottom_blank",
        "description": "顶部/底部用于排版",
    },
]

TAXONOMY_VALUE_ALIASES: TaxonomyAliases = {
    "styleTypes": {
        "realistic_card": "cinematic_realistic",
        "dark_cinematic": "cinematic_realistic",
        "watercolor_emotion": "cinematic_realistic",
        "guochao_illustration": "chinese_illustration",
        "gongbi_ancient": "chinese_illustration",
        "japanese_anime": "anime_illustration",
        "comic_cartoon": "cartoon_comic",
        "minimal_poster": "minimal_design",
        "collage_retro": "minimal_design",
        "cyberpunk": "cinematic_realistic",
    },
    "eraTypes": {
        "republic_china": "republic_modern",
        "ancient_china": "ancient",
        "modern_city": "modern",
        "campus": "modern",
        "japanese_modern": "modern",
        "sci_fi": "future_sci_fi",
        "fantasy": "fictional_fantasy",
        "folk_horror": "folk_rural",
        "european_manor": "western_vintage",
    },
}


def guess_usage_type(relative_path: str, file_name: str) -> str:
    """根据文件名/路径猜测图片用途，前端仍允许用户手动修改。"""

    text = f"{relative_path}/{file_name}".lower()
    if any(key in text for key in ["海报", "主图", "poster", "main"]):
        return "main_poster"
    if any(key in text for key in ["详情", "detail", "场景"]):
        return "detail"
    if any(key in text for key in ["人物", "角色", "character", "立绘"]):
        return "character"
    if any(key in text for key in ["朋友圈", "小红书", "宣传", "moments"]):
        return "moments"
    if any(key in text for key in ["banner", "横版"]):
        return "banner"
    if any(key in text for key in ["logo", "标题"]):
        return "logo"
    if any(key in text for key in ["道具", "线索", "prop"]):
        return "prop"
    return "other"


def canonical_taxonomy_value(group: str, value: str | None) -> str | None:
    """把历史细分类映射到当前粗分类。

    前端展示、后端筛选、后续传给 LLM 时都应该优先使用规范值，
    这样旧数据不会因为枚举收敛而渲染成英文。
    """

    if value is None:
        return None
    return TAXONOMY_VALUE_ALIASES.get(group, {}).get(value, value)


def values_for_taxonomy_filter(group: str, value: str | None) -> list[str]:
    """返回筛选某个规范值时应同时命中的历史值。"""

    if not value:
        return []
    canonical_value = canonical_taxonomy_value(group, value)
    values = {value, canonical_value}
    values.update(
        legacy_value
        for legacy_value, mapped_value in TAXONOMY_VALUE_ALIASES.get(group, {}).items()
        if mapped_value == canonical_value
    )
    return [item for item in values if item]


def taxonomy_payload() -> dict[str, object]:
    """返回前端上传/筛选要用的全部标签。"""

    return {
        "scriptTags": SCRIPT_TAG_OPTIONS,
        "usageTypes": USAGE_TYPE_OPTIONS,
        "styleTypes": STYLE_TYPE_OPTIONS,
        "eraTypes": ERA_TYPE_OPTIONS,
        "regionTypes": REGION_TYPE_OPTIONS,
        "moodTypes": MOOD_TYPE_OPTIONS,
        "compositionTypes": COMPOSITION_TYPE_OPTIONS,
        "aliases": TAXONOMY_VALUE_ALIASES,
    }
