"""Reusable live-game skill packages and curated build templates."""
from __future__ import annotations

from copy import deepcopy

from .core import DataError


_BASE_SKILL_TEMPLATES = (
    {
        "id": "fire_sword",
        "name": "火剑流",
        "summary": "流血引爆缩短身法冷却，火狐铺烈焰后叠加伤害。",
        "source": "https://www.taptap.cn/moment/619147536988376225",
        "slots": (
            ("武技", ("月影剑",), ("流血效果", "流血层数"), ("剑数量", "冷却")),
            ("绝技", ("绝影剑",), ("引爆流血", "身法冷却"), ("冷却",)),
            ("身法", ("火身法",), ("火狐", "烈焰"), ("火狐数量", "冷却", "灵力消耗")),
            ("神通", ("烈火凤",), ("持续时间", "烈焰中伤害降低"), ("冷却",)),
            ("秘卷", ("火秘卷",), ("烈焰", "伤害"), ()),
            ("神功", ("剑神功",), ("身法", "神通冷却"), ()),
            ("大法", ("火大法", "剑大法"), (), ("武技冷却", "身法冷却", "绝技冷却")),
        ),
    },
    {
        "id": "wind_sword",
        "name": "风剑流",
        "summary": "流血绝技缩短风身法冷却，依靠身法无敌窗口稳定循环。",
        "source": "https://www.taptap.cn/moment/619147241021505745",
        "slots": (
            ("武技", ("清风剑", "月影剑"), ("流血",), ("冷却", "流血层数")),
            ("绝技", ("绝影剑",), ("引爆流血", "身法冷却"), ("冷却",)),
            ("身法", ("风身法",), ("无敌",), ("持续时间", "冷却")),
            ("神功", ("剑神功",), (), ("身法冷却", "神通冷却")),
            ("大法", ("剑大法",), (), ("武技冷却", "身法冷却", "绝技冷却")),
        ),
    },
    {
        "id": "water_sword",
        "name": "流水剑",
        "summary": "清风剑叠流血、绝影剑减身法冷却，以水身法和骤天剑形成循环。",
        "source": "https://www.taptap.cn/moment/619012606908173138",
        "slots": (
            ("武技", ("清风剑",), ("流血概率", "流血持续时间"), ("冷却",)),
            ("绝技", ("绝影剑",), ("引爆流血", "身法冷却"), ("冷却",)),
            ("身法", ("水身法",), ("持续时间",), ("灵力消耗", "冷却")),
            ("神通", ("骤天剑",), ("神通冷却", "身法冷却"), ("灵力消耗", "无敌持续时间")),
            ("秘卷", ("剑秘卷",), ("流血持续时间",), ()),
        ),
    },
    {
        "id": "fire_blade",
        "name": "火刀",
        "summary": "烈火刀快速叠血刃，断斩持续引爆，烈焰触发火秘卷增伤。",
        "source": "https://www.taptap.cn/moment/601869089962459983",
        "slots": (
            ("武技", ("烈火刀",), ("血刃",), ("冷却", "刀痕", "血刃层数", "血刃伤害")),
            ("绝技", ("断斩",), ("冷却",), ("单一敌人", "武技冷却", "吸血")),
            ("身法", ("火身法",), ("生成烈焰",), ("冷却", "武技冷却", "火狐数量")),
            ("神通", ("火神通",), (), ("冷却", "持续时间", "减伤")),
            ("秘卷", ("火秘卷",), ("烈焰", "伤害"), ()),
            ("大法", ("剑大法",), (), ("武技冷却", "绝技冷却", "身法冷却")),
        ),
    },
    {
        "id": "whirlwind_blade",
        "name": "旋风刀",
        "summary": "旋风刀环身输出，以狂血斩/狂刀引爆血刃并堆叠减冷却。",
        "source": "https://www.taptap.cn/moment/601869089962459983",
        "slots": (
            ("武技", ("旋风刀",), ("血刃",), ("冷却", "连斩", "范围")),
            ("绝技", ("狂血斩", "狂刀"), ("引爆血刃",), ("武技冷却", "吸血", "伤害")),
            ("身法", ("枪身法",), ("武技冷却",), ("破甲", "破势", "身法冷却")),
            ("神通", ("剑神通",), ("武技冷却",), ("数量", "冷却")),
            ("秘卷", ("拳秘卷",), (), ("护盾", "铜皮", "冷却")),
            ("神功", ("指神功",), (), ("单一敌人", "武技冷却")),
            ("大法", ("剑大法",), (), ("武技冷却", "身法冷却", "绝技冷却")),
        ),
    },
    {
        "id": "collapse_fire_fist",
        "name": "崩山火拳",
        "summary": "以崩山拳为核心的拳火混合模板；词条以护盾、爆发和烈焰联动优先。",
        "source": "https://www.taptap.cn/moment/619206131171985344",
        "slots": (
            ("绝技", ("崩山拳",), ("护盾", "伤害"), ("冷却",)),
            ("身法", ("火身法",), ("生成烈焰",), ("火狐数量", "冷却")),
            ("秘卷", ("拳秘卷", "火秘卷"), (), ("护盾", "烈焰", "伤害")),
        ),
    },
    {
        "id": "soft_rice",
        "name": "软饭流（关系辅助）",
        "summary": "攻略核心是高修为关系经营；技能包仅保留前期开荒推荐的剑系组合。",
        "source": "https://www.taptap.cn/moment/614779851215210583",
        "slots": (
            ("武技", ("清风剑", "月影剑"), (), ("冷却",)),
            ("绝技", ("绝影剑",), (), ("冷却",)),
        ),
    },
    {
        "id": "soul_dragon_spear",
        "name": "噬魂龙枪（视频版）",
        "summary": "破势枪法配合火身法、火神通与火秘卷；优先保留来源角色完整词条。",
        "source": "https://www.bilibili.com/video/BV1RifUYUEUA/",
        "slots": (
            ("武技", ("穿心矛", "飞龙枪"), ("破势",), ("冷却", "破甲")),
            ("绝技", ("真龙破", "啸龙破"), ("消耗破势",), ("充能", "冷却")),
            ("身法", ("火身法",), ("生成烈焰",), ("冷却", "火狐数量")),
            ("神通", ("天龙阵", "火神通"), (), ("冷却", "持续时间")),
            ("秘卷", ("火秘卷",), ("烈焰", "伤害"), ()),
        ),
    },
    {
        "id": "lotus_sword",
        "name": "青莲剑仙（视频版）",
        "summary": "剑系与莲花剑意组合；复制时以来源角色实际技能和完整词条为准。",
        "source": "https://space.bilibili.com/263687361/lists/1407336?type=season",
        "slots": (
            ("武技", ("月影剑", "清风剑"), (), ("冷却", "流血", "弹道")),
            ("绝技", ("绝影剑",), (), ("冷却", "流血")),
            ("神通", ("万神剑", "骤天剑"), (), ("冷却", "无敌")),
            ("心法", ("剑大法", "剑秘卷", "剑神功"), (), ("冷却", "增伤")),
        ),
    },
    {
        "id": "water_firefly",
        "name": "万星飞萤·极致水修（视频版）",
        "summary": "水系持续输出模板；读取视频同款来源角色后可完整保留词条和修炼。",
        "source": "https://space.bilibili.com/263687361/lists/1407336?type=season",
        "slots": (
            ("灵技", ("水灵术",), (), ("冷却", "数量", "冻结")),
            ("绝技", ("冰刺术", "灵涌术"), (), ("冷却", "灵涌")),
            ("身法", ("水身法",), (), ("持续时间", "冷却")),
            ("神通", ("万星飞萤",), (), ("冷却", "持续时间")),
            ("心法", ("水大法", "水秘卷", "水神功"), (), ("冷却", "增伤")),
        ),
    },
    {
        "id": "slay_heaven_fire_fist",
        "name": "弑天火拳（视频版）",
        "summary": "拳系爆发与火系烈焰联动模板。",
        "source": "https://space.bilibili.com/263687361/lists/1407336?type=season",
        "slots": (
            ("武技", ("定气拳", "铜皮拳"), (), ("护盾", "拳影", "冷却")),
            ("绝技", ("崩山拳",), ("护盾", "伤害"), ("冷却",)),
            ("身法", ("火身法",), ("生成烈焰",), ("冷却", "火狐数量")),
            ("秘卷", ("拳秘卷", "火秘卷"), (), ("护盾", "烈焰", "增伤")),
        ),
    },
    {
        "id": "divine_thunder_sword",
        "name": "神剑御雷（视频版）",
        "summary": "剑系叠层与雷系爆发组合，优先匹配来源角色中的同名功法。",
        "source": "https://www.bilibili.com/video/BV12AxM6YEC3/",
        "slots": (
            ("武技", ("月影剑", "清风剑"), (), ("冷却", "流血", "弹道")),
            ("绝技", ("绝影剑",), (), ("冷却",)),
            ("身法", ("雷身法", "剑身法"), (), ("冷却", "雷球")),
            ("神通", ("天雷劫", "万神剑"), (), ("冷却", "伤害")),
            ("心法", ("雷秘卷", "剑大法"), (), ("雷涌", "冷却", "增伤")),
        ),
    },
    {
        "id": "soul_frenzy_blade",
        "name": "噬魂狂刀（视频版）",
        "summary": "血刃高频引爆与刀系吸血模板。",
        "source": "https://space.bilibili.com/263687361/lists/1407336?type=season",
        "slots": (
            ("武技", ("烈火刀", "旋风刀"), ("血刃",), ("冷却", "范围")),
            ("绝技", ("狂血斩", "断斩", "醉饮狂刀"), ("引爆血刃",), ("冷却", "吸血")),
            ("身法", ("刀身法", "火身法"), (), ("冷却", "武技冷却")),
            ("心法", ("刀大法", "刀秘卷", "刀神功"), (), ("吸血", "冷却", "增伤")),
        ),
    },
    {
        "id": "prison_heaven_finger",
        "name": "大荒囚天指（视频版）",
        "summary": "指系内虚与爆发组合；适合从已成型角色原样打包。",
        "source": "https://space.bilibili.com/263687361/upload/video",
        "slots": (
            ("灵技", ("轮回指", "无相指"), (), ("内虚", "冷却")),
            ("绝技", ("幽空爆", "封魔指"), (), ("内虚", "冷却", "伤害")),
            ("神通", ("冲虚指", "神脉指"), (), ("冷却", "持续时间")),
            ("心法", ("指大法", "指秘卷", "指神功"), (), ("内虚", "冷却", "增伤")),
        ),
    },
)


