"""Verified legacy fields, save discovery and reference-inspired shortcuts."""
from __future__ import annotations

from dataclasses import dataclass
from bisect import bisect_right
from functools import lru_cache
import copy
import json
import os
from pathlib import Path
import re
import sys
import secrets
import string

from .core import FIELDS, DataError, find_roles, get_at

UNIT_CACHE = "O33a@9fkh++YwffVNeV1RA==.cache"
WORLD_CACHE = "eMZk7avfjaaSiFBwLwtZHg==.cache"
SCHOOL_CACHE = "soegnXJ65qU3ZS4O9xLDgg==.cache"
DEFAULT_GAME = Path(r"F:\steam\steamapps\common\鬼谷八荒")
POTMON_LIST_PATH = ("devilDemonData", "potmonData", "potMonList")


def save_root():
    return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "AppData/LocalLow/guigugame/guigubahuang/Steam/CacheData"


@dataclass
class SaveSlot:
    label: str
    path: Path
    modified: float
    size: int


def discover_saves(root=None):
    root = Path(root) if root is not None else save_root()
    if not root.is_dir():
        return []
    result = []
    for folder in root.iterdir():
        if not folder.is_dir() or not folder.name.split("_", 1)[0].isdigit():
            continue
        path = folder / UNIT_CACHE
        if not path.is_file():
            continue
        stat = path.stat()
        result.append(SaveSlot(folder.name, path, stat.st_mtime, stat.st_size))
    return sorted(result, key=lambda slot: slot.modified, reverse=True)


def _new_unit_id(existing):
    alphabet = string.ascii_letters + string.digits
    for _ in range(1000):
        token = "".join(secrets.choice(alphabet) for _ in range(6))
        if token not in existing:
            existing.add(token)
            return token
    raise DataError("无法生成不重复的角色编号")


def _rewrite_import_ids(value, mapping):
    if isinstance(value, dict):
        return {mapping.get(key, key) if isinstance(key, str) else key: _rewrite_import_ids(item, mapping)
                for key, item in value.items()}
    if isinstance(value, list):
        return [_rewrite_import_ids(item, mapping) for item in value]
    if isinstance(value, str):
        return mapping.get(value, value)
    return value


