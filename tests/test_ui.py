from pathlib import Path
import tempfile
import unittest

from ggbh.core import Document
from ggbh.ui import Editor


class InterfaceTests(unittest.TestCase):
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