_FULL_BUILD_SOURCE = "https://www.taptap.cn/moment/846846504906785623?group_id=775859"
_FULL_BUILD_REFERENCE = "https://tieba.baidu.com/p/9544643534?fr=frs"

_MARTIAL_BUILDS = (
    ("sword", "剑", ("月影剑", "清风剑"), "流血", ("绝影剑",), "引爆流血",
     ("剑身法",), ("万神剑",), "剑斩流转"),
    ("blade", "刀", ("血刃刀", "烈火刀"), "血刃", ("断斩",), "引爆血刃",
     ("刀身法",), ("魔煞刀",), "血刃流转"),
    ("fist", "拳", ("定气拳",), "碎骨", ("崩山拳",), "消耗护盾",
     ("拳身法",), ("震山河",), "碎骨流转"),
    ("palm", "掌", ("青涛掌",), "内伤", ("惊虹掌",), "引爆内伤",
     ("土身法", "掌身法"), ("归神掌",), "内伤流转"),
    ("finger", "指", ("轮回指",), "内虚", ("幽空爆",), "引爆内虚",
     ("指身法",), ("洞玄指",), "内虚流转"),
    ("spear", "枪", ("穿心矛",), "破势", ("真龙破",), "消耗破势",
     ("天龙阵", "枪身法"), ("过龙门",), "破势流转"),
)