def _sanitize_import_relations(role, mapping, keep_internal):
    relations = role.get("x") if isinstance(role, dict) else None
    if not isinstance(relations, dict):
        return
    relation_fields = ("q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "a")
    allowed = set(mapping.values()) if keep_internal else set()
    for key in relation_fields:
        value = relations.get(key)
        if isinstance(value, list):
            relations[key] = [unit_id for unit_id in value if isinstance(unit_id, str) and unit_id in allowed]
        elif isinstance(value, str):
            relations[key] = value if value in allowed else ""
    intimacy = relations.get("d")
    if isinstance(intimacy, dict):
        relations["d"] = {unit_id: amount for unit_id, amount in intimacy.items() if unit_id in allowed}
    if type(relations.get("s")) in (int, float):
        relations["s"] = type(relations["s"])(0)


def import_roles(destination_document, source_document, source_paths, keep_internal_relations=True):
    """Clone selected roles with fresh IDs and no references to the source save."""
    if destination_document.source == source_document.source:
        raise DataError("来源存档不能与当前存档相同")
    target = destination_document.data.get("allUnit") if isinstance(destination_document.data, dict) else None
    if not isinstance(target, dict):
        raise DataError("当前存档缺少可写入的 allUnit 角色容器")
    unique_paths = []
    seen_paths = set()
    for path in source_paths:
        path = tuple(path)
        if path not in seen_paths:
            seen_paths.add(path)
            unique_paths.append(path)
    if not unique_paths:
        raise DataError("请至少选择一个来源角色")
    source_roles = []
    for path in unique_paths:
        try:
            role = get_at(source_document.data, path)
        except (KeyError, IndexError, TypeError) as exc:
            raise DataError("来源角色列表已经变化，请重新打开导入面板") from exc
        if not isinstance(role, dict) or not path or not isinstance(path[-1], str):
            raise DataError("所选来源角色结构不兼容")
        source_roles.append((path[-1], role))
    existing = set(target)
    id_mapping = {old_id: _new_unit_id(existing) for old_id, _role in source_roles}
    imported = []
    for old_id, source_role in source_roles:
        new_id = id_mapping[old_id]
        role = _rewrite_import_ids(copy.deepcopy(source_role), id_mapping)
        if "u" in role:
            role["u"] = ""
        _sanitize_import_relations(role, id_mapping, bool(keep_internal_relations))
        destination_document.add_mapping(("allUnit",), new_id, role)
        q = role.get("q", {})
        names = q.get("q", []) if isinstance(q, dict) else []
        name = "".join(names[:2]) if isinstance(names, list) else new_id
        imported.append({"old_id": old_id, "new_id": new_id, "name": name})
    return imported


class Catalog:
    def __init__(self):
        self.props = {}
        self.types = {}
        self.grades = {}
        self.skills = {}
        self.born_luck = {}
        self.reverse_fate = {}
        self.taoist_seeds = {}
        self.taoist_levels = {}
        self.in_traits = {}
        self.out_traits = {}
        self.hobbies = {}
        self.appellations = {}
        self.souls = {}
        self.directions = {}
        self.skill_types = {}
        self.skill_info = {}
        self.skill_grades = {}
        self.skill_effects = []
        self.skill_values = {}
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        path = base / "catalog.json"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            self.props = data.get("props", {})
            self.types = data.get("types", {})
            self.grades = data.get("grades", {})
            self.skills = data.get("skills", {})
        reference = base / "reference_catalog.json"
        if reference.is_file():
            data = json.loads(reference.read_text(encoding="utf-8"))
            for name in ("born_luck", "reverse_fate", "taoist_seeds", "taoist_levels", "in_traits",
                         "out_traits", "hobbies", "appellations", "souls", "directions",
                         "skill_types", "skill_info", "skill_grades", "skill_effects", "skill_values"):
                setattr(self, name, data.get(name, {}))

    def prop(self, prop_id):
        return self.props.get(str(prop_id), {"name": f"未知物品 #{prop_id}", "type": "未分类"})


def role_info(role, catalog):
    q = role.get("q", {})
    sex = {1: "男", 2: "女"}.get(q.get("r"), "未知")
    grade_id = str(q.get("d", ""))
    grade = catalog.grades.get(grade_id, f"境界 #{grade_id}")
    age = q.get("y")
    age = f"{int(age) // 12} 岁 {int(age) % 12} 月" if type(age) in (int, float) else "年龄未知"
    return {"sex": sex, "grade": grade, "age": age, "school": str(role.get("u", "")),
            "position": f"({role.get('t', '?')}, {role.get('y', '?')})"}


_PINYIN_INITIAL_RANGES = (
    (-20319, "a"), (-20284, "b"), (-19776, "c"), (-19219, "d"), (-18711, "e"),
    (-18527, "f"), (-18240, "g"), (-17923, "h"), (-17418, "j"), (-16475, "k"),
    (-16213, "l"), (-15641, "m"), (-15166, "n"), (-14923, "o"), (-14915, "p"),
    (-14631, "q"), (-14150, "r"), (-14091, "s"), (-13319, "t"), (-12839, "w"),
    (-12557, "x"), (-11848, "y"), (-11056, "z"),
)


@lru_cache(maxsize=8192)
def pinyin_initials(text):
    """Return searchable GB2312-style pinyin initials without an optional runtime dependency."""
    result = []
    for character in str(text):
        if character.isascii():
            if character.isalnum():
                result.append(character.casefold())
            continue
        try:
            encoded = character.encode("gbk")
        except UnicodeEncodeError:
            continue
        if len(encoded) != 2:
            continue
        code = encoded[0] * 256 + encoded[1] - 65536
        position = bisect_right(_PINYIN_INITIAL_RANGES, (code, chr(0x10ffff))) - 1
        if position >= 0:
            result.append(_PINYIN_INITIAL_RANGES[position][1])
    return "".join(result)


@lru_cache(maxsize=4)
def potmon_catalog(game_path=str(DEFAULT_GAME)):
    root = Path(game_path) / "Mod/modFQA/配置修改教程/配置（只读）Json格式"

    def read(name):
        path = root / name
        if not path.is_file():
            return []
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return value if isinstance(value, list) else []

    local = {str(row.get("key")): str(row.get("ch") or row.get("tc") or row.get("key"))
             for row in read("LocalText.json") if isinstance(row, dict) and row.get("key")}
    ranges = {str(row.get("id")): row for row in read("PotmonPropertyScale.json") if isinstance(row, dict)}
    species = {}
    for row in read("PotmonBase.json"):
        if not isinstance(row, dict) or not str(row.get("id", "")).isdigit():
            continue
        potmon_id = int(row["id"])
        species[potmon_id] = {
            "name": local.get(str(row.get("name")), str(row.get("name") or f"壶妖 #{potmon_id}")),
            "race": local.get(str(row.get("race")), str(row.get("race") or f"种族 #{potmon_id}")),
            "ranges": ranges.get(str(potmon_id), {}),
        }
    battle = {}
    for row in read("PotmonBattleSkill.json"):
        if not isinstance(row, dict) or not str(row.get("skillID", "")).isdigit():
            continue
        skill_id = int(row["skillID"])
        battle[skill_id] = local.get(f"skill_name_middle{skill_id}") or local.get(
            f"GodEyeSkills_name_{skill_id}") or f"战斗技能 #{skill_id}"
    life = {}
    for row in read("PotmonSkill.json"):
        if not isinstance(row, dict) or not str(row.get("id", "")).isdigit():
            continue
        skill_id = int(row["id"])
        life[skill_id] = local.get(str(row.get("name"))) or f"生活技能 #{skill_id}"
    skills = ([{"id": key, "name": value, "type": "战斗技能"} for key, value in battle.items()] +
              [{"id": key, "name": value, "type": "生活技能"} for key, value in life.items()])
    return {"species": species, "battle_skills": battle, "life_skills": life, "skills": skills}


POTMON_PROPERTY_FIELDS = {
    "体力": "hp", "攻击": "atk", "防御": "def", "会心": "crit", "护心": "guard",
    "功抗": "pfr", "暴击": "critV", "抗暴": "guardV", "灵抗": "mfr",
}


def potmon_records(document, game_path=str(DEFAULT_GAME)):
    try:
        values = get_at(document.data, POTMON_LIST_PATH)
    except (KeyError, IndexError, TypeError):
        return []
    if not isinstance(values, list):
        return []
    catalog = potmon_catalog(str(game_path))
    result = []
    for index, value in enumerate(values):
        if not isinstance(value, dict):
            continue
        potmon_id = value.get("id")
        species = catalog["species"].get(potmon_id, {"name": f"壶妖 #{potmon_id}", "race": f"种族 #{potmon_id}", "ranges": {}})
        conver = value.get("converState", 0)
        transformed = bool(value.get("unitId")) or conver in (1, 2)
        name = str(value.get("fixName") or species["name"])
        result.append({
            "index": index, "path": POTMON_LIST_PATH + (index,), "sole_id": str(value.get("soleId", "")),
            "id": potmon_id, "name": name, "race": species["race"], "sex": {1: "男", 2: "女"}.get(value.get("sex"), "未知"),
            "health": {0: "正常", 1: "受伤", 2: "濒危"}.get(value.get("health"), f"状态 {value.get('health')}"),
            "contract": conver == 2, "transformed": transformed,
            "transform_state": "已化形" if transformed else "未化形", "ranges": species.get("ranges", {}), "raw": value,
        })
    return result


def _validate_potmon_row(document, row):
    try:
        value = get_at(document.data, tuple(row["path"]))
    except (KeyError, IndexError, TypeError) as exc:
        raise DataError("壶妖列表已变化，请刷新后重试") from exc
    if not isinstance(value, dict) or str(value.get("soleId", "")) != str(row.get("sole_id", "")):
        raise DataError("壶妖列表已变化，请刷新后重试")
    return value


def set_potmon_contract(document, row, enabled):
    value = _validate_potmon_row(document, row)
    current = value.get("converState", 0)
    if enabled:
        if current == 0 and not value.get("unitId"):
            raise DataError("未化形的壶妖不能签订契约")
        target = 2
    else:
        target = 1 if current == 2 else current
    document.set_many([(tuple(row["path"]) + ("converState",), str(target))])


def update_potmon(document, row, name, sex, health, properties):
    value = _validate_potmon_row(document, row)
    if row.get("transformed"):
        raise DataError("已化形壶妖请到 NPC 列表修改；本页只计算未化形属性")
    sex_id = {"男": 1, "女": 2}.get(str(sex))
    health_id = {"正常": 0, "受伤": 1, "濒危": 2}.get(str(health))
    if sex_id is None or health_id is None:
        raise DataError("请选择有效的性别和健康状态")
    edits = [(tuple(row["path"]) + ("fixName",), str(name)),
             (tuple(row["path"]) + ("sex",), str(sex_id)),
             (tuple(row["path"]) + ("health",), str(health_id))]
    scale = value.get("monstPropertyScale")
    if not isinstance(scale, dict):
        raise DataError("壶妖属性范围结构缺失")
    for label, key in POTMON_PROPERTY_FIELDS.items():
        if key not in scale or scale[key] is None:
            continue
        try:
            amount = int(properties[label])
        except (KeyError, TypeError, ValueError) as exc:
            raise DataError(f"{label}必须填写整数") from exc
        configured = str(row.get("ranges", {}).get(key, ""))
        try:
            low, high = (int(part) for part in configured.split("_", 1))
        except (TypeError, ValueError):
            low, high = 1, 1000
        if not low <= amount <= high:
            raise DataError(f"{label}的正确范围是 {low} - {high}")
        old = str(scale[key])
        prefix = old.split("|", 1)[0] if "|" in old else "1"
        edits.append((tuple(row["path"]) + ("monstPropertyScale", key), f"{prefix}|{amount}"))
    document.set_many(edits)


def potmon_skills(document, row, game_path=str(DEFAULT_GAME)):
    value = _validate_potmon_row(document, row)
    catalog = potmon_catalog(str(game_path))
    result = []
    for field, label, names in (("battleSkills", "战斗技能", catalog["battle_skills"]),
                                ("lifeSkills", "生活技能", catalog["life_skills"])):
        skills = value.get(field, [])
        if not isinstance(skills, list):
            continue
        for index, skill_id in enumerate(skills):
            if type(skill_id) is int:
                result.append({"field": field, "index": index, "id": skill_id,
                               "type": label, "name": names.get(skill_id, f"{label} #{skill_id}")})
    return result


def add_potmon_skills(document, row, skills):
    value = _validate_potmon_row(document, row)
    added = 0
    for skill in skills:
        field = "battleSkills" if skill.get("type") == "战斗技能" else "lifeSkills"
        current = value.get(field)
        skill_id = skill.get("id")
        if not isinstance(current, list) or type(skill_id) is not int or skill_id in current:
            continue
        document.append(tuple(row["path"]) + (field,), skill_id)
        added += 1
        if field == "battleSkills" and type(value.get("battleSkillMax")) is int and len(current) > value["battleSkillMax"]:
            document.set_many([(tuple(row["path"]) + ("battleSkillMax",), str(len(current)))])
    return added


def delete_potmon_skills(document, row, skills):
    _validate_potmon_row(document, row)
    removed = 0
    for field in ("battleSkills", "lifeSkills"):
        indexes = sorted({skill["index"] for skill in skills if skill.get("field") == field}, reverse=True)
        for index in indexes:
            document.remove_at(tuple(row["path"]) + (field,), index)
            removed += 1
    return removed


def attribute_values(document, role_path):
    result = {}
    for label, field in FIELDS:
        path = tuple(field.split("."))
        try:
            value = get_at(document.data, tuple(role_path) + path)
        except (KeyError, TypeError, IndexError):
            continue
        if type(value) in (int, float):
            result[field] = value
    return result


def paste_attributes(document, role_path, values):
    allowed = {field for _, field in FIELDS}
    edits = []
    for field, value in values.items():
        if field not in allowed or type(value) not in (int, float):
            raise DataError("属性模板包含不支持的字段或类型")
        path = tuple(role_path) + tuple(field.split("."))
        try:
            old = get_at(document.data, path)
        except (KeyError, TypeError, IndexError):
            continue
        if type(old) is not type(value):
            raise DataError("属性类型与目标角色不一致")
        edits.append((path, str(value)))
    if not edits:
        raise DataError("没有可粘贴的相同属性")
    document.set_many(edits)
    return len(edits)


def refill(document, role_paths):
    pairs = [("x", "c"), ("v", "b"), ("n", "m"), ("l", "z"), ("5", "6"), ("qx", "qc")]
    edits = []
    for role_path in role_paths:
        role = get_at(document.data, role_path)
        q = role.get("q", {})
        for current, maximum in pairs:
            if current in q and maximum in q and type(q[current]) is int and type(q[maximum]) is int:
                if q[maximum] < 0:
                    raise DataError("状态上限为负，无法补满")
                # Modded saves can legitimately exceed a stored base maximum.
                # A refill must never reduce an existing value.
                if q[current] < q[maximum]:
                    edits.append((tuple(role_path) + ("q", current), str(q[maximum])))
    if not edits:
        return 0
    document.set_many(edits)
    return len(edits)


def inventory(document, role_path, catalog):
    try:
        items = get_at(document.data, tuple(role_path) + ("z", "allProps"))
    except (KeyError, IndexError, TypeError):
        return []
    if not isinstance(items, list):
        return []
    result = []
    for index, item in enumerate(items):
        w = item.get("w") if isinstance(item, dict) else None
        if not isinstance(w, list) or len(w) < 3 or w[0] != 1 or type(w[1]) is not int or type(w[2]) is not int:
            continue
        prop = catalog.prop(w[1])
        result.append({"index": index, "id": w[1], "quantity": w[2], "name": prop["name"],
                       "type": prop["type"], "path": tuple(role_path) + ("z", "allProps", index, "w", 2)})
    return result


def set_quantity(document, row, text):
    try:
        quantity = int(text)
    except ValueError as exc:
        raise DataError("数量需要填写整数") from exc
    if not 1 <= quantity <= 2**31 - 1:
        raise DataError("数量必须介于 1 和 2147483647；本页不支持删除物品")
    document.set_many([(row["path"], str(quantity))])


def delete_items(document, role_path, rows):
    """Delete selected ordinary inventory entries, highest index first so paths stay stable."""
    role_path = tuple(role_path)
    try:
        items = get_at(document.data, role_path + ("z", "allProps"))
    except (KeyError, IndexError, TypeError) as exc:
        raise DataError("角色背包结构缺失") from exc
    if not isinstance(items, list):
        raise DataError("角色背包结构不兼容")
    indexes = sorted({row.get("index") for row in rows if isinstance(row, dict)}, reverse=True)
    if not indexes or any(type(index) is not int or not 0 <= index < len(items) for index in indexes):
        raise DataError("请选择有效的背包物品")
    for index in indexes:
        item = items[index]
        expected = next((row for row in rows if row.get("index") == index), None)
        values = item.get("w") if isinstance(item, dict) else None
        if not expected or not isinstance(values, list) or len(values) < 3 or values[1] != expected.get("id"):
            raise DataError("背包内容已变化，请刷新后重新选择")
    for index in indexes:
        document.remove_at(role_path + ("z", "allProps"), index)
    return len(indexes)


def add_item(document, role_path, prop_id_text, quantity_text, catalog):
    try:
        prop_id = int(prop_id_text)
        quantity = int(quantity_text)
    except ValueError as exc:
        raise DataError("物品 ID 和数量必须是整数") from exc
    if not 1 <= prop_id <= 2**31 - 1:
        raise DataError("物品 ID 必须是正整数")
    if not 1 <= quantity <= 2**31 - 1:
        raise DataError("数量必须介于 1 和 2147483647")
    existing = inventory(document, role_path, catalog)
    if any(row["id"] == prop_id for row in existing):
        raise DataError("背包中已有该物品；请选择它并修改数量")
    path = tuple(role_path) + ("z", "allProps")
    token = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(6))
    document.append(path, {"q": token, "w": [1, prop_id, quantity], "e": ""})
    return catalog.prop(prop_id)


