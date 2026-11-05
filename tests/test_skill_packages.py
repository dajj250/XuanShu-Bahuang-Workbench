import unittest

from ggbh.skill_packages import build_package, select_template_skills, template_by_id, templates


class SkillPackageTests(unittest.TestCase):
    def test_templates_have_sources_and_slots(self):
        rows = templates()
        self.assertGreaterEqual(len(rows), 44)
        self.assertTrue(all(row["source"].startswith("https://") and row["slots"] for row in rows))
        self.assertEqual(len({row["id"] for row in rows}), len(rows))
        self.assertEqual(len({row["name"] for row in rows}), len(rows))

    def test_full_build_matrix_contains_requested_reference(self):
        rows = [row for row in templates() if row["id"].startswith("guide_")]
        self.assertEqual(len(rows), 30)
        self.assertTrue(all("9544643534" in row["reference"] for row in rows))
        self.assertEqual(template_by_id("guide_fire_sword")["name"], "全流派·火剑")
        self.assertEqual(template_by_id("guide_pure_spear")["name"], "全流派·纯枪")

    def test_template_selects_one_skill_per_slot(self):
        template = template_by_id("fire_sword")
        skills = [
            {"name": "悟道月影剑", "rawValues": [1, 8], "type": 1},
            {"name": "绝影剑", "rawValues": [2, 8], "type": 2},
            {"name": "火身法", "rawValues": [3, 8], "type": 3},
        ]
        matched, missing = select_template_skills(template, skills)
        self.assertEqual([row["name"] for row in matched], ["悟道月影剑", "绝影剑", "火身法"])
        self.assertTrue(missing)

    def test_package_copies_raw_values(self):
        source = {"unitId": "u1", "name": "甲"}
        skill = {"name": "月影剑", "rawValues": [101, 8, 9], "type": 1, "exp": 600}
        package = build_package("测试", source, [skill], "fire_sword")
        skill["rawValues"][0] = 0
        self.assertEqual(package["version"], "1.1.1")
        self.assertEqual(package["skills"][0]["rawValues"][0], 101)


if __name__ == "__main__":
    unittest.main()
