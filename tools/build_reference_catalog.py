"""Extract searchable names from the user-provided legacy reference database."""
import json
import sqlite3
import sys
from pathlib import Path


def rows(connection, table, extra=()):
    result = {}
    for row in connection.execute(f"SELECT ID, Name{''.join(', ' + value for value in extra)} FROM {table}"):
        result[str(row[0])] = {"name": row[1] or str(row[0])}
        for index, value in enumerate(extra, 2):
            result[str(row[0])][value] = row[index]
    return result


source = Path(sys.argv[1]).resolve(strict=True)
destination = Path(sys.argv[2]).resolve()
connection = sqlite3.connect(str(source))
data = {
    "source": "用户提供的旧版 HTSourceData.db；新版未知 ID 仍可按编号操作",
    "born_luck": rows(connection, "BornLuck"),
    "reverse_fate": rows(connection, "Fate"),
    "taoist_seeds": rows(connection, "TaoistSeed", ("HeartSkills",)),
    "taoist_levels": rows(connection, "TaoistLevel"),
    "in_traits": rows(connection, "InTrait"),
    "out_traits": rows(connection, "OutTrait"),
    "hobbies": rows(connection, "Hobby"),
    "appellations": rows(connection, "Appellation"),
    "souls": rows(connection, "Elder"),
    "directions": rows(connection, "SkillGroup"),
    "skill_types": rows(connection, "SkillType"),
    "skill_info": rows(connection, "SkillInfo", ("TypeID",)),
    "skill_grades": rows(connection, "Grade"),
    "skill_effects": [
        {"skill_id": row[0], "id": row[1], "name": row[2] or str(row[1])}
        for row in connection.execute("SELECT ID, ValueID, Tips FROM SkillEffect")
        if row[1] is not None
    ],
}
destination.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