def installation_status(game_path):
    game = Path(game_path)
    required = {
        "游戏程序": game / "guigubahuang.exe",
        "MelonLoader": game / "MelonLoader",
        "游戏托管程序集": game / "MelonLoader/Managed/Assembly-CSharp.dll",
        "JSON 通信依赖": game / "MelonLoader/Managed/Newtonsoft.Json.dll",
    }
    status = {label: path.exists() for label, path in required.items()}
    status["玄枢 GameBridge 游戏客户端"] = any(
        (game / "Mods" / name).is_file()
        for name in ("XuanShu.GameBridge.dll", "GGBH.BridgeMod.dll")
    )
    return status


def discover_mods(game_path):
    """List locally exported mods without interpreting or executing their content."""
    root = Path(game_path) / "ModExportData"
    if not root.is_dir():
        return []
    result = []
    for folder in root.iterdir():
        if not folder.is_dir():
            continue
        files = sum(1 for path in folder.rglob("*") if path.is_file())
        result.append({"name": folder.name, "path": str(folder), "files": files})
    return sorted(result, key=lambda item: item["name"].casefold())


RELATION_FIELDS = {
    "q": "父母", "w": "子女", "e": "私生子女", "r": "兄弟姐妹",
    "t": "义父母", "y": "义子女", "u": "义兄弟姐妹", "i": "夫妻",
    "o": "道侣", "p": "师父", "a": "徒弟", "s": "对玩家好感",
}

RELATION_PAIRS = {
    "兄弟姐妹": ("r", "r"), "义兄弟姐妹": ("u", "u"), "道侣": ("o", "o"),
    "师父": ("p", "a"), "徒弟": ("a", "p"), "义父母": ("t", "y"), "义子女": ("y", "t"),
}

RELATION_KINDS = ("父母", "子女", "私生子女", "兄弟姐妹", "义父母", "义子女",
                  "义兄弟姐妹", "夫妻", "道侣", "师父", "徒弟", "好友")
FRIEND_KINDS = ("好友", "认识的人")


def add_relationship(document, root_path, target_path, kind, intimacy=300, bidirectional=True):
    root_path, target_path = tuple(root_path), tuple(target_path)
    if root_path == target_path:
        raise DataError("不能把角色与自己建立关系")
    try:
        intimacy = int(intimacy)
    except (TypeError, ValueError) as exc:
        raise DataError("好感值必须是整数") from exc
    if not -1000 <= intimacy <= 1000:
        raise DataError("好感值必须介于 -1000 和 1000")
    root, target = get_at(document.data, root_path), get_at(document.data, target_path)
    root_id, target_id = str(root_path[-1]), str(target_path[-1])
    rx, tx = root.get("x"), target.get("x")
    if not isinstance(rx, dict) or not isinstance(tx, dict):
        raise DataError("角色关系结构缺失")

    scalar_edits = []
    appends = []
    if kind in RELATION_PAIRS:
        left, right = RELATION_PAIRS[kind]
        if not isinstance(rx.get(left), list) or (bidirectional and not isinstance(tx.get(right), list)):
            raise DataError("目标关系字段结构不兼容")
        if target_id in rx[left] or (bidirectional and root_id in tx[right]):
            raise DataError("双方已经存在该关系")
        appends = [(root_path + ("x", left), target_id)]
        if bidirectional:
            appends.append((target_path + ("x", right), root_id))
    elif kind in ("子女", "私生子女"):
        left = "w" if kind == "子女" else "e"
        parents = tx.get("q")
        if not isinstance(rx.get(left), list) or (bidirectional and not isinstance(parents, list)):
            raise DataError("亲子关系字段结构不兼容")
        if target_id in rx[left] or (bidirectional and root_id in parents):
            raise DataError("双方已经存在该亲子关系")
        appends = [(root_path + ("x", left), target_id)]
        if bidirectional:
            try:
                slot = parents.index("")
            except ValueError as exc:
                raise DataError("目标角色的父母栏已满") from exc
            scalar_edits.append((target_path + ("x", "q", slot), root_id))
    elif kind == "父母":
        parents, children = rx.get("q"), tx.get("w")
        if not isinstance(parents, list) or (bidirectional and not isinstance(children, list)):
            raise DataError("亲子关系字段结构不兼容")
        if target_id in parents or (bidirectional and root_id in children):
            raise DataError("双方已经存在该亲子关系")
        try:
            slot = parents.index("")
        except ValueError as exc:
            raise DataError("当前角色的父母栏已满") from exc
        scalar_edits.append((root_path + ("x", "q", slot), target_id))
        if bidirectional:
            appends = [(target_path + ("x", "w"), root_id)]
    elif kind == "夫妻":
        if not isinstance(rx.get("i"), str) or (bidirectional and not isinstance(tx.get("i"), str)):
            raise DataError("夫妻字段结构不兼容")
        if rx["i"] or (bidirectional and tx["i"]):
            raise DataError("一方已有夫妻；请先使用替换功能")
        scalar_edits = [(root_path + ("x", "i"), target_id)]
        if bidirectional:
            scalar_edits.append((target_path + ("x", "i"), root_id))
    elif kind not in FRIEND_KINDS:
        raise DataError("不支持的关系类型")

    # Validate all writes before mutating either side.
    for path, _value in appends:
        if not isinstance(get_at(document.data, path), list):
            raise DataError("关系列表结构不兼容")
    owners = (root_path, target_path) if bidirectional else (root_path,)
    for owner_path in owners:
        if not isinstance(get_at(document.data, owner_path + ("x", "d")), dict):
            raise DataError("好感关系字段结构不兼容")
    if scalar_edits:
        document.set_many([(path, str(value)) for path, value in scalar_edits])
    for path, value in appends:
        document.append(path, value)
    intimacy_pairs = [(root_path, target_id)]
    if bidirectional:
        intimacy_pairs.append((target_path, root_id))
    for owner_path, other_id in intimacy_pairs:
        relation_path = owner_path + ("x", "d")
        relation = get_at(document.data, relation_path)
        if other_id in relation:
            document.set_many([(relation_path + (other_id,), str(intimacy))])
        else:
            document.add_mapping(relation_path, other_id, float(intimacy))