_ELEMENT_BUILDS = (
    ("pure", "纯", None, None, "本系循环"),
    ("fire", "火", ("火身法",), ("丹凤吟", "烈火凤", "火神通"), "烈焰持续增伤"),
    ("water", "水", ("水身法",), ("潜龙渊",), "分身冻结控场"),
    ("thunder", "雷", ("雷身法",), ("踏云行",), "乱流雷击爆发"),
    ("earth", "土", ("土身法", "化尘决"), ("震山河",), "护盾站场"),
)

_ELEMENT_TERMS = {
    "fire": (("火狐", "烈焰"), ("冷却", "火狐数量"), ("范围", "灼烧", "火属性增伤")),
    "water": (("水分身", "寒霜"), ("冷却", "分身数量", "持续时间"), ("冻结", "灵湖", "防御")),
    "thunder": (("雷涌", "乱流"), ("冷却", "雷涌数量"), ("雷击", "雷兽", "范围")),
    "earth": (("开脉", "护盾"), ("冷却", "移速", "防御"), ("护盾", "暴击", "范围")),
}


def _full_build_templates():
    """Generate the six martial schools and their four elemental hybrids."""
    rows = []
    for (school_id, school, weapon_names, status, ultimate_names, ultimate_status,
         pure_motion, pure_divine, destiny) in _MARTIAL_BUILDS:
        for element_id, element, motion_names, divine_names, mechanism in _ELEMENT_BUILDS:
            is_pure = element_id == "pure"
            motion = pure_motion if is_pure else motion_names
            divine = pure_divine if is_pure else divine_names
            slots = [
                ("武技", weapon_names, (status,), ("冷却", "层数", "数量", "增伤")),
                ("绝技", ultimate_names, (ultimate_status,), ("冷却", "增伤", "范围")),
            ]
            if is_pure:
                slots.extend((
                    ("身法", motion, (), ("冷却", "移速", "减伤")),
                    ("神通", divine, (), ("冷却", "范围", "增伤")),
                ))
            else:
                required, movement_terms, divine_terms = _ELEMENT_TERMS[element_id]
                slots.extend((
                    ("身法", motion, required, movement_terms),
                    ("神通", divine, (), divine_terms),
                ))
            slots.extend((
                ("大法", (f"{school}大法",), (), ("武技冷却", "绝技冷却", "身法冷却")),
                ("秘卷", (f"{school}秘卷",), (status,), ("层数", "持续时间", "增伤")),
                ("神功", (f"{school}神功",), (), ("冷却", "增伤")),
            ))
            if not is_pure:
                slots.append(("元素秘卷", (f"{element}秘卷",), (), ("增伤", "冷却")))
            rows.append({
                "id": f"guide_{element_id}_{school_id}",
                "name": f"全流派·{element}{school}",
                "summary": f"{mechanism}；逆天改命优先武法系、{destiny}及对应{element if not is_pure else school}系强化。",
                "source": _FULL_BUILD_SOURCE,
                "reference": _FULL_BUILD_REFERENCE,
                "slots": tuple(slots),
            })
    return tuple(rows)


