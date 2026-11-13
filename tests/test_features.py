import json
from pathlib import Path
import tempfile
import unittest

from ggbh.core import Document, DataError, decode
from ggbh.features import (Catalog, UNIT_CACHE, discover_saves, inventory, set_quantity, delete_items, add_item,
                           attribute_values, paste_attributes, refill, role_info,
                           relation_rows, skill_rows, appearance_rows, fate_rows, school_rows,
                           editable_page_rows, add_relationship, remove_relationship, relationship_tables,
                           perfect_skill_comprehension,
                           enable_skill_effects, fate_entries, add_fate, add_fates, replace_fate, delete_fate,
                           special_attribute_rows, skill_records, skill_effect_candidates,
                           update_skill, pinyin_initials)
from ggbh.features import (potmon_records, set_potmon_contract, update_potmon, potmon_skills,
                           add_potmon_skills, delete_potmon_skills, appearance_data, update_appearance)
from ggbh.features import (school_data, update_school, update_school_main_skills, school_members,
                           school_batch_genius, school_batch_salary, school_batch_friend, import_roles)
from ggbh.features import installation_status
from ggbh.protocol import unpack_string


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        role = {"q": {"q": ["Test", "Role"], "r": 1, "d": 1, "x": 5, "c": 100, "1": 20},
                "z": {"allProps": [{"q": "item-unique-id", "w": [1, 10001, 10], "e": "unchanged"},
                                    {"q": "equipment", "w": [2, 123, 999]}]}}
        path = self.root / "demo.json"
        path.write_text(json.dumps({"allUnit": {"a": role, "b": role}}))
        self.doc = Document(path)
        self.a = ("allUnit", "a")
        self.b = ("allUnit", "b")

    def test_copy_refill_reset_and_identity(self):
        self.doc.set_many([(self.a + ("q", "1"), "80")])
        values = attribute_values(self.doc, self.a)
        paste_attributes(self.doc, self.b, values)
        self.assertEqual(self.doc.data["allUnit"]["b"]["q"]["1"], 80)
        self.assertEqual(self.doc.data["allUnit"]["b"]["q"]["q"], ["Test", "Role"])
        refill(self.doc, [self.a, self.b])
        self.assertEqual(self.doc.data["allUnit"]["b"]["q"]["x"], 100)
        self.doc.reset()
        self.assertEqual(self.doc.data["allUnit"]["b"]["q"]["x"], 5)
        self.assertEqual(self.doc.data["allUnit"]["a"]["q"]["1"], 20)

    def test_installation_status_accepts_current_and_legacy_bridge_names(self):
        game = self.root / "game"
        mods = game / "Mods"
        mods.mkdir(parents=True)
        (mods / "XuanShu.GameBridge.dll").touch()
        self.assertTrue(installation_status(game)["玄枢 GameBridge 游戏客户端"])
        (mods / "XuanShu.GameBridge.dll").unlink()
        (mods / "GGBH.BridgeMod.dll").touch()
        self.assertTrue(installation_status(game)["玄枢 GameBridge 游戏客户端"])

    def test_repeated_edit_tracks_original(self):
        p = self.a + ("q", "1")
        self.doc.set_many([(p, "40")])
        self.doc.set_many([(p, "60")])
        self.assertEqual(self.doc.changes[p], (20, 60))
        self.doc.set_many([(p, "20")])
        self.assertNotIn(p, self.doc.changes)

    def test_normal_and_battle_appearance_use_verified_paths(self):
        role = self.doc.data["allUnit"]["a"]
        role["q"]["e"] = {"q": 1, "w": 91001, "e": 15001, "r": 16001, "t": 11001,
                            "y": 12001, "u": 13001, "i": 14001, "o": 17001, "p": 18001,
                            "a": 90001, "s": 20001, "d": 21001, "f": 22001, "g": 23001}
        role["q"]["w"] = {"q": 1, "w": 18001, "e": 90001, "r": 91001, "t": 15001, "y": 11001}
        current = appearance_data(self.doc, self.a)
        self.assertEqual(current["normal"]["前发"], 16001)
        self.assertEqual(current["battle"]["衣服"], 18001)
        normal = dict(current["normal"], 性别=0, 前发=16099, 左脸=22099)
        battle = dict(current["battle"], 衣服=18099, 脸型=11099)
        self.assertEqual(update_appearance(self.doc, self.a, normal, battle), 21)
        self.assertEqual(role["q"]["e"]["r"], 16099)
        self.assertEqual(role["q"]["e"]["f"], 22099)
        self.assertEqual(role["q"]["e"]["q"], 0)
        self.assertEqual(role["q"]["w"]["w"], 18099)
        self.assertEqual(role["q"]["w"]["y"], 11099)
        self.doc.reset()
        self.assertEqual(role["q"]["e"]["r"], 16001)
        self.assertEqual(role["q"]["w"]["w"], 18001)

    def test_school_companion_fields_skills_members_and_batch_actions(self):
        role = self.doc.data["allUnit"]["a"]
        role.update({"u": "school1", "qe": {"u": 0, "y": 0, "h": 0, "s": 0}, "x": {"s": 0}})
        school_path = self.root / "school.json"
        school_path.write_text(json.dumps({"allBuild": {"school1": {
            "money": 100, "reputation": 20, "totalMember": 1,
            "npcSchoolMain": "a", "npcBigElders": [], "npcElders": [],
            "npcInherit": [], "npcIn": [], "npcOut": [],
            "values": [json.dumps({"stand": 1, "fateID": 1001,
                                   "schoolSloganItem1Type1": 11, "schoolSloganItem1Type2": 12,
                                   "schoolSloganItem2Type1": 21, "schoolSloganItem2Type2": 22})],
            "propertyData": {"prosperous": 30, "loyal": 40, "Loyal": 40, "medicina": 5, "mine": 6,
                             "fixStand": 0, "fixFateID": 0, "fixName": None, "fixAreaName": None,
                             "fixSloganItem1Type1": 0, "fixSloganItem1Type2": 0,
                             "fixSloganItem2Type1": 0, "fixSloganItem2Type2": 0},
            "manorData": {"mainManor": {"stable": 50, "Stable": 50}},
            "allBuildSub": {"1002": {"objData": {"allObject": {"": {"data": json.dumps({
                "weaponType": ["basBlade"], "magicType": ["basFire"], "keep": 7})}}}}}
        }}}))
        school_doc = Document(school_path)
        data = school_data(school_doc, self.doc, self.a)
        self.assertEqual(data["fields"]["立场"], 1)
        self.assertTrue(data["main_skills"]["刀"])
        self.assertEqual(update_school(school_doc, self.doc, self.a,
                                      dict(data["fields"], 灵石="200", 宗门名="测试宗门")), 2)
        selected = dict(data["main_skills"], 剑=True, 火=False)
        self.assertEqual(update_school_main_skills(school_doc, self.doc, self.a, selected), 2)
        members, souls = school_members(school_doc, self.doc, self.a, Catalog())
        self.assertEqual((len(members), len(souls)), (1, 0))
        self.assertEqual(school_batch_genius(self.doc, members, 2001, 700181), 1)
        self.assertEqual(school_batch_salary(self.doc, members, 50), 1)
        self.assertEqual(school_batch_friend(self.doc, members, 300), 1)
        self.assertEqual(role["qe"], {"u": 2, "y": 2001, "h": 3, "s": 700181})
        self.assertEqual(role["z"]["allProps"][0]["w"][2], 60)
        self.assertEqual(role["x"]["s"], 300)
        school_doc.reset()
        self.doc.reset()
        self.assertEqual(school_doc.data["allBuild"]["school1"]["money"], 100)

    def test_import_roles_creates_fresh_ids_and_sanitizes_cross_save_references(self):
        source_path = self.root / "source.json"
        def source_role(name, school, parents, intimacy):
            return {"q": {"q": [name, "君"], "r": 1, "d": 1}, "u": school,
                    "x": {"q": parents, "w": [], "e": [], "r": [], "t": [], "y": [], "u": [],
                          "i": "", "o": [], "p": [], "a": [], "s": 500.0, "d": intimacy},
                    "z": {"allProps": [{"q": "token", "w": [1, 10001, 9]}]}}
        source_path.write_text(json.dumps({"allUnit": {
            "srcA": source_role("甲", "oldSchool", ["srcB", "srcC"], {"srcB": 300, "srcC": 50}),
            "srcB": source_role("乙", "oldSchool", ["srcA"], {"srcA": 300}),
            "srcC": source_role("丙", "oldSchool", [], {}),
        }}))
        source = Document(source_path)
        imported = import_roles(self.doc, source, [("allUnit", "srcA"), ("allUnit", "srcB")])
        self.assertEqual(len(imported), 2)
        new_a, new_b = imported[0]["new_id"], imported[1]["new_id"]
        self.assertNotIn(new_a, ("a", "b", "srcA"))
        self.assertNotEqual(new_a, new_b)
        role_a = self.doc.data["allUnit"][new_a]
        self.assertEqual(role_a["u"], "")
        self.assertEqual(role_a["x"]["q"], [new_b])
        self.assertEqual(role_a["x"]["d"], {new_b: 300})
        self.assertEqual(role_a["x"]["s"], 0.0)
        self.assertEqual(role_a["z"]["allProps"][0]["w"], [1, 10001, 9])
        self.doc.reset()
        self.assertEqual(set(self.doc.data["allUnit"]), {"a", "b"})

    def test_inventory_quantity_preserves_metadata(self):
        rows = inventory(self.doc, self.a, Catalog())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], 10001)
        set_quantity(self.doc, rows[0], "30")
        item = self.doc.data["allUnit"]["a"]["z"]["allProps"][0]
        self.assertEqual(item, {"q": "item-unique-id", "w": [1, 10001, 30], "e": "unchanged"})
        for bad in ["-1", "0", "abc", str(2**31)]:
            with self.assertRaises(DataError):
                set_quantity(self.doc, rows[0], bad)

    def test_item_name_pinyin_initials(self):
        self.assertEqual(pinyin_initials("灵石"), "ls")
        self.assertEqual(pinyin_initials("九转还魂丹2"), "jzhhd2")

    def test_potmon_attributes_contract_skills_and_reset(self):
        original = {
            "devilDemonData": {"potmonData": {"potMonList": [
                {"soleId": "wild", "id": 1002, "fixName": "", "sex": 2, "health": 0,
                 "converState": 0, "unitId": "", "battleSkillMax": 1, "battleSkills": [5151],
                 "lifeSkills": [], "monstPropertyScale": {"hp": "1|88"}},
                {"soleId": "furry", "id": 1002, "fixName": "", "sex": 2, "health": 0,
                 "converState": 1, "unitId": "npc", "battleSkillMax": 1, "battleSkills": [],
                 "lifeSkills": [], "monstPropertyScale": {"hp": "1|90"}},
            ]}}}
        path = self.root / "world.json"
        path.write_text(json.dumps(original))
        world = Document(path)
        rows = potmon_records(world)
        with self.assertRaises(DataError):
            set_potmon_contract(world, rows[0], True)
        update_potmon(world, rows[0], "小药灵", "男", "正常", {"体力": "95"})
        self.assertEqual(world.data["devilDemonData"]["potmonData"]["potMonList"][0]["monstPropertyScale"]["hp"], "1|95")
        set_potmon_contract(world, rows[1], True)
        self.assertEqual(world.data["devilDemonData"]["potmonData"]["potMonList"][1]["converState"], 2)
        self.assertEqual(add_potmon_skills(world, rows[0], [
            {"type": "战斗技能", "id": 5152}, {"type": "生活技能", "id": 1001}]), 2)
        skills = potmon_skills(world, rows[0])
        chosen = [skill for skill in skills if skill["id"] in (5152, 1001)]
        self.assertEqual(delete_potmon_skills(world, rows[0], chosen), 2)
        world.reset()
        self.assertEqual(world.data, original)

    def test_add_item_tracks_structure_and_resets(self):
        original = list(self.doc.data["allUnit"]["a"]["z"]["allProps"])
        add_item(self.doc, self.a, "10002", "7", Catalog())
        rows = inventory(self.doc, self.a, Catalog())
        self.assertTrue(any(row["id"] == 10002 and row["quantity"] == 7 for row in rows))
        self.assertEqual(self.doc.change_count, 1)
        with self.assertRaises(DataError):
            add_item(self.doc, self.a, "10002", "1", Catalog())
        self.doc.reset()
        self.assertEqual(self.doc.data["allUnit"]["a"]["z"]["allProps"], original)
        self.assertEqual(self.doc.change_count, 0)

    def test_force_delete_inventory_items_and_reset(self):
        original = json.loads(json.dumps(self.doc.data["allUnit"]["a"]["z"]["allProps"]))
        rows = inventory(self.doc, self.a, Catalog())
        self.assertEqual(delete_items(self.doc, self.a, rows), 1)
        self.assertEqual(len(self.doc.data["allUnit"]["a"]["z"]["allProps"]), 1)
        self.assertEqual(self.doc.data["allUnit"]["a"]["z"]["allProps"][0]["q"], "equipment")
        self.doc.reset()
        self.assertEqual(self.doc.data["allUnit"]["a"]["z"]["allProps"], original)

    def test_add_relationship_is_bidirectional_and_resettable(self):
        empty = {"q": ["", ""], "w": [], "e": [], "r": [], "t": [], "y": [],
                 "u": [], "i": "", "o": [], "p": [], "a": [], "s": 0.0, "d": {}}
        self.doc.data["allUnit"]["a"]["x"] = json.loads(json.dumps(empty))
        self.doc.data["allUnit"]["b"]["x"] = json.loads(json.dumps(empty))
        add_relationship(self.doc, self.a, self.b, "师父", 300)
        self.assertEqual(self.doc.data["allUnit"]["a"]["x"]["p"], ["b"])
        self.assertEqual(self.doc.data["allUnit"]["b"]["x"]["a"], ["a"])
        self.assertEqual(self.doc.data["allUnit"]["a"]["x"]["d"]["b"], 300.0)
        self.assertEqual(self.doc.data["allUnit"]["b"]["x"]["d"]["a"], 300.0)
        rows = relationship_tables(self.doc, self.a)
        self.assertEqual(rows["师父"], [{"id": "b", "name": "TestRole", "intimacy": 300.0}])
        remove_relationship(self.doc, self.a, self.b, "师父", True)
        self.assertEqual(self.doc.data["allUnit"]["a"]["x"]["p"], [])
        self.assertEqual(self.doc.data["allUnit"]["b"]["x"]["a"], [])
        self.assertEqual(self.doc.data["allUnit"]["a"]["x"]["d"], {})
        self.assertEqual(self.doc.data["allUnit"]["b"]["x"]["d"], {})
        self.doc.reset()
        self.assertEqual(self.doc.data["allUnit"]["a"]["x"], empty)
        self.assertEqual(self.doc.data["allUnit"]["b"]["x"], empty)

    def test_relationship_can_be_one_way(self):
        empty = {"q": ["", ""], "w": [], "e": [], "r": [], "t": [], "y": [],
                 "u": [], "i": "", "o": [], "p": [], "a": [], "s": 0.0, "d": {}}
        self.doc.data["allUnit"]["a"]["x"] = json.loads(json.dumps(empty))
        self.doc.data["allUnit"]["b"]["x"] = json.loads(json.dumps(empty))
        add_relationship(self.doc, self.a, self.b, "兄弟姐妹", 120, False)
        self.assertEqual(self.doc.data["allUnit"]["a"]["x"]["r"], ["b"])
        self.assertEqual(self.doc.data["allUnit"]["b"]["x"]["r"], [])
        self.assertEqual(self.doc.data["allUnit"]["a"]["x"]["d"], {"b": 120.0})
        self.assertEqual(self.doc.data["allUnit"]["b"]["x"]["d"], {})
        remove_relationship(self.doc, self.a, self.b, "兄弟姐妹", False)
        self.assertEqual(self.doc.data["allUnit"]["a"]["x"]["r"], [])
        self.assertEqual(self.doc.data["allUnit"]["a"]["x"]["d"], {})

    def test_friend_can_be_added_and_removed_bidirectionally(self):
        empty = {"q": ["", ""], "w": [], "e": [], "r": [], "t": [], "y": [],
                 "u": [], "i": "", "o": [], "p": [], "a": [], "s": 0.0, "d": {}}
        self.doc.data["allUnit"]["a"]["x"] = json.loads(json.dumps(empty))
        self.doc.data["allUnit"]["b"]["x"] = json.loads(json.dumps(empty))
        add_relationship(self.doc, self.a, self.b, "好友", 300, True)
        self.assertEqual(relationship_tables(self.doc, self.a)["好友"][0]["id"], str(self.b[-1]))
        self.assertEqual(relationship_tables(self.doc, self.b)["好友"][0]["id"], str(self.a[-1]))
        remove_relationship(self.doc, self.a, self.b, "好友", True)
        self.assertEqual(relationship_tables(self.doc, self.a)["好友"], [])
        self.assertEqual(relationship_tables(self.doc, self.b)["好友"], [])

    def test_batch_validation(self):
        self.doc.data["allUnit"]["b"]["q"]["c"] = -1
        with self.assertRaises(DataError):
            refill(self.doc, [self.a, self.b])
        self.assertEqual(self.doc.data["allUnit"]["a"]["q"]["x"], 5)

    def test_refill_preserves_values_above_base_maximum(self):
        self.doc.set_many([(self.a + ("q", "x"), "200")])
        refill(self.doc, [self.a])
        self.assertEqual(self.doc.data["allUnit"]["a"]["q"]["x"], 200)

    def test_save_discovery(self):
        for name in ["1_test", "cacheSimple", "2_empty"]:
            (self.root / name).mkdir()
        (self.root / "1_test" / UNIT_CACHE).write_bytes(b"data")
        (self.root / "cacheSimple" / UNIT_CACHE).write_bytes(b"data")
        self.assertEqual([slot.label for slot in discover_saves(self.root)], ["1_test"])

    def test_frame(self):
        payload = '{"ServerVersion":"1.9.8"}'.encode()
        self.assertEqual(unpack_string(bytes([len(payload)]) + payload), payload.decode())
        self.assertEqual(unpack_string(b"\x80\x01" + b"x" * 128), "x" * 128)
        for bad in [b"\x80", b"\xff\xff\xff\xff\x7f", b"\x03a", b"\x01\xff"]:
            with self.assertRaises(DataError):
                unpack_string(bad)

    def test_floating_overflow(self):
        with self.assertRaises(DataError):
            decode(b'{"x":1e9999}')

    def test_reference_page_readers_are_bounded_and_read_only(self):
        a = self.doc.data["allUnit"]["a"]
        a["x"] = {"r": ["b"], "d": {"b": 300}}
        a["k"] = {"skill-1": {"q": {"w": [0, 0, 0, 1, 101, 2]}}}
        a["q"]["e"] = {"q": 2, "r": 17, "y": 8}
        a["q"]["qb"] = [{"q": 2801}]
        a["u"] = "school-1"
        before = json.dumps(self.doc.data, sort_keys=True)
        self.assertTrue(any(row[0] == "兄弟姐妹" for row in relation_rows(self.doc, self.a)))
        self.assertEqual(skill_rows(self.doc, self.a, Catalog())[0][0], "武技/灵技")
        self.assertEqual(dict((row[0], row[2]) for row in appearance_rows(self.doc, self.a))["性别"], 2)
        self.assertIn(("先天气运", "2801"), fate_rows(self.doc, self.a))
        self.assertEqual(school_rows(self.doc, self.a)[0], ("宗门编号", "school-1"))
        self.assertEqual(json.dumps(self.doc.data, sort_keys=True), before)

    def test_perfect_skill_comprehension_and_effect_enable(self):
        skill = {"q": {"q": "skill-1", "w": [2, 0, 0, 1, 101, 2, 11, 22, -1, 4, 5], "e": ""},
                 "w": 7, "e": 0, "r": {"allObject": {}}}
        self.doc.data["allUnit"]["a"]["k"] = {"skill-1": skill}
        skills, effects = perfect_skill_comprehension(self.doc, self.a, "skill-1")
        self.assertEqual((skills, effects), (1, 2))
        self.assertEqual(skill["q"]["w"][-2:], [600, 600])
        self.assertEqual(enable_skill_effects(self.doc, self.a, "skill-1"), 1)
        self.assertEqual(skill["w"], 9999999)
        self.doc.reset()
        self.assertEqual(self.doc.data["allUnit"]["a"]["k"]["skill-1"]["q"]["w"][-2:], [4, 5])
        self.assertEqual(self.doc.data["allUnit"]["a"]["k"]["skill-1"]["w"], 7)

    def test_skill_unified_edit_and_reset(self):
        role = self.doc.data["allUnit"]["a"]
        role["k"] = {"skill-1": {"q": {"q": "skill-1", "w": [2, 0, 1, 1, 11432, 1, 31, -1, 20]},
                                      "w": 5, "e": 0, "r": {"allObject": {}}}}
        record = skill_records(self.doc, self.a, Catalog())[0]
        self.assertEqual((record["inheritance"], record["effects"], record["effect_exp"]), (1, [31], [20]))
        update_skill(self.doc, self.a, "skill-1", type_id=2, info_id=22111, grade_id=3,
                     inheritance=0, progress=99, effects=[41, 42] + [0] * 9,
                     effect_exp=[600, 300] + [0] * 9)
        self.assertEqual(role["k"]["skill-1"]["q"]["w"], [2, 0, 0, 2, 22111, 3, 41, 42, -1, 600, 300])
        self.assertEqual(role["k"]["skill-1"]["w"], 99)
        self.doc.reset()
        self.assertEqual(role["k"]["skill-1"]["q"]["w"], [2, 0, 1, 1, 11432, 1, 31, -1, 20])

    def test_skill_effect_numbers_follow_grade_and_payload_length(self):
        role = self.doc.data["allUnit"]["a"]
        role["k"] = {"skill-1": {"q": {"w": [2, 0, 0, 2, 22111, 3, 41, 42, -1, 600, 300]},
                                      "w": 1}}
        catalog = Catalog()
        catalog.skill_info = {"22111": {"name": "测试功法"}}
        catalog.skill_types = {"2": {"name": "绝技"}}
        catalog.skill_grades = {"3": {"name": "结晶"}}
        catalog.skill_effects = [{"skill_id": 22111, "id": 41, "name": "伤害提升&demo&%"}]
        catalog.skill_values = {"&demo+6": {"values": [10, 20, 30], "scale": "x1|f0"}}
        record = skill_records(self.doc, self.a, catalog)[0]
        self.assertEqual(record["effects"], [41, 42])
        self.assertEqual(record["effect_exp"], [600, 300])
        self.assertEqual(skill_effect_candidates(catalog, 2, 22111, 3)[0][1], "伤害提升30%")

    def test_four_fate_sections_add_replace_delete_and_reset(self):
        role = self.doc.data["allUnit"]["a"]
        role["q"]["qb"] = [{"q": 1101, "w": -1, "e": 1, "t": {"allObject": {}}}]
        role["q"]["qn"] = [{"q": 9000001, "w": -1, "e": 1, "t": {"allObject": {}}},
                              {"q": 700001, "w": -1, "e": 1, "t": {"allObject": {}}}]
        role["qr"] = {"2": {"quality": 5, "luck": 700002}}
        catalog = Catalog()
        self.assertEqual([row["id"] for row in fate_entries(self.doc, self.a, "先天气运", catalog)], [1101])
        self.assertEqual([row["id"] for row in fate_entries(self.doc, self.a, "后天气运", catalog)], [9000001])
        self.assertEqual([row["id"] for row in fate_entries(self.doc, self.a, "逆天改命", catalog)], [700001])
        self.assertEqual([row["id"] for row in fate_entries(self.doc, self.a, "道心", catalog)], [700002])
        add_fate(self.doc, self.a, "先天气运", 1102)
        entry = fate_entries(self.doc, self.a, "先天气运", catalog)[-1]
        replace_fate(self.doc, self.a, "先天气运", entry, 1103)
        self.assertEqual(role["q"]["qb"][-1]["q"], 1103)
        delete_fate(self.doc, self.a, "先天气运", fate_entries(self.doc, self.a, "先天气运", catalog)[0])
        self.assertEqual([item["q"] for item in role["q"]["qb"]], [1103])
        add_fate(self.doc, self.a, "道心", 700003)
        self.assertEqual(role["qr"]["3"]["luck"], 700003)
        self.assertTrue(any(item["q"] == 700003 for item in role["q"]["qn"]))
        add_fates(self.doc, self.a, "先天气运", [1104, 1105])
        self.assertEqual([item["q"] for item in role["q"]["qb"]], [1103, 1104, 1105])
        with self.assertRaises(DataError):
            add_fates(self.doc, self.a, "先天气运", [1104, 1106])
        self.assertFalse(any(item["q"] == 1106 for item in role["q"]["qb"]))
        self.doc.reset()
        self.assertEqual([item["q"] for item in role["q"]["qb"]], [1101])
        self.assertEqual(role["qr"], {"2": {"quality": 5, "luck": 700002}})

    def test_special_attribute_rows_use_verified_paths(self):
        role = self.doc.data["allUnit"]["a"]
        role.update({"qe": {"y": 1001, "h": 2, "i": 1001, "u": 2}, "b": {"q": 1},
                     "qt": {"w": [10]}, "x": {"s": 300}})
        role["q"].update({"f": 1, "g": 8, "h": 9, "qv": [201, 202, 203]})
        rows = special_attribute_rows(self.doc, self.a, Catalog())
        paths = {row["label"]: row["path"] for row in rows}
        self.assertEqual(paths["内在性格"], self.a + ("q", "f"))
        self.assertEqual(paths["道种"], self.a + ("qe", "y"))
        self.assertEqual(paths["道号"], self.a + ("qt", "w", 0))

    def test_reference_page_existing_scalars_are_editable_without_structure_changes(self):
        a = self.doc.data["allUnit"]["a"]
        a["x"] = {"r": ["b"], "d": {"b": 30}}
        a["k"] = {"skill-1": {"q": {"w": [0, 0, 0, 1, 101, 2]}}}
        a["q"]["e"] = {"r": 17}
        a["q"]["qb"] = [{"q": 2801}]
        a["u"] = "school-1"
        a["qy"] = {"level": 3, "members": [{"id": 1}]}
        cases = [("relation", "45"), ("skill", "4"), ("appearance", "19"),
                 ("school", "school-2"), ("potmon", "5"), ("fate", "2802")]
        for page, value in cases:
            rows = [row for row in editable_page_rows(self.doc, self.a, page, Catalog()) if row["path"]]
            self.assertTrue(rows, page)
            before_keys = set(a.keys())
            self.doc.set_many([(rows[0]["path"], value)])
            self.assertEqual(set(a.keys()), before_keys)
        self.assertEqual(a["x"]["d"]["b"], 45)
        self.assertEqual(a["k"]["skill-1"]["q"]["w"][5], 4)
        self.assertEqual(a["q"]["e"]["r"], 19)
        self.assertEqual(a["q"]["qb"][0]["q"], 2802)