def remove_relationship(document, root_path, target_path, kind, bidirectional=True):
    root_path, target_path = tuple(root_path), tuple(target_path)
    root, target = get_at(document.data, root_path), get_at(document.data, target_path)
    root_id, target_id = str(root_path[-1]), str(target_path[-1])
    rx, tx = root.get("x"), target.get("x")
    if not isinstance(rx, dict) or not isinstance(tx, dict):
        raise DataError("角色关系结构缺失")

    def remove_list(owner_path, relations, key, unit_id, required=True):
        values = relations.get(key)
        if not isinstance(values, list):
            raise DataError("关系列表结构不兼容")
        if unit_id not in values:
            if required:
                raise DataError("所选关系已经不存在")
            return
        document.remove_at(owner_path + ("x", key), values.index(unit_id))

    if kind in RELATION_PAIRS:
        left, right = RELATION_PAIRS[kind]
        remove_list(root_path, rx, left, target_id)
        if bidirectional:
            remove_list(target_path, tx, right, root_id, required=False)
    elif kind in ("子女", "私生子女"):
        left = "w" if kind == "子女" else "e"
        remove_list(root_path, rx, left, target_id)
        if bidirectional and isinstance(tx.get("q"), list) and root_id in tx["q"]:
            document.set_many([(target_path + ("x", "q", tx["q"].index(root_id)), "")])
    elif kind == "父母":
        parents = rx.get("q")
        if not isinstance(parents, list) or target_id not in parents:
            raise DataError("所选父母关系已经不存在")
        document.set_many([(root_path + ("x", "q", parents.index(target_id)), "")])
        if bidirectional:
            remove_list(target_path, tx, "w", root_id, required=False)
    elif kind == "夫妻":
        if rx.get("i") != target_id:
            raise DataError("所选夫妻关系已经不存在")
        edits = [(root_path + ("x", "i"), "")]
        if bidirectional and tx.get("i") == root_id:
            edits.append((target_path + ("x", "i"), ""))
        document.set_many(edits)
    elif kind not in FRIEND_KINDS:
        raise DataError("不支持的关系类型")

    pairs = [(root_path, target_id)]
    if bidirectional:
        pairs.append((target_path, root_id))
    for owner_path, other_id in pairs:
        relation = get_at(document.data, owner_path + ("x", "d"))
        if isinstance(relation, dict) and other_id in relation:
            document.remove_mapping(owner_path + ("x", "d"), other_id)


def relationship_tables(document, role_path):
    role_path = tuple(role_path)
    relations = get_at(document.data, role_path).get("x", {})
    names = role_name_map(document)
    result = {kind: [] for kind in RELATION_KINDS}
    if not isinstance(relations, dict):
        return result
    intimacy = relations.get("d", {}) if isinstance(relations.get("d"), dict) else {}
    structural_ids = set()
    for key, label in RELATION_FIELDS.items():
        if label == "对玩家好感":
            continue
        value = relations.get(key)
        ids = value if isinstance(value, list) else ([value] if isinstance(value, str) and value else [])
        for unit_id in ids:
            if not isinstance(unit_id, str) or not unit_id:
                continue
            structural_ids.add(unit_id)
            result[label].append({"id": unit_id, "name": names.get(unit_id, "存档中未找到"),
                                  "intimacy": intimacy.get(unit_id, 0)})
    for unit_id, amount in intimacy.items():
        if isinstance(unit_id, str) and unit_id not in structural_ids and type(amount) in (int, float):
            result["好友"].append({"id": unit_id, "name": names.get(unit_id, "存档中未找到"),
                                  "intimacy": amount})
    return result


def role_name_map(document):
    return {str(path[-1]): name for path, name in find_roles(document.data) if path}


def relation_rows(document, role_path):
    relations = get_at(document.data, role_path).get("x", {})
    names = role_name_map(document)
    rows = []
    if not isinstance(relations, dict):
        return rows
    for key, value in relations.items():
        label = RELATION_FIELDS.get(key, f"关系字段 {key}")
        ids = value if isinstance(value, list) else ([value] if isinstance(value, str) and value else [])
        for unit_id in ids:
            if isinstance(unit_id, str) and unit_id:
                rows.append((label, names.get(unit_id, "存档中未找到"), unit_id))
                if len(rows) >= 2000:
                    return rows
    intimacy = relations.get("d")
    if isinstance(intimacy, dict):
        for unit_id, amount in intimacy.items():
            if isinstance(unit_id, str) and type(amount) in (int, float):
                rows.append(("好感", names.get(unit_id, "存档中未找到"), f"{unit_id} · {amount:g}"))
                if len(rows) >= 2000:
                    return rows
    return rows


def skill_rows(document, role_path, catalog):
    role = get_at(document.data, role_path)
    skills = role.get("k")
    if not isinstance(skills, dict):
        return []
    type_names = {"1": "武技/灵技", "2": "绝技", "3": "身法", "4": "心法", "5": "神通"}
    equipped = {role.get("a"), role.get("s"), role.get("g"), role.get("d")}
    equipped.update(value for value in role.get("f", []) if isinstance(value, str))
    result = []
    for unique_id, item in skills.items():
        try:
            values = item["q"]["w"]
            type_id, info_id, grade_id = values[3], values[4], values[5]
        except (KeyError, IndexError, TypeError):
            result.append(("未知", str(unique_id), "", "是" if unique_id in equipped else "否"))
            continue
        name = catalog.skills.get(str(info_id), f"功法 #{info_id}")
        result.append((type_names.get(str(type_id), f"类型 {type_id}"), name,
                       catalog.grades.get(str(grade_id), str(grade_id)), "是" if unique_id in equipped else "否"))
    return result


def _split_skill_effect_values(values):
    """Split the game's header/effect/marker/comprehension payload without shifting slots."""
    if not isinstance(values, list) or len(values) < 7:
        return [], []
    count = (len(values) - 7) // 2
    marker = 6 + count
    if count >= 0 and len(values) == 7 + count * 2 and values[marker] == -1:
        return values[6:marker], values[marker + 1:]
    try:
        marker = values.index(-1, 6)
    except ValueError:
        return [], []
    count = min(marker - 6, len(values) - marker - 1, 11)
    return values[6:6 + count], values[marker + 1:marker + 1 + count]


def skill_records(document, role_path, catalog):
    role_path = tuple(role_path)
    role = get_at(document.data, role_path)
    skills = role.get("k", {})
    if not isinstance(skills, dict):
        return []
    equipped = {role.get("a"): "武技/灵技", role.get("s"): "绝技", role.get("g"): "身法", role.get("d"): "神通"}
    for value in role.get("f", []) if isinstance(role.get("f"), list) else []:
        equipped[value] = "心法"
    result = []
    for unique_id, item in skills.items():
        try:
            values = item["q"]["w"]
            if not isinstance(values, list) or len(values) < 6:
                continue
            type_id, info_id, grade_id = int(values[3]), int(values[4]), int(values[5])
            inheritance = int(values[2])
            progress = int(item.get("w", 0))
        except (KeyError, TypeError, ValueError):
            continue
        raw_ids, raw_exp = _split_skill_effect_values(values)
        effect_ids = [int(value) for value in raw_ids][:11]
        effect_exp = [int(value) for value in raw_exp][:len(effect_ids)]
        effect_exp.extend([0] * (len(effect_ids) - len(effect_exp)))
        name = catalog.skill_info.get(str(info_id), {}).get("name") or catalog.skills.get(str(info_id), f"未知功法 #{info_id}")
        type_name = catalog.skill_types.get(str(type_id), {}).get("name", f"类型 #{type_id}")
        grade_name = catalog.skill_grades.get(str(grade_id), {}).get("name") or catalog.grades.get(str(grade_id), f"境界 #{grade_id}")
        result.append({
            "uuid": str(unique_id), "path": role_path + ("k", unique_id), "equipped": equipped.get(unique_id, "否"),
            "name": name, "type": type_name, "grade": grade_name, "progress": progress,
            "type_id": type_id, "info_id": info_id, "grade_id": grade_id, "inheritance": inheritance,
            "effects": effect_ids, "effect_exp": effect_exp,
        })
    return result


def _skill_value(catalog, token, grade_id):
    row = catalog.skill_values.get(f"&{token}+6") or catalog.skill_values.get(f"&{token}")
    if row:
        values = row.get("values", [])
        index = max(0, min(int(grade_id) - 1, len(values) - 1))
        value = float(values[index]) if values else 0.0
        scale = str(row.get("scale") or "x1").split("|", 1)[0]
        try:
            if scale.startswith("x"):
                value *= float(scale[1:])
        except ValueError:
            pass
        return value
    try:
        return float(token)
    except (TypeError, ValueError):
        return 0.0