SKILL_TEMPLATES = _BASE_SKILL_TEMPLATES + _full_build_templates()


def templates():
    return deepcopy(SKILL_TEMPLATES)


def template_by_id(template_id):
    for template in SKILL_TEMPLATES:
        if template["id"] == template_id:
            return deepcopy(template)
    raise DataError("未找到所选技能包模板")


def normalize_runtime_skill(skill):
    if not isinstance(skill, dict):
        raise DataError("功法数据格式无效")
    raw = skill.get("rawValues")
    if not isinstance(raw, list) or not all(isinstance(value, int) for value in raw):
        raise DataError("功法缺少可复制的原始数据")
    return {
        "soleId": str(skill.get("soleId") or ""),
        "name": str(skill.get("name") or "未命名功法"),
        "type": int(skill.get("type") or 0),
        "level": int(skill.get("level") or 0),
        "baseId": int(skill.get("baseId") or (raw[0] if raw else 0)),
        "grade": int(skill.get("grade") or (raw[1] if len(raw) > 1 else 0)),
        "exp": int(skill.get("exp") or 0),
        "rawValues": list(raw),
    }


def build_package(name, source_role, skills, template_id=None):
    rows = [normalize_runtime_skill(skill) for skill in skills]
    if not rows:
        raise DataError("来源角色没有可打包的功法")
    return {
        "format": "XuanShu.SkillPackage/1",
        "version": "1.1.3",
        "name": str(name or "未命名技能包"),
        "sourceRole": dict(source_role or {}),
        "templateId": template_id,
        "skills": rows,
    }


def select_template_skills(template, skills):
    """Match template slots to source skills by displayed name, preserving one skill per slot."""
    matched, missing = [], []
    used = set()
    for slot, names, _required, _recommended in template["slots"]:
        found = None
        for index, skill in enumerate(skills):
            if index in used:
                continue
            actual = str(skill.get("name") or "")
            if any(name in actual or actual in name for name in names if actual):
                found = (index, skill)
                break
        if found:
            used.add(found[0])
            matched.append(found[1])
        else:
            missing.append(f"{slot}：{' / '.join(names)}")
    return matched, missing
