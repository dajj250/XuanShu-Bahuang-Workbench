"""File codecs and editing rules. No game process or network access."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import tempfile
import copy
from datetime import datetime
from uuid import uuid4

MAX_BYTES = 128 * 1024 * 1024
KEY = b"5:.A%KL;,.?<aH._=-/DF4s"
PREFIX = bytes(c ^ 3 for c in b"2a;ad.,&fSf^SX.,:12@D")


class DataError(ValueError):
    pass


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DataError(f"JSON 包含重复字段：{key}")
        result[key] = value
    return result


def _finite_float(text):
    value = float(text)
    if not math.isfinite(value):
        raise DataError("不支持超出范围的浮点数")
    return value


def parse_json(raw: bytes):
    if len(raw) > MAX_BYTES:
        raise DataError("数据超过 128 MB 上限")
    try:
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_pairs,
                           parse_float=_finite_float,
                           parse_constant=lambda s: (_ for _ in ()).throw(DataError("不支持非有限数字")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise DataError(f"无法读取 JSON：{exc}") from exc
    if not isinstance(value, (dict, list)):
        raise DataError("数据顶层必须是对象或数组")
    return value


def decode(raw: bytes):
    if len(raw) > MAX_BYTES:
        raise DataError("文件超过 128 MB 上限")
    if raw.startswith(PREFIX):
        compressed = bytes((c - KEY[i % len(KEY)]) % 256 for i, c in enumerate(raw[len(PREFIX):]))
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
                plain = stream.read(MAX_BYTES + 1)
        except (OSError, EOFError) as exc:
            raise DataError("旧版缓存已损坏或格式不受支持") from exc
        return parse_json(plain), "legacy-cache"
    return parse_json(raw), "json"


def encode(value, kind: str) -> bytes:
    try:
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")
    except (ValueError, RecursionError, TypeError) as exc:
        raise DataError(f"无法编码数据：{exc}") from exc
    if len(raw) > MAX_BYTES:
        raise DataError("导出数据超过 128 MB 上限")
    if kind == "json":
        return raw
    if kind != "legacy-cache":
        raise DataError("未知文件格式")
    compressed = gzip.compress(raw, mtime=0)
    result = PREFIX + bytes((c + KEY[i % len(KEY)]) % 256 for i, c in enumerate(compressed))
    if len(result) > MAX_BYTES:
        raise DataError("缓存超过 128 MB 上限")
    return result


def get_at(value, path):
    for key in path:
        value = value[key]
    return value


def pointer(path):
    return "/" + "/".join(str(k).replace("~", "~0").replace("/", "~1") for k in path)


def convert_scalar(text: str, previous):
    try:
        if isinstance(previous, str):
            return text
        if isinstance(previous, bool):
            if text.strip().lower() not in ("true", "false"):
                raise DataError("布尔值只能填写 true 或 false")
            return text.strip().lower() == "true"
        if isinstance(previous, int):
            number = int(text)
            if not -(2**31) <= number <= 2**31 - 1:
                raise DataError("整数必须在 32 位有符号整数范围内")
            return number
        if isinstance(previous, float):
            number = float(text)
            if not math.isfinite(number):
                raise DataError("数字必须是有限值")
            return number
    except ValueError as exc:
        raise DataError("数值格式不正确") from exc
    raise DataError("该字段不可直接编辑")


class Document:
    def __init__(self, path):
        self.source = Path(path).resolve(strict=True)
        with self.source.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        self.data, self.kind = decode(raw)
        self.source_hash = hashlib.sha256(raw).hexdigest()
        self.changes = {}
        self.structural_changes = []

    @property
    def change_count(self):
        return len(self.changes) + len(self.structural_changes)

    def set_many(self, edits):
        # Validate every edit before mutating anything.
        staged = []
        for path, text in edits:
            path = tuple(path)
            if not path:
                raise DataError("不能替换根对象")
            old = get_at(self.data, path)
            new = convert_scalar(text, old)
            staged.append((path, new))
        for path, new in staged:
            old = self.changes[path][0] if path in self.changes else get_at(self.data, path)
            get_at(self.data, path[:-1])[path[-1]] = new
            if old == new:
                self.changes.pop(path, None)
            else:
                self.changes[path] = (old, new)

    def replace_value(self, path, value):
        """Replace an existing list/dictionary as one reversible transaction."""
        path = tuple(path)
        if not path:
            raise DataError("不能替换根对象")
        current = get_at(self.data, path)
        if not isinstance(current, (list, dict)) or not isinstance(value, type(current)):
            raise DataError("复合字段类型不匹配")
        original = self.changes[path][0] if path in self.changes else copy.deepcopy(current)
        replacement = copy.deepcopy(value)
        get_at(self.data, path[:-1])[path[-1]] = replacement
        if original == replacement:
            self.changes.pop(path, None)
        else:
            self.changes[path] = (original, copy.deepcopy(replacement))

    def replace_scalar(self, path, value):
        """Replace an existing scalar, including nullable override fields."""
        path = tuple(path)
        if not path:
            raise DataError("不能替换根对象")
        current = get_at(self.data, path)
        if isinstance(current, (dict, list)) or isinstance(value, (dict, list)):
            raise DataError("该字段不是可替换的标量")
        original = self.changes[path][0] if path in self.changes else current
        get_at(self.data, path[:-1])[path[-1]] = value
        if original == value:
            self.changes.pop(path, None)
        else:
            self.changes[path] = (original, value)

    def append(self, path, value):
        path = tuple(path)
        target = get_at(self.data, path)
        if not isinstance(target, list):
            raise DataError("目标字段不是列表，无法添加")
        item = copy.deepcopy(value)
        target.append(item)
        self.structural_changes.append(("append", path, len(target) - 1, copy.deepcopy(item)))
        return len(target) - 1

    def add_mapping(self, path, key, value):
        path = tuple(path)
        target = get_at(self.data, path)
        if not isinstance(target, dict):
            raise DataError("目标字段不是对象，无法添加")
        if key in target:
            raise DataError("目标键已存在")
        target[key] = copy.deepcopy(value)
        self.structural_changes.append(("dict_add", path, key, copy.deepcopy(value)))

    def remove_at(self, path, index):
        path = tuple(path)
        target = get_at(self.data, path)
        if not isinstance(target, list) or not isinstance(index, int) or not 0 <= index < len(target):
            raise DataError("目标列表或删除位置无效")
        item = copy.deepcopy(target[index])
        target.pop(index)
        self.structural_changes.append(("list_remove", path, index, item))
        return item

    def remove_mapping(self, path, key):
        path = tuple(path)
        target = get_at(self.data, path)
        if not isinstance(target, dict) or key not in target:
            raise DataError("目标对象字段不存在")
        item = copy.deepcopy(target[key])
        del target[key]
        self.structural_changes.append(("dict_remove", path, key, item))
        return item

    def reset(self):
        for operation, path, index, _item in reversed(self.structural_changes):
            target = get_at(self.data, path)
            if operation == "append":
                if index != len(target) - 1:
                    raise DataError("结构修改顺序异常，无法安全撤销")
                target.pop()
            elif operation == "dict_add":
                if index not in target:
                    raise DataError("结构修改已发生外部变化，无法安全撤销")
                del target[index]
            elif operation == "list_remove":
                if not isinstance(target, list) or not 0 <= index <= len(target):
                    raise DataError("列表删除记录已发生外部变化，无法安全撤销")
                target.insert(index, copy.deepcopy(_item))
            elif operation == "dict_remove":
                if not isinstance(target, dict) or index in target:
                    raise DataError("对象删除记录已发生外部变化，无法安全撤销")
                target[index] = copy.deepcopy(_item)
            else:
                raise DataError("未知结构修改，无法安全撤销")
        # Restore scalars after list/dictionary shape is back to its original form.
        # A scalar inside an item added during this session legitimately no longer exists.
        for path, (old, _) in self.changes.items():
            try:
                get_at(self.data, path[:-1])[path[-1]] = old
            except (KeyError, IndexError, TypeError):
                pass
        self.changes.clear()
        self.structural_changes.clear()

    def export(self, destination, kind=None):
        requested = Path(destination)
        if requested.is_symlink():
            raise DataError("不支持符号链接目标")
        target = requested.resolve()
        if target == self.source or (target.exists() and os.path.samefile(target, self.source)):
            raise DataError("请导出到新文件；此版本保留原文件不变")
        if target.is_symlink():
            raise DataError("不支持符号链接目标")
        payload = encode(self.data, kind or self.kind)
        # Create-only export prevents accidentally replacing any existing save.
        # Temporary data is fully flushed before the no-overwrite rename.
        fd, temporary = tempfile.mkstemp(prefix=".ggbh-", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            backup_dir = target.parent / "GGBH-backups"
            backup_dir.mkdir(exist_ok=True)
            backup = backup_dir / (datetime.now().strftime("%Y%m%d-%H%M%S-%f") + "-" + uuid4().hex + ".original")
            with self.source.open("rb") as stream:
                original_bytes = stream.read(MAX_BYTES + 1)
            if hashlib.sha256(original_bytes).hexdigest() != self.source_hash:
                raise DataError("原文件在打开后发生变化，请重新打开后操作")
            with backup.open("xb") as stream:
                stream.write(original_bytes)
                stream.flush()
                os.fsync(stream.fileno())
            # Windows rename fails when destination exists. On other systems,
            # link provides equivalent atomic, create-only publication.
            if os.name == "nt":
                os.rename(temporary, target)
            else:
                os.link(temporary, target)
            return backup
        finally:
            Path(temporary).unlink(missing_ok=True)


FIELDS = [
    ("年龄（月）", "q.y"), ("寿命（月）", "q.u"), ("心情", "q.qx"), ("心情上限", "q.qc"),
    ("健康", "q.l"), ("健康上限", "q.z"), ("精力", "q.5"), ("精力上限", "q.6"),
    ("体力", "q.x"), ("体力上限", "q.c"), ("灵力", "q.v"), ("灵力上限", "q.b"),
    ("念力", "q.n"), ("念力上限", "q.m"), ("幸运", "q.4"), ("悟性", "q.k"),
    ("魅力", "q.i"), ("声望", "q.a"), ("攻击", "q.1"), ("防御", "q.2"),
    ("脚力", "q.3"), ("暴击", "q.7"), ("护心", "q.9"), ("道点", "q.j"),
    ("刀法资质", "q.qd"), ("枪法资质", "q.qs"), ("剑法资质", "q.qa"), ("拳法资质", "q.qf"),
    ("掌法资质", "q.qg"), ("指法资质", "q.qh"), ("火灵根", "q.qt"), ("风灵根", "q.qy"),
    ("雷灵根", "q.qu"), ("土灵根", "q.qo"), ("木灵根", "q.qp"), ("水灵根", "q.qi"),
    ("炼丹", "q.qj"), ("炼器", "q.qk"), ("风水", "q.ql"), ("画符", "q.qz"),
    ("药材", "q.wq"), ("矿材", "q.ww"),
]


def find_roles(root):
    stack = [((), root)]
    while stack:
        path, item = stack.pop()
        if isinstance(item, dict):
            q = item.get("q")
            if isinstance(q, dict) and isinstance(q.get("q"), list) and len(q["q"]) >= 2:
                names = q["q"][:2]
                if all(isinstance(s, str) for s in names):
                    yield path, "".join(names)
                    continue
            stack.extend((path + (k,), v) for k, v in reversed(list(item.items())) if isinstance(v, (dict, list)))
        elif isinstance(item, list):
            stack.extend((path + (i,), v) for i, v in reversed(list(enumerate(item))) if isinstance(v, (dict, list)))