def _skill_tip(catalog, text, grade_id):
    def replace(match):
        parts = match.group(1).split("|")
        operands = parts[:-1] if len(parts) > 1 and parts[-1].startswith("f") else parts
        values, operations = [], []
        for index, part in enumerate(operands):
            operation = part[0] if part[:1] in "x/+-" else None
            values.append(_skill_value(catalog, part[1:] if operation else part, grade_id))
            if index:
                operations.append(operation or "+")
        result = values[0] if values else 0.0
        for operation, value in zip(operations, values[1:]):
            if operation == "x": result *= value
            elif operation == "/" and value: result /= value
            elif operation == "+": result += value
            elif operation == "-": result -= value
        precision = 0
        if parts and parts[-1].startswith("f"):
            try:
                precision = max(0, min(int(parts[-1][1:]), 6))
            except ValueError:
                pass
        return f"{result:.{precision}f}" if precision else f"{result:.2f}".rstrip("0").rstrip(".")
    return re.sub(r"&([^&]+)&", replace, str(text)).replace("\n", " ")


def skill_effect_candidates(catalog, type_id, info_id, grade_id=1):
    result = {}
    for owner in (int(info_id), int(type_id), 0):
        for row in catalog.skill_effects:
            if int(row.get("skill_id", -1)) == owner:
                result.setdefault(int(row["id"]), _skill_tip(
                    catalog, row.get("name") or str(row["id"]), grade_id))
    return sorted(result.items(), key=lambda row: row[0])


def update_skill(document, role_path, unique_id, *, type_id, info_id, grade_id, inheritance,
                 progress, effects, effect_exp):
    role_path = tuple(role_path)
    item_path = role_path + ("k", str(unique_id))
    item = get_at(document.data, item_path)
    values = item.get("q", {}).get("w")
    if not isinstance(values, list) or len(values) < 6:
        raise DataError("所选功法结构无法安全修改")
    try:
        type_id, info_id, grade_id = int(type_id), int(info_id), int(grade_id)
        inheritance, progress = int(inheritance), int(progress)
        ids = [int(value) for value in effects]
        exps = [int(value) for value in effect_exp]
    except (TypeError, ValueError) as exc:
        raise DataError("功法编号、境界、词条和参悟程度必须是整数") from exc
    if type_id <= 0 or info_id <= 0 or grade_id <= 0:
        raise DataError("功法类型、名称和所用境界必须选择有效编号")
    if inheritance not in (0, 1):
        raise DataError("传承只能选择否或是")
    if not 0 <= progress <= 999999999:
        raise DataError("功法进度超出允许范围")
    if len(ids) != 11 or len(exps) != 11:
        raise DataError("词条编辑区必须保持 11 个栏位")
    compact_ids, compact_exp = [], []
    for effect_id, exp in zip(ids, exps):
        if effect_id == 0:
            continue
        if effect_id < 0 or not 0 <= exp <= 9999999:
            raise DataError("词条编号或参悟程度超出允许范围")
        if effect_id in compact_ids:
            raise DataError(f"词条 #{effect_id} 重复")
        compact_ids.append(effect_id)
        compact_exp.append(exp)
    prefix = [values[0], values[1], inheritance, type_id, info_id, grade_id]
    replacement = prefix + compact_ids + ([-1] + compact_exp if compact_ids else [])
    document.replace_value(item_path + ("q", "w"), replacement)
    document.set_many([(item_path + ("w",), str(progress))])


def perfect_skill_comprehension(document, role_path, unique_id=None):
    """Set existing skill-entry comprehension to the value used by the old editor.

    The skill payload stores effect IDs before a -1 marker and one comprehension
    value per effect after it.  We only replace those existing numeric values and
    never manufacture effect IDs.
    """
    role_path = tuple(role_path)
    skills = get_at(document.data, role_path).get("k", {})
    if not isinstance(skills, dict):
        raise DataError("当前角色没有可识别的功法列表")
    targets = [(unique_id, skills.get(unique_id))] if unique_id is not None else list(skills.items())
    changes = []
    changed_skills = 0
    for skill_id, item in targets:
        if not isinstance(item, dict):
            continue
        values = item.get("q", {}).get("w")
        if not isinstance(values, list):
            continue
        try:
            marker = values.index(-1, 6)
        except ValueError:
            continue
        effect_count = marker - 6
        if effect_count <= 0 or len(values) < marker + 1 + effect_count:
            continue
        local = []
        for index in range(marker + 1, marker + 1 + effect_count):
            if type(values[index]) not in (int, float):
                local = []
                break
            local.append((role_path + ("k", skill_id, "q", "w", index), 600))
        if local:
            changes.extend(local)
            changed_skills += 1
    if not changes:
        raise DataError("所选功法没有可识别的已有词条参悟值")
    document.set_many(changes)
    return changed_skills, len(changes)


def enable_skill_effects(document, role_path, unique_id=None):
    """Unlock existing skill effects using the old editor's verified value."""
    role_path = tuple(role_path)
    skills = get_at(document.data, role_path).get("k", {})
    if not isinstance(skills, dict):
        raise DataError("当前角色没有可识别的功法列表")
    targets = [(unique_id, skills.get(unique_id))] if unique_id is not None else list(skills.items())
    changes = []
    for skill_id, item in targets:
        if isinstance(item, dict) and type(item.get("w")) in (int, float):
            changes.append((role_path + ("k", skill_id, "w"), 9999999))
    if not changes:
        raise DataError("所选功法没有可识别的词条生效字段")
    document.set_many(changes)
    return len(changes)


APPEARANCE_FIELDS = {
    "q": "性别", "w": "帽子", "e": "后发", "r": "前发", "t": "脸型", "y": "眉毛",
    "u": "眼睛", "i": "鼻子", "o": "嘴巴", "p": "衣服", "a": "后背", "s": "眉心",
    "d": "全脸", "f": "左脸", "g": "右脸", "h": "前额", "j": "其他",
}

NORMAL_APPEARANCE_PATHS = {
    "性别": ("q", "e", "q"), "帽子": ("q", "e", "w"), "后发": ("q", "e", "e"),
    "前发": ("q", "e", "r"), "脸型": ("q", "e", "t"), "眉毛": ("q", "e", "y"),
    "眼睛": ("q", "e", "u"), "鼻子": ("q", "e", "i"), "嘴巴": ("q", "e", "o"),
    "衣服": ("q", "e", "p"), "后背": ("q", "e", "a"), "眉心": ("q", "e", "s"),
    "全脸": ("q", "e", "d"), "左脸": ("q", "e", "f"), "右脸": ("q", "e", "g"),
}

BATTLE_APPEARANCE_PATHS = {
    "性别": ("q", "w", "q"), "衣服": ("q", "w", "w"), "后背": ("q", "w", "e"),
    "帽子": ("q", "w", "r"), "后发": ("q", "w", "t"), "脸型": ("q", "w", "y"),
}

APPEARANCE_TYPES = {
    "帽子": "maozi", "后发": "toufa", "前发": "toufaqian", "脸型": "lian",
    "眉毛": "meimao", "眼睛": "yanjing", "鼻子": "bizi", "嘴巴": "zuiba",
    "衣服": "yifu", "后背": "houbei", "眉心": "meixin", "全脸": "quanlian",
    "左脸": "zuolian", "右脸": "youlian",
}


@lru_cache(maxsize=4)
def appearance_catalog(game_path=str(DEFAULT_GAME)):
    path = Path(game_path) / "Mod/modFQA/配置修改教程/配置（只读）Json格式/RoleDress.json"
    if not path.is_file():
        return {}
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    result = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            item_id, sex = int(row.get("id")), int(row.get("sex"))
        except (TypeError, ValueError):
            continue
        result.setdefault((str(row.get("type")), sex), []).append(item_id)
    for values in result.values():
        values.sort()
    return result


def appearance_data(document, role_path):
    role_path = tuple(role_path)
    normal, battle = {}, {}
    for label, suffix in NORMAL_APPEARANCE_PATHS.items():
        try:
            normal[label] = get_at(document.data, role_path + suffix)
        except (KeyError, IndexError, TypeError):
            normal[label] = ""
    for label, suffix in BATTLE_APPEARANCE_PATHS.items():
        try:
            battle[label] = get_at(document.data, role_path + suffix)
        except (KeyError, IndexError, TypeError):
            battle[label] = ""
    return {"version": 1, "normal": normal, "battle": battle}


def update_appearance(document, role_path, normal, battle):
    if not isinstance(normal, dict) or not isinstance(battle, dict):
        raise DataError("外貌模板结构无效")
    edits = []
    for values, paths, group in ((normal, NORMAL_APPEARANCE_PATHS, "常态"),
                                 (battle, BATTLE_APPEARANCE_PATHS, "战斗")):
        for label, suffix in paths.items():
            if label not in values:
                raise DataError(f"{group}形象缺少{label}")
            try:
                value = int(str(values[label]).rsplit(" · ", 1)[-1].strip())
            except (TypeError, ValueError) as exc:
                raise DataError(f"{group}形象的{label}必须是整数 ID") from exc
            if value < 0 or value > 2 ** 31 - 1:
                raise DataError(f"{group}形象的{label}超出有效范围")
            path = tuple(role_path) + suffix
            try:
                current = get_at(document.data, path)
            except (KeyError, IndexError, TypeError) as exc:
                raise DataError(f"当前角色缺少{group}形象字段：{label}") from exc
            if type(current) is not int:
                raise DataError(f"当前角色的{group}形象字段类型不兼容：{label}")
            edits.append((path, str(value)))
    document.set_many(edits)
    return len(edits)


