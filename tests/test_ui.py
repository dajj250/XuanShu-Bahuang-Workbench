from pathlib import Path
import tempfile
import tkinter as tk
import unittest

from ggbh.core import Document
from ggbh.ui import Editor


class InterfaceTests(unittest.TestCase):
    def test_role_live_write_routes_supported_fields_to_client(self):
        app = Editor()
        try:
            app.withdraw()
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "role.json"
                path.write_text('{"allUnit":{"npc":{"q":{"x":10,"1":2,"qa":12}}}}', encoding="utf-8")
                app.doc = Document(path)
                app.role_path = ("allUnit", "npc")
                app.form = [
                    (("allUnit", "npc", "q", "x"), tk.StringVar(app, value="88")),
                    (("allUnit", "npc", "q", "1"), tk.StringVar(app, value="66")),
                    (("allUnit", "npc", "q", "qa"), tk.StringVar(app, value="99")),
                ]
                app.special_form = [
                    (("allUnit", "npc", "q", "f"), tk.StringVar(app, value="内在 · 7"), "set"),
                    (("allUnit", "npc", "qe", "y"), tk.StringVar(app, value="道种 · 9"), "set"),
                    (("allUnit", "npc", "qe", "u"), tk.StringVar(app, value="是 · 2"), "set"),
                ]
                app.live.connected = True
                sent = []
                app.live_send_as = lambda command, payload, response: sent.append((command, payload, response))
                app.apply_role_live()
                self.assertEqual(len(sent), 6)
                self.assertIn(("setRuntimeRoleScalar", {"unitId": "npc", "field": "hp", "value": 88}, "roleWrite"), sent)
                self.assertIn(("setRuntimeRoleScalar", {"unitId": "npc", "field": "basisSword", "value": 99}, "roleWrite"), sent)
                self.assertIn(("setRuntimeRoleProfileField", {"unitId": "npc", "field": "isHero", "value": 2}, "roleWrite"), sent)
        finally:
            app.destroy()

    def test_role_live_write_ignores_unchanged_decimal_intimacy(self):
        app = Editor()
        try:
            app.withdraw()
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "role.json"
                path.write_text('{"allUnit":{"npc":{"q":{"x":10},"x":{"s":300.0}}}}', encoding="utf-8")
                app.doc = Document(path)
                app.role_path = ("allUnit", "npc")
                hp = tk.StringVar(app, value="88")
                intimacy = tk.StringVar(app, value="300.0")
                app.form = [(('allUnit', 'npc', 'q', 'x'), hp)]
                app.special_form = [(('allUnit', 'npc', 'x', 's'), intimacy, "set")]
                app.live.connected = True
                sent = []
                app.live_send_as = lambda command, payload, response: sent.append((command, payload, response))
                app.apply_role_live()
                self.assertEqual(sent, [
                    ("setRuntimeRoleScalar", {"unitId": "npc", "field": "hp", "value": 88}, "roleWrite")
                ])

                sent.clear()
                hp.set("10")
                intimacy.set("450.0")
                app.apply_role_live()
                self.assertEqual(sent, [
                    ("setRuntimeRoleProfileField",
                     {"unitId": "npc", "field": "intimacyToPlayer", "value": 450}, "roleWrite")
                ])
        finally:
            app.destroy()

    def test_relation_tree_plain_click_selection_accumulates(self):
        app = Editor()
        try:
            app.withdraw()
            tree = app.relation_widgets["好友"]["tree"]
            tree.insert("", "end", iid="0", values=("甲", "a", 100))
            tree.insert("", "end", iid="1", values=("乙", "b", 200))
            self.assertEqual(app.toggle_tree_item(tree, "0"), "break")
            app.toggle_tree_item(tree, "1")
            self.assertEqual(set(tree.selection()), {"0", "1"})
            app.toggle_tree_item(tree, "0")
            self.assertEqual(tree.selection(), ("1",))
        finally:
            app.destroy()

    def test_school_workspace_tabs_filter_sort_and_selection_scope(self):
        app = Editor()
        try:
            app.withdraw()
            self.assertEqual([app.school_pages.tab(tab, "text") for tab in app.school_pages.tabs()],
                             ["基础资料", "成员名册", "发展管理"])
            app.school_member_rows = [
                {"name": "甲", "post": "外门弟子", "grade": "练气", "path": ("u", 0)},
                {"name": "乙", "post": "宗主", "grade": "元婴", "path": ("u", 1)},
            ]
            app.school_post_box.configure(values=["全部职位", "宗主", "外门弟子"])
            app.school_member_query.set("乙")
            self.assertEqual([row["name"] for row in app.visible_school_member_rows], ["乙"])
            app.school_member_query.set("")
            app.school_post_filter.set("外门弟子")
            app.refresh_school_member_view()
            self.assertEqual([row["name"] for row in app.visible_school_member_rows], ["甲"])
            app.school_post_filter.set("全部职位")
            app.refresh_school_member_view()
            app.school_action_scope.set("选中成员")
            app.school_member_tree.selection_set("0")
            self.assertEqual(len(app.school_action_members()), 1)
            app.sort_school_members("name")
            self.assertEqual(len(app.visible_school_member_rows), 2)
        finally:
            app.destroy()

    def test_all_large_tree_pages_are_accessible(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demo.json"
            import json
            path.write_text(json.dumps({"bulk": list(range(1201))}))
            app = Editor()
            try:
                app.withdraw()
                app.doc = Document(path)
                app.refresh_tree()
                root = app.tree.get_children()[0]
                bulk = app.tree.get_children(root)[0]
                app.populate(bulk)
                self.assertEqual(len(app.tree.get_children(bulk)), 501)
                more = app.tree.get_children(bulk)[-1]
                app.tree.focus(more)
                app.load_more()
                self.assertEqual(len(app.tree.get_children(bulk)), 1001)
                more = app.tree.get_children(bulk)[-1]
                app.tree.focus(more)
                app.load_more()
                self.assertEqual(len(app.tree.get_children(bulk)), 1201)
                self.assertFalse(app.paging)
            finally:
                app.update()
                app.destroy()

    def test_role_edit_and_tree_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demo.json"
            path.write_text('{"units":[{"q":{"q":["Test","Role"],"1":20,"2":10}}]}')
            app = Editor()
            try:
                app.withdraw()
                app.doc = Document(path)
                from ggbh.core import find_roles
                app.roles = list(find_roles(app.doc.data))
                app.filter_roles()
                self.assertEqual(app.role_list.size(), 1)
                app.role_list.selection_set(0)
                app.select_role()
                self.assertEqual(len(app.form), 2)
                app.form[0][1].set("80")
                app.apply_role()
                self.assertEqual(app.doc.data["units"][0]["q"]["1"], 80)
                self.assertEqual(len(app.doc.changes), 1)
                root = app.tree.get_children()[0]
                self.assertTrue(app.tree.get_children(root))
                app.search.set("missing")
                self.assertEqual(app.role_list.size(), 0)
                app.doc.export(Path(directory) / "edited.json")
                self.assertIn('"1": 80', (Path(directory) / "edited.json").read_text(encoding="utf-8"))
                app.update()
            finally:
                app.destroy()


if __name__ == "__main__":
    unittest.main()