def appearance_rows(document, role_path):
    data = get_at(document.data, role_path).get("q", {}).get("e", {})
    if not isinstance(data, dict):
        return []
    return [(APPEARANCE_FIELDS.get(key, f"字段 {key}"), key, value) for key, value in data.items()
            if type(value) in (int, float, str, bool)]


def fate_rows(document, role_path):
    q = get_at(document.data, role_path).get("q", {})
    sections = [("先天气运", q.get("qb")), ("后天气运 / 逆天改命", q.get("qn")),
                ("道心相关", q.get("qv"))]
    rows = []
    for label, values in sections:
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, dict):
                value = value.get("q", value)
            if value not in (None, "", 0):
                rows.append((label, str(value)))
    return rows


FATE_SECTION_LABELS = ("先天气运", "后天气运", "逆天改命", "道心")


def _luck_id(item):
    if isinstance(item, dict) and type(item.get("q")) in (int, float):
        return int(item["q"])
    return None


def fate_entries(document, role_path, section, catalog):
    if section not in FATE_SECTION_LABELS:
        raise DataError("未知气运类别")
    role_path = tuple(role_path)
    role = get_at(document.data, role_path)
    q = role.get("q", {}) if isinstance(role, dict) else {}
    result = []
    if section == "道心":
        hearts = role.get("qr", {})
        if not isinstance(hearts, dict):
            return []
        for key, value in hearts.items():
            fate_id = value.get("luck") if isinstance(value, dict) else None
            if type(fate_id) not in (int, float):
                continue
            fate_id = int(fate_id)
            name = catalog.reverse_fate.get(str(fate_id), {}).get("name", f"未知道心 #{fate_id}")
            result.append({"id": fate_id, "name": name, "path": role_path + ("qr", key, "luck"),
                           "container": "mapping", "key": key})
        return result
    field = "qb" if section == "先天气运" else "qn"
    values = q.get(field, [])
    if not isinstance(values, list):
        return []
    heart_ids = {row["id"] for row in fate_entries(document, role_path, "道心", catalog)}
    for index, value in enumerate(values):
        fate_id = _luck_id(value)
        if fate_id is None:
            continue
        is_reverse = str(fate_id) in catalog.reverse_fate
        if section == "后天气运" and (is_reverse or fate_id in heart_ids):
            continue
        if section == "逆天改命" and not is_reverse:
            continue
        names = catalog.born_luck if section == "先天气运" else catalog.reverse_fate
        name = names.get(str(fate_id), {}).get("name", f"未知气运 #{fate_id}")
        result.append({"id": fate_id, "name": name, "path": role_path + ("q", field, index, "q"),
                       "container": "list", "index": index})
    return result


def fate_candidates(catalog, section, needle=""):
    if section == "先天气运":
        source = catalog.born_luck
    elif section in ("逆天改命", "道心"):
        source = catalog.reverse_fate
    else:
        source = {**catalog.born_luck, **catalog.reverse_fate}
    needle = str(needle).strip().casefold()
    rows = []
    for fate_id, data in source.items():
        name = data.get("name", fate_id)
        if not needle or needle in fate_id.casefold() or needle in name.casefold():
            rows.append((int(fate_id), name))
    return sorted(rows, key=lambda row: (row[1], row[0]))[:500]


def _parse_fate_id(value):
    try:
        fate_id = int(str(value).strip())
    except ValueError as exc:
        raise DataError("气运 ID 必须是整数") from exc
    if not 0 < fate_id <= 2**31 - 1:
        raise DataError("气运 ID 必须在 1 到 2147483647 之间")
    return fate_id


def _luck_object(fate_id):
    return {"q": fate_id, "w": -1, "e": 1, "t": {"allObject": {"": {"NewCreateLuck": "1"}}}}


def add_fate(document, role_path, section, fate_id):
    fate_id = _parse_fate_id(fate_id)
    role_path = tuple(role_path)
    role = get_at(document.data, role_path)
    if section == "道心":
        hearts = role.get("qr")
        qn = role.get("q", {}).get("qn")
        if not isinstance(hearts, dict) or not isinstance(qn, list):
            raise DataError("当前角色缺少可写入的道心结构")
        if any(isinstance(value, dict) and value.get("luck") == fate_id for value in hearts.values()):
            raise DataError("该道心已存在")
        if any(_luck_id(value) == fate_id for value in qn):
            raise DataError("该编号已存在于后天气运/逆天改命中")
        numeric = [int(key) for key in hearts if str(key).isdigit()]
        key = str(max(numeric, default=1) + 1)
        document.add_mapping(role_path + ("qr",), key, {"quality": 5, "luck": fate_id})
        document.append(role_path + ("q", "qn"), _luck_object(fate_id))
        return
    field = "qb" if section == "先天气运" else "qn"
    values = role.get("q", {}).get(field)
    if not isinstance(values, list):
        raise DataError("当前角色缺少可写入的气运列表")
    if any(_luck_id(value) == fate_id for value in values):
        raise DataError("该气运编号已存在")
    document.append(role_path + ("q", field), _luck_object(fate_id))


def add_fates(document, role_path, section, fate_ids):
    """Validate the entire selection before adding any fate entries."""
    parsed = [_parse_fate_id(value) for value in fate_ids]
    if not parsed:
        raise DataError("请至少选择一条候选气运")
    if len(parsed) != len(set(parsed)):
        raise DataError("批量选择中存在重复气运")
    role_path = tuple(role_path)
    role = get_at(document.data, role_path)
    if section == "道心":
        hearts = role.get("qr")
        qn = role.get("q", {}).get("qn")
        if not isinstance(hearts, dict) or not isinstance(qn, list):
            raise DataError("当前角色缺少可写入的道心结构")
        existing_hearts = {value.get("luck") for value in hearts.values() if isinstance(value, dict)}
        existing_qn = {_luck_id(value) for value in qn}
        conflicts = [value for value in parsed if value in existing_hearts or value in existing_qn]
        if conflicts:
            raise DataError("以下编号已经存在：" + "、".join(str(value) for value in conflicts))
        numeric = [int(key) for key in hearts if str(key).isdigit()]
        next_key = max(numeric, default=1) + 1
        for offset, fate_id in enumerate(parsed):
            document.add_mapping(role_path + ("qr",), str(next_key + offset), {"quality": 5, "luck": fate_id})
            document.append(role_path + ("q", "qn"), _luck_object(fate_id))
        return
    field = "qb" if section == "先天气运" else "qn"
    values = role.get("q", {}).get(field)
    if not isinstance(values, list):
        raise DataError("当前角色缺少可写入的气运列表")
    existing = {_luck_id(value) for value in values}
    conflicts = [value for value in parsed if value in existing]
    if conflicts:
        raise DataError("以下编号已经存在：" + "、".join(str(value) for value in conflicts))
    for fate_id in parsed:
        document.append(role_path + ("q", field), _luck_object(fate_id))


def replace_fate(document, role_path, section, entry, fate_id):
    fate_id = _parse_fate_id(fate_id)
    old_id = entry["id"]
    if old_id == fate_id:
        return
    role_path = tuple(role_path)
    role = get_at(document.data, role_path)
    if section == "道心":
        qn = role.get("q", {}).get("qn", [])
        matches = [index for index, value in enumerate(qn) if _luck_id(value) == old_id]
        edits = [(entry["path"], str(fate_id))]
        if len(matches) == 1:
            edits.append((role_path + ("q", "qn", matches[0], "q"), str(fate_id)))
        document.set_many(edits)
        return
    document.set_many([(entry["path"], str(fate_id))])


def delete_fate(document, role_path, section, entry):
    role_path = tuple(role_path)
    if section == "道心":
        role = get_at(document.data, role_path)
        qn = role.get("q", {}).get("qn", [])
        matches = [index for index, value in enumerate(qn) if _luck_id(value) == entry["id"]]
        document.remove_mapping(role_path + ("qr",), entry["key"])
        if len(matches) == 1:
            document.remove_at(role_path + ("q", "qn"), matches[0])
        return
    field = "qb" if section == "先天气运" else "qn"
    document.remove_at(role_path + ("q", field), entry["index"])


def special_attribute_rows(document, role_path, catalog):
    role_path = tuple(role_path)
    role = get_at(document.data, role_path)
    candidates = [
        ("性格", "内在性格", ("q", "f"), catalog.in_traits),
        ("性格", "外在性格一", ("q", "g"), catalog.out_traits),
        ("性格", "外在性格二", ("q", "h"), catalog.out_traits),
        ("关系", "对主角好感", ("x", "s"), {}),
        ("道心", "道种", ("qe", "y"), catalog.taoist_seeds),
        ("道心", "阶段", ("qe", "h"), catalog.taoist_levels),
        ("身份", "境界", ("q", "d"), {key: {"name": value} for key, value in catalog.grades.items()}),
        ("身份", "神魂", ("b", "q"), catalog.souls),
        ("身份", "性别", ("q", "r"), {"1": {"name": "男"}, "2": {"name": "女"}}),
        ("身份", "发展方向", ("qe", "i"), catalog.directions),
        ("身份", "是否天骄", ("qe", "u"), {"0": {"name": "否"}, "1": {"name": "否"}, "2": {"name": "是"}}),
    ]
    hobbies = role.get("q", {}).get("qv", [])
    if isinstance(hobbies, list):
        for index in range(min(3, len(hobbies))):
            candidates.insert(3 + index, ("爱好", f"爱好 {index + 1}", ("q", "qv", index), catalog.hobbies))
    result = []
    for group, label, suffix, choices in candidates:
        path = role_path + suffix
        try:
            value = get_at(document.data, path)
        except (KeyError, TypeError, IndexError):
            continue
        name = choices.get(str(value), {}).get("name", str(value)) if choices else str(value)
        result.append({"group": group, "label": label, "value": value, "name": name,
                       "path": path, "choices": choices, "mode": "set"})
    titles = role.get("qt", {}).get("w", [])
    if isinstance(titles, list):
        if titles:
            value = titles[0]
            name = catalog.appellations.get(str(value), {}).get("name", str(value))
            result.append({"group": "身份", "label": "道号", "value": value, "name": name,
                           "path": role_path + ("qt", "w", 0), "choices": catalog.appellations,
                           "mode": "set"})
        else:
            result.append({"group": "身份", "label": "道号", "value": 0, "name": "未设置",
                           "path": role_path + ("qt", "w"), "choices": catalog.appellations,
                           "mode": "append"})
    return result


def school_rows(document, role_path):
    role = get_at(document.data, role_path)
    q = role.get("q", {})
    return [("宗门编号", role.get("u", "")), ("身份/职位字段", q.get("t", "")),
            ("境界", q.get("d", "")), ("声望", q.get("a", ""))]


SCHOOL_MAIN_SKILLS = {
    "刀": ("weaponType", "basBlade"), "枪": ("weaponType", "basSpear"),
    "剑": ("weaponType", "basSword"), "拳": ("weaponType", "basFist"),
    "掌": ("weaponType", "basPalm"), "指": ("weaponType", "basFinger"),
    "火": ("magicType", "basFire"), "水": ("magicType", "basFroze"),
    "雷": ("magicType", "basThunder"), "风": ("magicType", "basWind"),
    "土": ("magicType", "basEarth"), "木": ("magicType", "basWood"),
}


def _school_record(school_document, unit_document, role_path):
    if not school_document or not unit_document or role_path is None:
        return None, None
    role = get_at(unit_document.data, tuple(role_path))
    school_id = role.get("u") if isinstance(role, dict) else None
    schools = school_document.data.get("allBuild", {}) if isinstance(school_document.data, dict) else {}
    school = schools.get(school_id) if isinstance(schools, dict) else None
    return (school_id, school) if isinstance(school, dict) else (school_id, None)


def _school_base_values(school):
    try:
        value = school.get("values", ["{}"])[:1][0]
        return json.loads(value) if isinstance(value, str) else {}
    except (ValueError, TypeError, IndexError):
        return {}


def school_data(school_document, unit_document, role_path):
    school_id, school = _school_record(school_document, unit_document, role_path)
    if school is None:
        return None
    prop = school.get("propertyData", {})
    manor = school.get("manorData", {}).get("mainManor", {})
    base = _school_base_values(school)
    def fixed(name, fallback):
        value = prop.get(name)
        return fallback if value in (None, 0, "") else value
    fields = {
        "灵石": school.get("money", 0), "宗门荣誉": school.get("reputation", 0),
        "繁荣": prop.get("prosperous", 0), "忠诚": prop.get("loyal", prop.get("Loyal", 0)),
        "立场": fixed("fixStand", base.get("stand", 0)), "宗门名": prop.get("fixName") or "",
        "安定": manor.get("stable", manor.get("Stable", 0)), "记名弟子": school.get("totalMember", 0),
        "药材": prop.get("medicina", 0), "矿材": prop.get("mine", 0),
        "灵阁": fixed("fixFateID", base.get("fateID", 0)), "分舵名": prop.get("fixAreaName") or "",
        "宗门特质1": fixed("fixSloganItem1Type1", base.get("schoolSloganItem1Type1", 0)),
        "宗门特质2": fixed("fixSloganItem1Type2", base.get("schoolSloganItem1Type2", 0)),
        "宗门门规1": fixed("fixSloganItem2Type1", base.get("schoolSloganItem2Type1", 0)),
        "宗门门规2": fixed("fixSloganItem2Type2", base.get("schoolSloganItem2Type2", 0)),
    }
    data_path = ("allBuild", school_id, "allBuildSub", "1002", "objData", "allObject", "", "data")
    try:
        skill_data = json.loads(get_at(school_document.data, data_path))
    except (KeyError, IndexError, TypeError, ValueError):
        skill_data = {}
    selected = set(skill_data.get("weaponType", [])) | set(skill_data.get("magicType", []))
    skills = {label: code in selected for label, (_group, code) in SCHOOL_MAIN_SKILLS.items()}
    return {"id": school_id, "path": ("allBuild", school_id), "fields": fields,
            "main_skills": skills, "skill_data_path": data_path}


def update_school(school_document, unit_document, role_path, values):
    data = school_data(school_document, unit_document, role_path)
    if data is None:
        raise DataError("当前角色没有可识别的宗门数据")
    numeric = ("灵石", "宗门荣誉", "繁荣", "忠诚", "立场", "安定", "记名弟子", "药材", "矿材",
               "灵阁", "宗门特质1", "宗门特质2", "宗门门规1", "宗门门规2")
    parsed = {}
    for label in numeric:
        try:
            number = int(str(values[label]).rsplit(" · ", 1)[-1].strip())
        except (KeyError, ValueError) as exc:
            raise DataError(f"{label}必须是整数") from exc
        if not -(2 ** 31) <= number <= 2 ** 31 - 1:
            raise DataError(f"{label}超出有效范围")
        parsed[label] = number
    root = data["path"]
    edits = []
    direct = (("灵石", ("money",)), ("宗门荣誉", ("reputation",)),
              ("繁荣", ("propertyData", "prosperous")), ("忠诚", ("propertyData", "loyal")),
              ("安定", ("manorData", "mainManor", "stable")), ("记名弟子", ("totalMember",)),
              ("药材", ("propertyData", "medicina")), ("矿材", ("propertyData", "mine")))
    changed_labels = set()
    for label, suffix in direct:
        if parsed[label] != data["fields"][label]:
            edits.append((root + suffix, str(parsed[label])))
            changed_labels.add(label)
    prop = get_at(school_document.data, root + ("propertyData",))
    manor = get_at(school_document.data, root + ("manorData", "mainManor"))
    if "忠诚" in changed_labels and "Loyal" in prop:
        edits.append((root + ("propertyData", "Loyal"), str(parsed["忠诚"])))
    if "安定" in changed_labels and "Stable" in manor:
        edits.append((root + ("manorData", "mainManor", "Stable"), str(parsed["安定"])))
    base = _school_base_values(get_at(school_document.data, root))
    fixed = (("stand", "立场", "fixStand"), ("fateID", "灵阁", "fixFateID"),
             ("schoolSloganItem1Type1", "宗门特质1", "fixSloganItem1Type1"),
             ("schoolSloganItem1Type2", "宗门特质2", "fixSloganItem1Type2"),
             ("schoolSloganItem2Type1", "宗门门规1", "fixSloganItem2Type1"),
             ("schoolSloganItem2Type2", "宗门门规2", "fixSloganItem2Type2"))
    base_changed = False
    for key, label, fix_key in fixed:
        if parsed[label] != data["fields"][label]:
            edits.append((root + ("propertyData", fix_key), str(parsed[label])))
            base[key] = parsed[label]
            base_changed = True
            changed_labels.add(label)
    if base_changed:
        edits.append((root + ("values", 0), json.dumps(base, ensure_ascii=False, separators=(",", ":"))))
    if edits:
        school_document.set_many(edits)
    for label, key in (("宗门名", "fixName"), ("分舵名", "fixAreaName")):
        new_value = str(values.get(label, "")).strip() or None
        current = get_at(school_document.data, root + ("propertyData", key))
        if current != new_value:
            school_document.replace_scalar(root + ("propertyData", key), new_value)
            changed_labels.add(label)
    return len(changed_labels)


def update_school_main_skills(school_document, unit_document, role_path, selected):
    data = school_data(school_document, unit_document, role_path)
    if data is None:
        raise DataError("当前角色没有可识别的宗门数据")
    normalized = {label: bool(selected.get(label)) for label in SCHOOL_MAIN_SKILLS}
    if normalized == data["main_skills"]:
        return 0
    path = data["skill_data_path"]
    try:
        payload = json.loads(get_at(school_document.data, path))
    except (KeyError, TypeError, ValueError) as exc:
        raise DataError("宗门藏经阁功法结构无法识别") from exc
    payload["weaponType"] = [code for label, (group, code) in SCHOOL_MAIN_SKILLS.items()
                             if group == "weaponType" and normalized[label]]
    payload["magicType"] = [code for label, (group, code) in SCHOOL_MAIN_SKILLS.items()
                            if group == "magicType" and normalized[label]]
    school_document.set_many([(path, json.dumps(payload, ensure_ascii=False, separators=(",", ":")))])
    return sum(normalized.values())


def school_members(school_document, unit_document, role_path, catalog):
    data = school_data(school_document, unit_document, role_path)
    if data is None:
        return [], []
    school = get_at(school_document.data, data["path"])
    paths = {str(path[-1]): path for path, _name in find_roles(unit_document.data) if path}
    names = role_name_map(unit_document)
    groups = (("宗主", [school.get("npcSchoolMain")]), ("大长老", school.get("npcBigElders", [])),
              ("长老", school.get("npcElders", [])), ("真传弟子", school.get("npcInherit", [])),
              ("内门弟子", school.get("npcIn", [])), ("外门弟子", school.get("npcOut", [])))
    rows, souls, seen = [], [], set()
    for post, ids in groups:
        for unit_id in ids if isinstance(ids, list) else []:
            if not isinstance(unit_id, str) or not unit_id or unit_id in seen:
                continue
            seen.add(unit_id)
            path = paths.get(unit_id)
            if path is None:
                souls.append({"id": unit_id, "name": "存档中未找到", "grade": "未知"})
                continue
            info = role_info(get_at(unit_document.data, path), catalog)
            rows.append({"id": unit_id, "path": path, "name": names.get(unit_id, unit_id),
                         "post": post, "grade": info["grade"]})
    return rows, souls


def school_batch_genius(unit_document, member_rows, seed_id, heart_skill=0):
    try:
        seed_id, heart_skill = int(seed_id), int(heart_skill or 0)
    except ValueError as exc:
        raise DataError("请选择有效道种") from exc
    if seed_id <= 0:
        raise DataError("全天骄前必须选择非零道种")
    edits = []
    for row in member_rows:
        for suffix, value in ((('qe', 'u'), 2), (('qe', 'y'), seed_id), (('qe', 'h'), 3)):
            try:
                get_at(unit_document.data, tuple(row["path"]) + suffix)
                edits.append((tuple(row["path"]) + suffix, str(value)))
            except (KeyError, TypeError, IndexError):
                pass
        if heart_skill:
            path = tuple(row["path"]) + ("qe", "s")
            try:
                get_at(unit_document.data, path)
                edits.append((path, str(heart_skill)))
            except (KeyError, TypeError, IndexError):
                pass
    if not edits:
        raise DataError("宗门成员缺少可写入的天骄字段")
    unit_document.set_many(edits)
    return len(member_rows)


def school_batch_salary(unit_document, member_rows, amount):
    try:
        amount = int(amount)
    except ValueError as exc:
        raise DataError("工资必须是整数") from exc
    if amount <= 0:
        raise DataError("工资必须大于 0")
    edits, paid = [], 0
    for row in member_rows:
        props = get_at(unit_document.data, tuple(row["path"])).get("z", {}).get("allProps", [])
        for index, item in enumerate(props if isinstance(props, list) else []):
            values = item.get("w") if isinstance(item, dict) else None
            if isinstance(values, list) and len(values) > 2 and values[1] == 10001 and type(values[2]) is int:
                total = values[2] + amount
                if total > 2 ** 31 - 1:
                    raise DataError(f"{row['name']}的灵石会超出上限")
                edits.append((tuple(row["path"]) + ("z", "allProps", index, "w", 2), str(total)))
                paid += 1
                break
    if not edits:
        raise DataError("未找到拥有灵石条目的宗门成员")
    unit_document.set_many(edits)
    return paid


def school_batch_friend(unit_document, member_rows, intimacy):
    try:
        intimacy = int(intimacy)
    except ValueError as exc:
        raise DataError("好感必须是整数") from exc
    if not -1000 <= intimacy <= 1000:
        raise DataError("好感必须在 -1000 到 1000 之间")
    edits = []
    for row in member_rows:
        path = tuple(row["path"]) + ("x", "s")
        try:
            get_at(unit_document.data, path)
            edits.append((path, str(intimacy)))
        except (KeyError, TypeError, IndexError):
            pass
    if not edits:
        raise DataError("宗门成员缺少可写入的主角好感字段")
    unit_document.set_many(edits)
    return len(edits)


def editable_page_rows(document, role_path, page, catalog=None):
    """Return display columns plus the exact existing scalar path that may be edited.

    This deliberately never manufactures list members or cross-object references.  It is
    the safe subset shared by old and current saves: replace an already present scalar.
    """
    role_path = tuple(role_path)
    role = get_at(document.data, role_path)
    q = role.get("q", {}) if isinstance(role, dict) else {}
    rows = []
    if page == "relation":
        relations = role.get("x", {})
        names = role_name_map(document)
        intimacy = relations.get("d", {}) if isinstance(relations, dict) else {}
        if isinstance(intimacy, dict):
            for unit_id, amount in intimacy.items():
                if isinstance(unit_id, str) and type(amount) in (int, float):
                    rows.append({"values": ("好感", names.get(unit_id, "存档中未找到"), f"{unit_id} · {amount:g}"),
                                 "path": role_path + ("x", "d", unit_id)})
    elif page == "skill":
        skills = role.get("k", {})
        catalog = catalog or Catalog()
        type_names = {"1": "武技/灵技", "2": "绝技", "3": "身法", "4": "心法", "5": "神通"}
        equipped = {role.get("a"), role.get("s"), role.get("g"), role.get("d")}
        equipped.update(value for value in role.get("f", []) if isinstance(value, str))
        if isinstance(skills, dict):
            for unique_id, item in skills.items():
                try:
                    values = item["q"]["w"]
                    type_id, info_id, grade_id = values[3], values[4], values[5]
                    if type(grade_id) not in (int, float):
                        continue
                except (KeyError, IndexError, TypeError):
                    continue
                rows.append({"values": (type_names.get(str(type_id), f"类型 {type_id}"),
                                         catalog.skills.get(str(info_id), f"功法 #{info_id}"),
                                         catalog.grades.get(str(grade_id), str(grade_id)),
                                         "是" if unique_id in equipped else "否"),
                             "path": role_path + ("k", unique_id, "q", "w", 5)})
    elif page == "appearance":
        data = q.get("e", {}) if isinstance(q, dict) else {}
        if isinstance(data, dict):
            for key, value in data.items():
                if type(value) in (int, float, str, bool):
                    rows.append({"values": (APPEARANCE_FIELDS.get(key, f"字段 {key}"), key, value),
                                 "path": role_path + ("q", "e", key)})
    elif page == "school":
        candidates = [("宗门编号", role_path + ("u",)), ("身份/职位字段", role_path + ("q", "t")),
                      ("境界", role_path + ("q", "d")), ("声望", role_path + ("q", "a"))]
        for label, path in candidates:
            try:
                value = get_at(document.data, path)
            except (KeyError, IndexError, TypeError):
                continue
            if type(value) in (int, float, str, bool):
                rows.append({"values": (label, value), "path": path})
    elif page == "potmon":
        data = role.get("qy")
        if isinstance(data, dict):
            for key, value in data.items():
                if type(value) in (int, float, str, bool):
                    rows.append({"values": (f"字段 {key}", value), "path": role_path + ("qy", key)})
                else:
                    rows.append({"values": (f"字段 {key}", f"{len(value)} 项"), "path": None})
    elif page == "fate":
        for field, label in (("qb", "先天气运"), ("qn", "后天气运 / 逆天改命"), ("qv", "道心相关")):
            values = q.get(field)
            if not isinstance(values, list):
                continue
            for index, value in enumerate(values):
                path = role_path + ("q", field, index)
                if isinstance(value, dict) and "q" in value and type(value["q"]) in (int, float, str):
                    rows.append({"values": (label, value["q"]), "path": path + ("q",)})
                elif type(value) in (int, float, str):
                    rows.append({"values": (label, value), "path": path})
    return rows
