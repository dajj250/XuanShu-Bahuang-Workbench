from __future__ import annotations

import json
import queue
import sys
import threading
import webbrowser
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from PIL import Image, ImageTk

from .core import Document, DataError, FIELDS, find_roles, get_at, pointer
from .features import (Catalog, DEFAULT_GAME, discover_saves, role_info, attribute_values,
                       paste_attributes, refill, inventory, set_quantity, delete_items, add_item, installation_status,
                       relation_rows, add_relationship, remove_relationship, relationship_tables, RELATION_KINDS,
                       skill_rows, appearance_rows, fate_rows, school_rows, discover_mods,
                       editable_page_rows, perfect_skill_comprehension, enable_skill_effects,
                       FATE_SECTION_LABELS, fate_entries, fate_candidates, add_fate, add_fates, replace_fate, delete_fate,
                       special_attribute_rows, skill_records, skill_effect_candidates, update_skill, pinyin_initials,
                       UNIT_CACHE, WORLD_CACHE, SCHOOL_CACHE, POTMON_PROPERTY_FIELDS, potmon_catalog, potmon_records,
                       set_potmon_contract, update_potmon, potmon_skills, add_potmon_skills, delete_potmon_skills,
                       NORMAL_APPEARANCE_PATHS, BATTLE_APPEARANCE_PATHS, APPEARANCE_TYPES,
                       appearance_catalog, appearance_data, update_appearance, SCHOOL_MAIN_SKILLS,
                       school_data, update_school, update_school_main_skills, school_members,
                       school_batch_genius, school_batch_salary, school_batch_friend, import_roles)
from .live import LiveServer
from .skill_packages import (templates as skill_package_templates, template_by_id,
                             build_package, select_template_skills)
from .updater import APP_VERSION, is_newer, latest_release


APPEARANCE_SEX_OPTIONS = ["通用/无性 · 0", "男 · 1", "女 · 2"]


def resource_path(*parts):
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return root.joinpath(*parts)


class Editor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("玄枢 · 八荒编修台 1.1.3")
        self.geometry("1280x850")
        self.minsize(1000, 650)
        self.configure(bg="#eef2f6")
        self.doc = None
        self.world_doc = None
        self.school_doc = None
        self.nodes = {}
        self.roles = []
        self.form = []
        self.special_form = []
        self.role_path = None
        self.player_role_path = None
        self.sidebar_player_only = False
        self.scalar_path = None
        self.catalog = Catalog()
        self.attribute_clipboard = None
        self.loading = False
        self.load_results = queue.Queue()
        self.export_results = queue.Queue()
        self.busy_message = "正在读取数据，请等待完成"
        self.paging = {}
        self.inspector_paths = {}
        self.live = LiveServer()
        self.live_requests = {}
        self.live_after = None
        self.update_results = queue.Queue()
        self.update_repository = self.load_update_repository()
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=("Microsoft YaHei UI", 10))
        style.configure("TFrame", background="#eef2f6")
        style.configure("TLabel", background="#eef2f6", foreground="#25334a")
        style.configure("TButton", padding=(12, 7))
        style.configure("Treeview", rowheight=27)
        header = ttk.Frame(self, padding=20)
        header.pack(fill="x")
        ttk.Label(header, text="玄枢  /  八荒编修台", font=("Microsoft YaHei UI", 21, "bold")).pack(side="left")
        ttk.Label(header, text="1.1.3 · 官方模组桥接版", foreground="#62748c").pack(side="right")
        toolbar = ttk.Frame(self, padding=(20, 0, 20, 12))
        toolbar.pack(fill="x")
        for label, action in [("读取最新存档", self.open_latest_save), ("存档列表", self.choose_save),
                              ("打开文件", self.open_file), ("修改预览", self.preview),
                              ("撤销全部", self.reset), ("导出副本", self.export),
                              ("检查更新", lambda: self.check_for_updates(True))]:
            ttk.Button(toolbar, text=label, command=lambda f=action: self.guard(f)).pack(side="left", padx=(0, 8))
        self.info = tk.StringVar(value="打开 JSON 或旧版 .cache 文件开始；原文件保持不变。")
        ttk.Label(self, textvariable=self.info, padding=(20, 6), wraplength=1100).pack(fill="x")
        self.status = tk.StringVar(value="就绪")
        ttk.Label(self, textvariable=self.status, padding=(20, 8)).pack(side="bottom", fill="x")
        self.workspace = ttk.Frame(self, padding=(20, 0, 20, 12))
        self.workspace.pack(fill="both", expand=True)
        self.role_sidebar = ttk.Frame(self.workspace, width=245, padding=(0, 12, 14, 0))
        self.role_sidebar.pack(side="left", fill="y")
        self.build_role_sidebar(self.role_sidebar)
        self.book = ttk.Notebook(self.workspace)
        self.book.pack(side="left", fill="both", expand=True, pady=12)
        self.build_role_tab()
        self.build_fate_tab()
        self.build_relation_tab()
        self.build_skill_tab()
        self.build_skill_package_tab()
        self.build_inventory_tab()
        self.build_potmon_tab()
        self.build_appearance_tab()
        self.build_school_tab()
        self.build_tree_tab()
        self.build_live_tab()
        self.build_diagnostics_tab()
        self.build_sponsor_tab()
        self.build_credits_tab()
        help_tab = ttk.Frame(self.book, padding=24)
        self.book.add(help_tab, text="关于")
        ttk.Label(help_tab, justify="left", wraplength=980, text=(
            "工作流程\n\n1. 点击读取最新存档，或从存档列表选择槽位；也可打开备份中的 JSON / 旧版缓存。\n"
            "2. 在属性、关系、功法、物品、壶妖、形象、宗门页面暂存修改。\n"
            "3. 检查修改预览，导出到新文件；原文件保持不变并生成字节备份。\n"
            "4. 游戏内修改请进入实时连接页，读取当前玩家后点击引用修改。\n\n"
            "1.1.3 已实现\n\n基础属性实时读写；基础值和游戏显示值分开显示。\n"
            "先天气运、后天气运、逆天改命、道心四分栏，支持 ID/名称搜索及添加、替换、删除。\n"
            "属性页增加性格、爱好、关系、道心、身份五个并列栏目，统一点击引用修改。\n"
            "关系双向添加、属性页多选批量添加、好友管理和批量解除好友；普通物品新增和数量修改。\n"
            "已有好感、功法境界、功法完美参悟/词条生效、气运、壶妖标量、外貌 ID 和宗门字段修改。\n"
            "常态人物形象与战斗形象独立编辑；支持游戏外观 ID 下拉、手动 Mod ID、模板导入导出。\n"
            "自动检测 GGBH Bridge 和 ModExportData 目录；联网检查 GitHub 新版本，由使用者决定是否打开下载页。\n\n"
            "新增角色 A→B 技能包、多选打包、离线编辑、境界适配和流派模板；客户端改为官方模组工程。\n\n"
            "仍需实机验证\n\n官方模组导出、技能学习结果、资质同步、天骄和特殊能力、完整宗门操作。\n"
            "这些功能需要逐项实机验证后开放，避免单边引用或无效对象损坏存档。"
        )).pack(anchor="nw")
        self.book.bind("<<NotebookTabChanged>>", self.update_role_sidebar_visibility)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.live.start()
        self.live_after = self.after(250, self.poll_live)
        self.after(1600, lambda: self.check_for_updates(False))

    def load_update_repository(self):
        try:
            data = json.loads(resource_path("update-config.json").read_text(encoding="utf-8"))
            return str(data.get("repository") or "").strip()
        except (OSError, ValueError, TypeError):
            return ""

    def check_for_updates(self, manual=False):
        if not self.update_repository:
            if manual:
                messagebox.showinfo("检查更新", "尚未配置 GitHub 发布仓库。", parent=self)
            return
        self.status.set("正在连接 GitHub 检查更新…")

        def worker():
            try:
                self.update_results.put((manual, latest_release(self.update_repository), None))
            except Exception as exc:
                self.update_results.put((manual, None, str(exc)))

        threading.Thread(target=worker, daemon=True).start()
        self.after(100, self.poll_update_result)

    def poll_update_result(self):
        try:
            manual, release, error = self.update_results.get_nowait()
        except queue.Empty:
            self.after(100, self.poll_update_result)
            return
        if error:
            self.status.set("GitHub 更新检查暂时不可用")
            if manual:
                messagebox.showwarning("检查更新", f"暂时无法读取 GitHub 最新版本：\n{error}", parent=self)
            return
        latest = release["version"]
        if is_newer(latest, APP_VERSION):
            self.status.set(f"发现新版本 {latest}")
            if messagebox.askyesno("发现新版本", f"当前版本：{APP_VERSION}\n最新版本：{latest}\n\n是否打开 GitHub 下载页？\n工作台不会自动替换程序。", parent=self):
                webbrowser.open(release["url"])
        else:
            self.status.set(f"当前已是最新版 {APP_VERSION}")
            if manual:
                messagebox.showinfo("检查更新", f"当前已是最新版：{APP_VERSION}", parent=self)

    def guard(self, action):
        try:
            if self.loading:
                raise DataError(self.busy_message)
            action()
        except Exception as exc:
            messagebox.showerror("操作未完成", str(exc), parent=self)

    def confirm_discard(self):
        pending = self.doc and (
            any(v.get() != str(get_at(self.doc.data, p)) for p, v in self.form)
            or any(
                (self.value_id(v.get()) not in ("", "0") if mode == "append"
                 else self.value_id(v.get()) != str(get_at(self.doc.data, p)))
                for p, v, mode in self.special_form
            )
        )
        total_changes = ((self.doc.change_count if self.doc else 0) +
                         (self.world_doc.change_count if self.world_doc else 0) +
                         (self.school_doc.change_count if self.school_doc else 0))
        return not self.doc or (not total_changes and not pending) or messagebox.askyesno(
            "未导出的修改", "将放弃内存中的修改，是否继续？", parent=self)

    def close(self):
        if self.loading:
            messagebox.showinfo("操作进行中", self.busy_message, parent=self)
            return
        if self.confirm_discard():
            self.destroy()

    def destroy(self):
        if self.live_after is not None:
            try:
                self.after_cancel(self.live_after)
            except tk.TclError:
                pass
            self.live_after = None
        self.live.stop()
        super().destroy()

    def build_role_sidebar(self, side):
        self.role_sidebar_title = tk.StringVar(value="角色搜索")
        ttk.Label(side, textvariable=self.role_sidebar_title, font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w")
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *_: self.filter_roles())
        ttk.Entry(side, textvariable=self.search, width=28).pack(fill="x", pady=8)
        self.sex_filter = tk.StringVar(value="全部性别")
        self.grade_filter = tk.StringVar(value="全部境界")
        sex = ttk.Combobox(side, textvariable=self.sex_filter, values=["全部性别", "男", "女"], state="readonly", width=24)
        sex.pack(fill="x", pady=(0, 6))
        sex.bind("<<ComboboxSelected>>", lambda _: self.filter_roles())
        self.grade_box = ttk.Combobox(side, textvariable=self.grade_filter, values=["全部境界"], state="readonly", width=24)
        self.grade_box.pack(fill="x", pady=(0, 6))
        self.grade_box.bind("<<ComboboxSelected>>", lambda _: self.filter_roles())
        self.role_count = tk.StringVar(value="暂无角色")
        ttk.Label(side, textvariable=self.role_count).pack(anchor="w", pady=(0, 6))
        self.role_list = tk.Listbox(side, selectmode="extended", exportselection=False, font=("Microsoft YaHei UI", 10), borderwidth=0, activestyle="dotbox")
        self.role_list.pack(fill="both", expand=True)
        self.role_list.bind("<<ListboxSelect>>", lambda _: self.guard(self.select_role))
        ttk.Label(side, text="Ctrl / Shift 多选角色", foreground="#62748c").pack(anchor="w", pady=5)
        ttk.Button(side, text="所选角色补满状态", command=lambda: self.guard(self.refill_selected)).pack(fill="x")
        ttk.Button(side, text="从其他存档导入角色", command=lambda: self.guard(self.choose_role_import_source)).pack(
            fill="x", pady=(6, 0))

    def choose_role_import_source(self):
        if not self.doc:
            raise DataError("请先打开作为导入目标的存档")
        slots = [slot for slot in discover_saves() if slot.path.resolve() != self.doc.source]
        window = tk.Toplevel(self)
        window.title("选择角色来源存档")
        window.geometry("760x480")
        window.transient(self)
        ttk.Label(window, text="选择另一存档作为角色来源；目标存档只会在内存中暂存修改。",
                  padding=14).pack(anchor="w")
        tree = ttk.Treeview(window, columns=("modified", "size", "path"), show="headings", selectmode="browse")
        for column, title, width in (("modified", "修改时间", 145), ("size", "角色缓存", 90),
                                     ("path", "存档槽位", 450)):
            tree.heading(column, text=title)
            tree.column(column, width=width, stretch=column == "path")
        for index, slot in enumerate(slots):
            tree.insert("", "end", iid=str(index), values=(
                datetime.fromtimestamp(slot.modified).strftime("%Y-%m-%d %H:%M"),
                f"{slot.size / 1024 / 1024:.1f} MB", slot.label))
        tree.pack(fill="both", expand=True, padx=14)
        actions = ttk.Frame(window, padding=14)
        actions.pack(fill="x")

        def open_selected():
            selection = tree.selection()
            if not selection:
                raise DataError("请选择一个来源存档")
            path = slots[int(selection[0])].path
            window.destroy()
            self.open_role_import_panel(path)

        def browse_file():
            path = filedialog.askopenfilename(parent=window, title="选择来源角色缓存",
                                              initialdir=str(self.doc.source.parent),
                                              filetypes=[("角色缓存或 JSON", "*.cache *.json"), ("所有文件", "*.*")])
            if path:
                window.destroy()
                self.open_role_import_panel(path)

        ttk.Button(actions, text="浏览其他文件", command=lambda: self.guard(browse_file)).pack(side="left")
        ttk.Button(actions, text="取消", command=window.destroy).pack(side="right")
        ttk.Button(actions, text="查看所选存档角色", command=lambda: self.guard(open_selected)).pack(side="right", padx=8)
        tree.bind("<Double-1>", lambda _: self.guard(open_selected))

    def open_role_import_panel(self, source_path):
        source = Document(source_path)
        if source.source == self.doc.source:
            raise DataError("来源存档不能与当前存档相同")
        source_roles = list(find_roles(source.data))
        if not source_roles:
            raise DataError("来源文件中没有识别到角色")
        rows = []
        for path, name in source_roles:
            info = role_info(get_at(source.data, path), self.catalog)
            rows.append({"path": path, "name": name or "未命名角色", "sex": info["sex"],
                         "grade": info["grade"], "school": info["school"], "id": str(path[-1])})

        dialog = tk.Toplevel(self)
        dialog.title(f"导入角色 · {source.source.parent.name}")
        dialog.geometry("940x650")
        dialog.transient(self)
        ttk.Label(dialog, text="搜索并多选需要导入的角色", font=("Microsoft YaHei UI", 13, "bold"),
                  padding=(14, 14, 14, 2)).pack(anchor="w")
        ttk.Label(dialog, text="导入时生成新编号并清除原宗门和外部关系；不会覆盖目标存档角色。",
                  foreground="#62748c", padding=(14, 0, 14, 10)).pack(anchor="w")
        filters = ttk.Frame(dialog, padding=(14, 0, 14, 8))
        filters.pack(fill="x")
        query = tk.StringVar()
        sex = tk.StringVar(value="全部性别")
        grade = tk.StringVar(value="全部境界")
        ttk.Label(filters, text="姓名/编号").pack(side="left")
        ttk.Entry(filters, textvariable=query, width=25).pack(side="left", padx=(6, 12))
        ttk.Combobox(filters, textvariable=sex, values=["全部性别", "男", "女", "未知"],
                     state="readonly", width=11).pack(side="left", padx=5)
        grades = sorted({row["grade"] for row in rows})
        ttk.Combobox(filters, textvariable=grade, values=["全部境界"] + grades,
                     state="readonly", width=16).pack(side="left", padx=5)
        count = tk.StringVar()
        ttk.Label(filters, textvariable=count, foreground="#62748c").pack(side="right")

        frame = ttk.Frame(dialog, padding=(14, 0, 14, 0))
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=("name", "sex", "grade", "school", "id"),
                            show="headings", selectmode="extended")
        for column, title, width in (("name", "姓名", 190), ("sex", "性别", 70),
                                     ("grade", "境界", 150), ("school", "原宗门编号", 170),
                                     ("id", "来源编号", 145)):
            tree.heading(column, text=title)
            tree.column(column, width=width, stretch=column == "name")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)
        visible = []

        def refill(*_):
            needle = query.get().strip().casefold()
            visible[:] = [row for row in rows if
                          (sex.get() == "全部性别" or row["sex"] == sex.get()) and
                          (grade.get() == "全部境界" or row["grade"] == grade.get()) and
                          (not needle or needle in row["name"].casefold() or needle in row["id"].casefold())]
            tree.delete(*tree.get_children())
            for index, row in enumerate(visible):
                tree.insert("", "end", iid=str(index),
                            values=(row["name"], row["sex"], row["grade"], row["school"] or "无", row["id"]))
            count.set(f"显示 {len(visible)} / {len(rows)} 名")

        query.trace_add("write", refill)
        for variable in (sex, grade):
            variable.trace_add("write", refill)
        refill()

        options = ttk.Frame(dialog, padding=14)
        options.pack(fill="x")
        keep_relations = tk.BooleanVar(value=True)
        ttk.Checkbutton(options, text="保留本次所选角色彼此之间的关系", variable=keep_relations).pack(side="left")

        def commit():
            selection = tree.selection()
            if not selection:
                raise DataError("请至少选择一个角色")
            chosen = [visible[int(item)]["path"] for item in selection]
            imported = import_roles(self.doc, source, chosen, keep_relations.get())
            self.roles = list(find_roles(self.doc.data))
            grades_now = sorted({role_info(get_at(self.doc.data, path), self.catalog)["grade"] for path, _ in self.roles})
            self.grade_box.configure(values=["全部境界"] + grades_now)
            self.filter_roles()
            self.refresh_tree()
            self.update_status()
            self.status.set(f"已从其他存档暂存导入 {len(imported)} 名角色；请查看修改预览后导出副本")
            dialog.destroy()

        ttk.Button(options, text="取消", command=dialog.destroy).pack(side="right")
        ttk.Button(options, text="导入所选角色", command=lambda: self.guard(commit)).pack(side="right", padx=8)

    def update_role_sidebar_visibility(self, _event=None):
        if not hasattr(self, "book") or not self.book.select():
            return
        label = self.book.tab(self.book.select(), "text")
        hidden = {"完整数据", "实时连接", "游戏与连接检测", "自愿赞助", "关于"}
        if label in hidden:
            if self.role_sidebar.winfo_manager():
                self.role_sidebar.pack_forget()
            return
        if not self.role_sidebar.winfo_manager():
            self.role_sidebar.pack(side="left", fill="y", before=self.book)
        self.sidebar_player_only = label == "壶妖"
        self.role_sidebar_title.set("主角" if self.sidebar_player_only else "角色搜索")
        self.filter_roles()
        if self.sidebar_player_only and self.doc and self.player_role_path is not None and self.role_path != self.player_role_path:
            self.role_path = self.player_role_path
            name = next((name for path, name in self.roles if path == self.player_role_path), "主角")
            self.render_role(name)
            self.refresh_inspectors()
            self.refresh_tree()

    def build_sponsor_tab(self):
        tab = ttk.Frame(self.book, padding=28)
        self.book.add(tab, text="自愿赞助")

        hero = ttk.Frame(tab, padding=(26, 22))
        hero.pack(fill="x", pady=(0, 18))
        ttk.Label(hero, text="感谢支持玄枢 · 八荒编修台",
                  font=("Microsoft YaHei UI", 20, "bold")).pack(anchor="w")
        ttk.Label(
            hero,
            text="赞助完全自愿，不赞助也能使用全部功能；软件不会弹窗催促，也不会设置赞助专属功能。",
            foreground="#52677f",
            wraplength=920,
        ).pack(anchor="w", pady=(10, 0))

        content = ttk.Frame(tab)
        content.pack(fill="both", expand=True)
        note = ttk.LabelFrame(content, text="说明", padding=22)
        note.pack(side="left", fill="both", expand=True, padx=(0, 14))
        ttk.Label(
            note,
            justify="left",
            wraplength=600,
            text=(
                "如果这个工具节省了你的时间，可以在力所能及的范围内自愿支持维护。\n\n"
                "赞助不会影响版本更新、问题反馈或任何编辑能力。请先确认自己的支付信息，"
                "不要在备注中填写存档、账号、密码等隐私内容。\n\n"
                "右侧赞赏码仅用于无偿支持，不对应任何商品、功能、更新优先级或服务。"
            ),
        ).pack(anchor="nw")

        qr_card = ttk.LabelFrame(content, text="赞助方式", padding=22)
        qr_card.pack(side="right", fill="y")
        ttk.Label(qr_card, text="自愿赞赏码", font=("Microsoft YaHei UI", 14, "bold")).pack(pady=(0, 10))
        try:
            sponsor = Image.open(resource_path("assets", "sponsor.jpg")).convert("RGB")
            sponsor.thumbnail((430, 430), Image.Resampling.LANCZOS)
            self.sponsor_photo = ImageTk.PhotoImage(sponsor)
            ttk.Label(qr_card, image=self.sponsor_photo).pack(fill="both", expand=True)
        except Exception:
            ttk.Label(
                qr_card,
                text="赞赏码资源未找到",
                justify="center",
                foreground="#6b7c90",
                padding=(100, 120),
            ).pack(fill="both", expand=True)
        ttk.Label(qr_card, text="请量力而行 · 理性支持", foreground="#8a5a44").pack(pady=(10, 20))

    def build_role_tab(self):
        tab = ttk.Frame(self.book, padding=12)
        self.book.add(tab, text="属性")
        right = ttk.Frame(tab)
        right.pack(fill="both", expand=True)
        self.role_title = tk.StringVar(value="选择角色后编辑属性")
        ttk.Label(right, textvariable=self.role_title, font=("Microsoft YaHei UI", 14, "bold")).pack(anchor="w", pady=(0, 12))
        self.role_details = tk.StringVar(value="")
        ttk.Label(right, textvariable=self.role_details, wraplength=700).pack(anchor="w", pady=(0, 8))
        buttons = ttk.Frame(right)
        buttons.pack(fill="x", pady=(0, 10))
        for label, action in [("复制基础属性", self.copy_attributes), ("粘贴到当前角色", self.paste_attributes), ("查看背包", self.show_inventory)]:
            ttk.Button(buttons, text=label, command=lambda f=action: self.guard(f)).pack(side="left", padx=(0, 6))
        canvas = tk.Canvas(right, background="#eef2f6", highlightthickness=0)
        scroll = ttk.Scrollbar(right, orient="vertical", command=canvas.yview)
        scroll.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True)
        canvas.configure(yscrollcommand=scroll.set)
        self.form_frame = ttk.Frame(canvas)
        canvas.create_window(0, 0, window=self.form_frame, anchor="nw")
        self.form_frame.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        ttk.Button(right, text="引用修改", command=lambda: self.guard(self.apply_role)).pack(anchor="e", pady=8)

    def build_fate_tab(self):
        tab = ttk.Frame(self.book, padding=12)
        self.book.add(tab, text="气运")
        ttk.Label(tab, text="先天气运 / 后天气运 / 逆天改命 / 道心", font=("Microsoft YaHei UI", 14, "bold")).pack(anchor="w")
        ttk.Label(tab, text="四类数据独立显示；支持按 ID 或名称搜索，并可暂存添加、替换、删除。未知新版 ID 仍可直接输入。",
                  foreground="#62748c").pack(anchor="w", pady=(4, 10))
        grid = ttk.Frame(tab)
        grid.pack(fill="both", expand=True)
        self.fate_widgets = {}
        for position, section in enumerate(FATE_SECTION_LABELS):
            frame = ttk.LabelFrame(grid, text=section, padding=8)
            frame.grid(row=position // 2, column=position % 2, sticky="nsew", padx=5, pady=5)
            grid.rowconfigure(position // 2, weight=1)
            grid.columnconfigure(position % 2, weight=1)
            search = tk.StringVar()
            search_entry = ttk.Entry(frame, textvariable=search)
            search_entry.pack(fill="x", pady=(0, 6))
            tree = ttk.Treeview(frame, columns=("id", "name"), show="headings", height=7, selectmode="browse")
            tree.heading("id", text="ID")
            tree.heading("name", text="名称")
            tree.column("id", width=120, stretch=False)
            tree.column("name", width=260)
            tree.pack(fill="both", expand=True)
            editor = ttk.Frame(frame, padding=(0, 7, 0, 0))
            editor.pack(fill="x")
            ttk.Button(editor, text="添加气运", command=lambda s=section: self.guard(lambda: self.add_fate_ui(s))).pack(side="left", padx=3)
            ttk.Button(editor, text="替换气运", command=lambda s=section: self.guard(lambda: self.replace_fate_ui(s))).pack(side="left", padx=3)
            ttk.Button(editor, text="删除气运", command=lambda s=section: self.guard(lambda: self.delete_fate_ui(s))).pack(side="left", padx=3)
            self.fate_widgets[section] = {"tree": tree, "search": search, "entries": []}
            search.trace_add("write", lambda *_args, s=section: self.refresh_fate_tab())

    def build_relation_tab(self):
        tab = ttk.Frame(self.book, padding=12)
        self.book.add(tab, text="关系")
        self.relation_title = tk.StringVar(value="先选择角色，再管理分类关系")
        ttk.Label(tab, textvariable=self.relation_title, font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w")
        ttk.Label(tab, text="每种关系独立显示；单击一行可连续多选，再点一次取消；勾选双向关系时会同步建立或删除反向关系。",
                  foreground="#62748c").pack(anchor="w", pady=(4, 10))
        relation_book = ttk.Notebook(tab)
        relation_book.pack(fill="both", expand=True)
        self.relation_widgets = {}
        for kind in RELATION_KINDS:
            page = ttk.Frame(relation_book, padding=10)
            relation_book.add(page, text=kind)
            tree = ttk.Treeview(page, columns=("name", "id", "intimacy"), show="headings", selectmode="extended")
            for column, heading, width in (("name", "角色姓名", 220), ("id", "角色编号", 180), ("intimacy", "好感", 100)):
                tree.heading(column, text=heading)
                tree.column(column, width=width, stretch=column == "name")
            scroll = ttk.Scrollbar(page, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=scroll.set)
            scroll.pack(side="right", fill="y")
            tree.pack(fill="both", expand=True)
            tree.bind("<Button-1>", lambda event, current=tree: self.toggle_tree_click(current, event))
            controls = ttk.LabelFrame(page, text=f"{kind}关系操作", padding=8)
            controls.pack(fill="x", pady=(10, 0))
            bidirectional = tk.BooleanVar(value=True)
            ttk.Checkbutton(controls, text="双向关系", variable=bidirectional).pack(side="left", padx=(0, 8))
            target = tk.StringVar()
            ttk.Button(controls, text="搜索角色", command=lambda k=kind: self.guard(
                lambda: self.open_relation_role_dialog(k, False))).pack(side="left", padx=(0, 4))
            target_box = ttk.Entry(controls, textvariable=target, width=28, state="readonly")
            target_box.pack(side="left", fill="x", expand=True, padx=4)
            target_box.bind("<Button-1>", lambda _event, k=kind: self.guard(
                lambda: self.open_relation_role_dialog(k, False)))
            ttk.Label(controls, text="好感").pack(side="left", padx=(8, 2))
            intimacy = tk.StringVar(value="300")
            ttk.Entry(controls, textvariable=intimacy, width=8).pack(side="left", padx=(0, 6))
            ttk.Button(controls, text="添加一个", command=lambda k=kind: self.guard(lambda: self.add_relation_from_table(k))).pack(side="left", padx=4)
            ttk.Button(controls, text="批量添加", command=lambda k=kind: self.guard(lambda: self.open_relation_batch_dialog(k))).pack(side="left", padx=4)
            delete_text = "批量解除好友" if kind == "好友" else "批量删除所选"
            ttk.Button(controls, text=delete_text,
                       command=lambda k=kind: self.guard(lambda: self.delete_relation_from_table(k))).pack(side="left", padx=4)
            self.relation_widgets[kind] = {
                "tree": tree, "rows": [], "bidirectional": bidirectional,
                "target": target, "target_box": target_box, "intimacy": intimacy,
            }

    @staticmethod
    def toggle_tree_item(tree, item):
        """Checkbox-like multi-selection: ordinary clicks accumulate without Ctrl."""
        if not item:
            return "break"
        if item in tree.selection():
            tree.selection_remove(item)
        else:
            tree.selection_add(item)
        tree.focus(item)
        return "break"

    def toggle_tree_click(self, tree, event):
        return self.toggle_tree_item(tree, tree.identify_row(event.y))

    def build_potmon_tab(self):
        self.potmon_tab = ttk.Frame(self.book, padding=12)
        self.book.add(self.potmon_tab, text="壶妖")
        self.potmon_title = tk.StringVar(value="读取完整存档槽后显示壶妖")
        ttk.Label(self.potmon_tab, textvariable=self.potmon_title,
                  font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w")
        ttk.Label(self.potmon_tab, text="点击列表中的契约框可签订或取消契约；属性只计算未化形壶妖，已化形对象请到 NPC 列表修改。",
                  foreground="#62748c").pack(anchor="w", pady=(4, 10))
        panes = ttk.Panedwindow(self.potmon_tab, orient="horizontal")
        panes.pack(fill="both", expand=True)
        left = ttk.Frame(panes)
        right = ttk.LabelFrame(panes, text="属性", padding=10)
        panes.add(left, weight=3)
        panes.add(right, weight=2)

        list_frame = ttk.LabelFrame(left, text="壶妖列表（右键操作）", padding=8)
        list_frame.pack(fill="both", expand=True)
        columns = ("contract", "name", "race", "health", "state")
        self.potmon_tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="browse", height=10)
        for column, title, width in (("contract", "契约", 55), ("name", "名称", 150), ("race", "种族", 100),
                                     ("health", "健康", 70), ("state", "化形状态", 85)):
            self.potmon_tree.heading(column, text=title)
            self.potmon_tree.column(column, width=width, stretch=column == "name", anchor="center" if column != "name" else "w")
        pot_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.potmon_tree.yview)
        self.potmon_tree.configure(yscrollcommand=pot_scroll.set)
        pot_scroll.pack(side="right", fill="y")
        self.potmon_tree.pack(fill="both", expand=True)
        self.potmon_tree.bind("<<TreeviewSelect>>", lambda _event: self.guard(self.select_potmon))
        self.potmon_tree.bind("<Button-1>", self.potmon_tree_click)
        self.potmon_tree.bind("<Button-3>", self.potmon_context_menu)
        self.potmon_rows = []
        self.selected_potmon = None

        skills = ttk.LabelFrame(left, text="技能栏", padding=8)
        skills.pack(fill="both", expand=True, pady=(10, 0))
        self.potmon_skill_tree = ttk.Treeview(skills, columns=("type", "name", "id"), show="headings",
                                              selectmode="extended", height=7)
        for column, title, width in (("type", "类型", 90), ("name", "技能名称", 220), ("id", "编号", 100)):
            self.potmon_skill_tree.heading(column, text=title)
            self.potmon_skill_tree.column(column, width=width, stretch=column == "name")
        self.potmon_skill_tree.pack(fill="both", expand=True)
        skill_buttons = ttk.Frame(skills, padding=(0, 7, 0, 0))
        skill_buttons.pack(fill="x")
        ttk.Button(skill_buttons, text="添加技能", command=lambda: self.guard(self.open_potmon_skill_dialog)).pack(side="left")
        ttk.Button(skill_buttons, text="删除所选", command=lambda: self.guard(self.delete_selected_potmon_skills)).pack(side="left", padx=7)
        self.potmon_skill_rows = []

        self.potmon_contract = tk.BooleanVar()
        self.potmon_name = tk.StringVar()
        self.potmon_race = tk.StringVar()
        self.potmon_sex = tk.StringVar()
        self.potmon_health = tk.StringVar()
        self.potmon_transform = tk.StringVar()
        basics = ttk.Frame(right)
        basics.pack(fill="x")
        ttk.Checkbutton(basics, text="契约", variable=self.potmon_contract,
                        command=lambda: self.guard(self.toggle_potmon_contract)).grid(row=0, column=0, sticky="w", padx=4, pady=4)
        basic_fields = (("名称", self.potmon_name, "entry"), ("种族", self.potmon_race, "readonly"),
                        ("性别", self.potmon_sex, "sex"), ("健康", self.potmon_health, "health"),
                        ("化形状态", self.potmon_transform, "readonly"))
        self.potmon_basic_widgets = []
        for index, (label, variable, kind) in enumerate(basic_fields, start=1):
            row, column = divmod(index, 2)
            cell = ttk.Frame(basics)
            cell.grid(row=row, column=column, sticky="ew", padx=4, pady=4)
            ttk.Label(cell, text=label).pack(anchor="w")
            if kind == "sex":
                widget = ttk.Combobox(cell, textvariable=variable, values=("男", "女"), state="readonly")
            elif kind == "health":
                widget = ttk.Combobox(cell, textvariable=variable, values=("正常", "受伤", "濒危"), state="readonly")
            else:
                widget = ttk.Entry(cell, textvariable=variable, state="readonly" if kind == "readonly" else "normal")
            widget.pack(fill="x")
            if kind != "readonly":
                self.potmon_basic_widgets.append(widget)
            basics.columnconfigure(column, weight=1)

        property_frame = ttk.LabelFrame(right, text="未化形属性范围", padding=8)
        property_frame.pack(fill="x", pady=(10, 0))
        self.potmon_property_vars = {}
        self.potmon_property_entries = {}
        for index, label in enumerate(POTMON_PROPERTY_FIELDS):
            row, column = divmod(index, 3)
            cell = ttk.Frame(property_frame)
            cell.grid(row=row, column=column, sticky="ew", padx=4, pady=4)
            ttk.Label(cell, text=label).pack(anchor="w")
            variable = tk.StringVar()
            entry = ttk.Entry(cell, textvariable=variable, width=10)
            entry.pack(fill="x")
            self.potmon_property_vars[label] = variable
            self.potmon_property_entries[label] = entry
            self.attach_tooltip(entry, lambda name=label: self.potmon_range_tip(name))
            property_frame.columnconfigure(column, weight=1)
        ttk.Label(right, text="1、这里输入的是随机范围值，游戏会自动计算。\n2、鼠标悬停文本框可查看该种族的正确输入范围。",
                  foreground="#315c8c", justify="left").pack(anchor="w", pady=(10, 6))
        potmon_actions = ttk.Frame(right)
        potmon_actions.pack(fill="x")
        self.potmon_force_button = ttk.Button(potmon_actions, text="强制化形（游戏内）",
                                               command=lambda: self.guard(self.force_conver_selected_potmon))
        self.potmon_force_button.pack(side="left")
        self.potmon_save_button = ttk.Button(potmon_actions, text="保存属性", command=lambda: self.guard(self.save_potmon))
        self.potmon_save_button.pack(side="right")

    def attach_tooltip(self, widget, text_provider):
        state = {"window": None}

        def show(_event=None):
            text = str(text_provider())
            if not text:
                return
            window = tk.Toplevel(widget)
            window.wm_overrideredirect(True)
            window.wm_geometry(f"+{widget.winfo_rootx() + 12}+{widget.winfo_rooty() + widget.winfo_height() + 4}")
            ttk.Label(window, text=text, padding=6).pack()
            state["window"] = window

        def hide(_event=None):
            if state["window"] is not None:
                state["window"].destroy()
                state["window"] = None

        widget.bind("<Enter>", show)
        widget.bind("<Leave>", hide)

    def build_skill_tab(self):
        tab = ttk.Frame(self.book, padding=12)
        self.book.add(tab, text="功法")
        self.skill_tree_title = tk.StringVar(value="先选择角色，再选择已学习功法")
        ttk.Label(tab, textvariable=self.skill_tree_title, font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w")
        ttk.Label(tab, text="选择完成后统一点击“引用修改 / 统一保存”；编辑过程不会立即写入存档副本。",
                  foreground="#62748c").pack(anchor="w", pady=(4, 10))
        panes = ttk.Panedwindow(tab, orient="horizontal")
        panes.pack(fill="both", expand=True)
        left = ttk.LabelFrame(panes, text="已学习功法", padding=8)
        right = ttk.Frame(panes, padding=(10, 0, 0, 0))
        panes.add(left, weight=3)
        panes.add(right, weight=4)
        columns = ("equipped", "name", "type", "grade", "progress")
        self.skill_tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse")
        for column, title, width in (("equipped", "装备", 70), ("name", "名称", 180), ("type", "类型", 90),
                                     ("grade", "境界", 100), ("progress", "进度", 80)):
            self.skill_tree.heading(column, text=title)
            self.skill_tree.column(column, width=width, stretch=column == "name")
        skill_scroll = ttk.Scrollbar(left, orient="vertical", command=self.skill_tree.yview)
        self.skill_tree.configure(yscrollcommand=skill_scroll.set)
        skill_scroll.pack(side="right", fill="y")
        self.skill_tree.pack(fill="both", expand=True)
        self.skill_tree.bind("<<TreeviewSelect>>", lambda _: self.guard(self.select_skill_record))
        self.skill_rows_by_item = {}

        info = ttk.LabelFrame(right, text="功法信息修改栏", padding=8)
        info.pack(fill="x")
        self.skill_type_value = tk.StringVar()
        self.skill_name_value = tk.StringVar()
        self.skill_grade_value = tk.StringVar()
        self.skill_inheritance_value = tk.StringVar(value="否 · 0")
        self.skill_progress_value = tk.StringVar(value="0")
        info_fields = [
            ("功法类型", self.skill_type_value), ("功法名称", self.skill_name_value),
            ("所用境界", self.skill_grade_value), ("传承", self.skill_inheritance_value),
            ("进度", self.skill_progress_value),
        ]
        self.skill_info_boxes = {}
        for index, (label, variable) in enumerate(info_fields):
            row, column = divmod(index, 3)
            cell = ttk.Frame(info)
            cell.grid(row=row, column=column, sticky="ew", padx=4, pady=4)
            ttk.Label(cell, text=label).pack(anchor="w")
            if label == "进度":
                box = ttk.Entry(cell, textvariable=variable, width=20)
            else:
                box = ttk.Combobox(cell, textvariable=variable, width=22)
            box.pack(fill="x")
            self.skill_info_boxes[label] = box
            info.columnconfigure(column, weight=1)
        self.skill_info_boxes["功法类型"].configure(values=[
            f"{data.get('name', key)} · {key}" for key, data in self.catalog.skill_types.items()])
        self.skill_info_boxes["所用境界"].configure(values=[
            f"{data.get('name', key)} · {key}" for key, data in self.catalog.skill_grades.items() if key != "0"])
        self.skill_info_boxes["传承"].configure(values=["否 · 0", "是 · 1"], state="readonly")
        self.skill_info_boxes["功法类型"].bind("<<ComboboxSelected>>", lambda _: self.refresh_skill_name_choices())
        self.skill_info_boxes["功法名称"].bind("<<ComboboxSelected>>", lambda _: self.refresh_skill_effect_choices())
        self.skill_info_boxes["所用境界"].bind("<<ComboboxSelected>>", lambda _: self.refresh_skill_effect_choices())

        effects = ttk.LabelFrame(right, text="词条修改栏 · 词条 1–11 与对应参悟程度", padding=8)
        effects.pack(fill="both", expand=True, pady=(8, 0))
        self.skill_effect_vars = []
        self.skill_effect_boxes = []
        for index in range(11):
            ttk.Label(effects, text=f"词条 {index + 1}", width=8).grid(row=index, column=0, padx=3, pady=2, sticky="w")
            effect_value = tk.StringVar(value="空 · 0")
            effect_box = ttk.Combobox(effects, textvariable=effect_value, width=46)
            effect_box.grid(row=index, column=1, padx=3, pady=2, sticky="ew")
            ttk.Label(effects, text="参悟").grid(row=index, column=2, padx=(8, 3), pady=2)
            exp_value = tk.StringVar(value="0")
            ttk.Entry(effects, textvariable=exp_value, width=10).grid(row=index, column=3, padx=3, pady=2)
            self.skill_effect_vars.append((effect_value, exp_value))
            self.skill_effect_boxes.append(effect_box)
        effects.columnconfigure(1, weight=1)

        add = ttk.LabelFrame(right, text="词条添加栏", padding=8)
        add.pack(fill="x", pady=(8, 0))
        self.skill_effect_target = tk.StringVar(value="词条 1")
        ttk.Combobox(add, textvariable=self.skill_effect_target,
                     values=[f"词条 {index}" for index in range(1, 12)], state="readonly", width=10).pack(side="left")
        self.skill_effect_candidate = tk.StringVar()
        self.skill_effect_candidate_box = ttk.Combobox(add, textvariable=self.skill_effect_candidate, width=45)
        self.skill_effect_candidate_box.pack(side="left", fill="x", expand=True, padx=7)
        ttk.Button(add, text="加入/替换到所选栏", command=lambda: self.guard(self.place_skill_effect)).pack(side="left", padx=3)
        ttk.Button(add, text="清空所选栏", command=lambda: self.guard(self.clear_skill_effect_slot)).pack(side="left", padx=3)

        actions = ttk.Frame(right, padding=(0, 8, 0, 0))
        actions.pack(fill="x")
        ttk.Button(actions, text="完美参悟", command=self.skill_form_perfect).pack(side="left", padx=(0, 5))
        ttk.Button(actions, text="词条全部生效", command=self.skill_form_enable).pack(side="left", padx=5)
        ttk.Button(actions, text="引用修改 / 统一保存", command=lambda: self.guard(self.save_skill_form)).pack(side="right")

    def build_inspector_tab(self, label, attribute, columns, note):
        tab = ttk.Frame(self.book, padding=12)
        self.book.add(tab, text=label)
        title = tk.StringVar(value=f"先在属性页选择角色，再查看{label}")
        setattr(self, attribute + "_title", title)
        ttk.Label(tab, textvariable=title, font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w")
        ttk.Label(tab, text=note, foreground="#62748c", wraplength=1050).pack(anchor="w", pady=(4, 10))
        tree = ttk.Treeview(tab, columns=tuple(f"c{i}" for i in range(1, len(columns))), show="tree headings")
        tree.heading("#0", text=columns[0])
        tree.column("#0", width=190)
        for index, heading in enumerate(columns[1:], 1):
            name = f"c{index}"
            tree.heading(name, text=heading)
            tree.column(name, width=210)
        scroll = ttk.Scrollbar(tab, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)
        setattr(self, attribute, tree)
        paths = {}
        self.inspector_paths[attribute] = paths
        editor = ttk.Frame(tab, padding=(0, 10, 0, 0))
        editor.pack(fill="x")
        value = tk.StringVar()
        setattr(self, attribute + "_value", value)
        ttk.Label(editor, text="选中行的新值").pack(side="left", padx=(0, 8))
        ttk.Entry(editor, textvariable=value, width=28).pack(side="left")
        ttk.Button(editor, text="暂存此项修改",
                   command=lambda a=attribute: self.guard(lambda: self.apply_inspector_value(a))).pack(side="left", padx=10)
        tree.bind("<<TreeviewSelect>>", lambda _, a=attribute: self.select_inspector_value(a))
        if attribute == "relation_tree":
            relation = ttk.LabelFrame(tab, text="双向添加关系 · 写入当前内存副本", padding=10)
            relation.pack(fill="x", pady=(10, 0))
            self.relation_kind = tk.StringVar(value="好友")
            kinds = ["好友", "父母", "子女", "私生子女", "兄弟姐妹", "义父母", "义子女", "义兄弟姐妹", "夫妻", "道侣", "师父", "徒弟"]
            ttk.Combobox(relation, textvariable=self.relation_kind, values=kinds, state="readonly", width=14).pack(side="left")
            self.relation_target = tk.StringVar()
            self.relation_target_box = ttk.Combobox(relation, textvariable=self.relation_target, width=34)
            self.relation_target_box.pack(side="left", padx=8)
            self.relation_intimacy = tk.StringVar(value="300")
            ttk.Label(relation, text="好感").pack(side="left")
            ttk.Entry(relation, textvariable=self.relation_intimacy, width=8).pack(side="left", padx=6)
            ttk.Button(relation, text="添加", command=lambda: self.guard(self.add_relation_single)).pack(side="left", padx=5)
            ttk.Button(relation, text="批量添加属性页多选角色", command=lambda: self.guard(self.add_relation_batch)).pack(side="left", padx=5)
        elif attribute == "skill_tree":
            actions = ttk.LabelFrame(tab, text="功法词条 · 只修改已有词条", padding=10)
            actions.pack(fill="x", pady=(10, 0))
            ttk.Button(actions, text="选中功法完美参悟", command=lambda: self.guard(self.perfect_selected_skill)).pack(side="left", padx=(0, 6))
            ttk.Button(actions, text="选中功法词条生效", command=lambda: self.guard(self.enable_selected_skill)).pack(side="left", padx=6)
            ttk.Button(actions, text="全部功法完美参悟并生效", command=lambda: self.guard(self.perfect_all_skills)).pack(side="left", padx=6)

    def build_appearance_tab(self):
        self.appearance_tab = ttk.Frame(self.book, padding=12)
        self.book.add(self.appearance_tab, text="形象")
        self.appearance_title = tk.StringVar(value="先在左侧选择角色，再编辑人物形象")
        ttk.Label(self.appearance_tab, textvariable=self.appearance_title,
                  font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w", pady=(0, 8))

        body = ttk.Frame(self.appearance_tab)
        body.pack(fill="both", expand=True)
        normal = ttk.LabelFrame(body, text="人物形象", padding=12)
        normal.pack(side="left", fill="both", expand=True, padx=(0, 8))
        battle = ttk.LabelFrame(body, text="战斗形象（不要使用冥妖 ID）", padding=12)
        battle.pack(side="right", fill="y")

        self.appearance_vars = {}
        self.appearance_boxes = {}
        normal_layout = {
            "帽子": (0, 1),
            "前发": (1, 0), "后发": (1, 2),
            "眼睛": (2, 0), "眉毛": (2, 2),
            "嘴巴": (3, 0), "性别": (3, 1), "鼻子": (3, 2),
            "脸型": (4, 0), "后背": (4, 2),
            "衣服": (5, 0), "全脸": (5, 1),
            "眉心": (6, 1), "左脸": (7, 1), "右脸": (8, 1),
        }
        for column in range(3):
            normal.columnconfigure(column, weight=1, uniform="appearance")
        for label, (row, column) in normal_layout.items():
            field = ttk.Frame(normal)
            field.grid(row=row, column=column, padx=8, pady=8, sticky="ew")
            ttk.Label(field, text=f"{label}：", width=6, anchor="e").pack(side="left")
            variable = tk.StringVar()
            state = "readonly" if label == "性别" else "normal"
            box = ttk.Combobox(field, textvariable=variable, state=state, width=13)
            box.pack(side="left", fill="x", expand=True)
            self.appearance_vars[label] = variable
            self.appearance_boxes[label] = box
        self.appearance_boxes["性别"].configure(values=APPEARANCE_SEX_OPTIONS)
        self.appearance_boxes["性别"].bind(
            "<<ComboboxSelected>>", lambda _: self.refresh_appearance_choices("normal"))

        self.battle_appearance_vars = {}
        self.battle_appearance_boxes = {}
        for row, label in enumerate(BATTLE_APPEARANCE_PATHS):
            ttk.Label(battle, text=f"{label}：", foreground="#d62424", width=7, anchor="e").grid(
                row=row, column=0, padx=(0, 3), pady=5, sticky="e")
            variable = tk.StringVar()
            state = "readonly" if label == "性别" else "normal"
            box = ttk.Combobox(battle, textvariable=variable, state=state, width=14)
            box.grid(row=row, column=1, pady=5, sticky="ew")
            self.battle_appearance_vars[label] = variable
            self.battle_appearance_boxes[label] = box
        self.battle_appearance_boxes["性别"].configure(values=APPEARANCE_SEX_OPTIONS)
        self.battle_appearance_boxes["性别"].bind(
            "<<ComboboxSelected>>", lambda _: self.refresh_appearance_choices("battle"))

        warning = ttk.Frame(battle, padding=(0, 12, 0, 8))
        warning.grid(row=len(BATTLE_APPEARANCE_PATHS), column=0, columnspan=2, sticky="ew")
        tk.Label(warning, text="红色栏目为战斗形象。", fg="#d62424", bg="#eef2f6",
                 anchor="w").pack(fill="x")
        tk.Label(warning, text="可输入游戏或 Mod 外观 ID；请勿填入冥妖 ID。\n"
                               "战斗外观可能由副本或宗门界面调用，\n修改前建议先导出外貌模板。",
                 fg="#245bd6", bg="#eef2f6", justify="left", anchor="w").pack(fill="x", pady=(3, 0))

        actions = ttk.Frame(battle)
        actions.grid(row=len(BATTLE_APPEARANCE_PATHS) + 1, column=0, columnspan=2,
                     sticky="sew", pady=(16, 0))
        ttk.Button(actions, text="导入", command=lambda: self.guard(self.import_appearance_template)).pack(fill="x", pady=3)
        ttk.Button(actions, text="导出", command=lambda: self.guard(self.export_appearance_template)).pack(fill="x", pady=3)
        ttk.Button(actions, text="应用修改", command=lambda: self.guard(self.apply_appearance)).pack(fill="x", pady=3)

    @staticmethod
    def appearance_sex_value(variable):
        text = variable.get().strip()
        try:
            return int(text.rsplit(" · ", 1)[-1])
        except ValueError:
            return 1

    @staticmethod
    def appearance_sex_text(value):
        return {0: "通用/无性 · 0", 1: "男 · 1", 2: "女 · 2"}.get(value, str(value))

    def refresh_appearance_choices(self, group=None):
        if not hasattr(self, "game_path"):
            return
        catalog = appearance_catalog(self.game_path.get())
        targets = []
        if group in (None, "normal"):
            targets.append((self.appearance_vars, self.appearance_boxes))
        if group in (None, "battle"):
            targets.append((self.battle_appearance_vars, self.battle_appearance_boxes))
        for variables, boxes in targets:
            sex = self.appearance_sex_value(variables["性别"])
            for label, box in boxes.items():
                if label == "性别":
                    continue
                item_type = APPEARANCE_TYPES[label]
                ids = list(catalog.get((item_type, sex), []))
                if sex in (1, 2):
                    ids.extend(catalog.get((item_type, 0), []))
                values = [str(value) for value in sorted(set(ids))]
                box.configure(values=values)

    def refresh_appearance_tab(self):
        if not hasattr(self, "appearance_vars"):
            return
        variables = list(self.appearance_vars.values()) + list(self.battle_appearance_vars.values())
        if not self.doc or self.role_path is None:
            self.appearance_title.set("先在左侧选择角色，再编辑人物形象")
            for variable in variables:
                variable.set("")
            return
        data = appearance_data(self.doc, self.role_path)
        name = next((n for p, n in self.roles if p == self.role_path), "未命名角色")
        self.appearance_title.set(f"{name} · 人物形象")
        for label, value in data["normal"].items():
            self.appearance_vars[label].set(self.appearance_sex_text(value) if label == "性别" else str(value))
        for label, value in data["battle"].items():
            self.battle_appearance_vars[label].set(self.appearance_sex_text(value) if label == "性别" else str(value))
        self.refresh_appearance_choices()

    def appearance_form_data(self):
        normal = {label: variable.get().strip() for label, variable in self.appearance_vars.items()}
        battle = {label: variable.get().strip() for label, variable in self.battle_appearance_vars.items()}
        return {"version": 1, "normal": normal, "battle": battle}

    def apply_appearance(self):
        if not self.doc or self.role_path is None:
            raise DataError("请先选择角色")
        data = self.appearance_form_data()
        changed = update_appearance(self.doc, self.role_path, data["normal"], data["battle"])
        self.refresh_appearance_tab()
        self.refresh_tree()
        self.status.set(f"已暂存 {changed} 项人物与战斗形象；导出副本后才会写入文件")

    def import_appearance_template(self):
        path = filedialog.askopenfilename(parent=self, title="导入外貌模板",
                                          filetypes=[("外貌模板", "*.json"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise DataError(f"外貌模板读取失败：{exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("normal"), dict) or not isinstance(data.get("battle"), dict):
            raise DataError("外貌模板必须包含 normal 和 battle 两组数据")
        missing = ([f"常态/{label}" for label in NORMAL_APPEARANCE_PATHS if label not in data["normal"]] +
                   [f"战斗/{label}" for label in BATTLE_APPEARANCE_PATHS if label not in data["battle"]])
        if missing:
            raise DataError("外貌模板缺少：" + "、".join(missing))
        for label in NORMAL_APPEARANCE_PATHS:
            value = data["normal"][label]
            sex = int(str(value).rsplit(" · ", 1)[-1]) if label == "性别" else None
            self.appearance_vars[label].set(self.appearance_sex_text(sex) if label == "性别" else str(value))
        for label in BATTLE_APPEARANCE_PATHS:
            value = data["battle"][label]
            sex = int(str(value).rsplit(" · ", 1)[-1]) if label == "性别" else None
            self.battle_appearance_vars[label].set(self.appearance_sex_text(sex) if label == "性别" else str(value))
        self.refresh_appearance_choices()
        self.status.set("外貌模板已载入表单；点击“应用修改”后才会暂存到角色")

    def export_appearance_template(self):
        if not self.doc or self.role_path is None:
            raise DataError("请先选择角色")
        data = self.appearance_form_data()
        for group_name in ("normal", "battle"):
            for label, value in data[group_name].items():
                try:
                    data[group_name][label] = int(str(value).rsplit(" · ", 1)[-1].strip())
                except ValueError as exc:
                    raise DataError(f"{label}必须是整数 ID") from exc
        path = filedialog.asksaveasfilename(parent=self, title="导出外貌模板", defaultextension=".json",
                                            filetypes=[("外貌模板", "*.json")], initialfile="人物外貌模板.json")
        if not path:
            return
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.status.set(f"外貌模板已导出：{path}")

    def build_school_tab(self):
        self.school_tab = ttk.Frame(self.book, padding=10)
        self.book.add(self.school_tab, text="宗门")
        heading = ttk.Frame(self.school_tab)
        heading.pack(fill="x", pady=(0, 7))
        self.school_title = tk.StringVar(value="先选择宗门成员，再编辑其所在宗门")
        ttk.Label(heading, textvariable=self.school_title,
                  font=("Microsoft YaHei UI", 13, "bold")).pack(side="left")
        ttk.Button(heading, text="应用宗门资料", command=lambda: self.guard(self.save_school_properties)).pack(side="right")
        ttk.Label(heading, text="资料分组保存 · 成员工具独立执行", foreground="#62748c").pack(side="right", padx=12)

        self.school_pages = ttk.Notebook(self.school_tab)
        self.school_pages.pack(fill="both", expand=True)
        overview_page = ttk.Frame(self.school_pages, padding=10)
        members_page = ttk.Frame(self.school_pages, padding=10)
        development_page = ttk.Frame(self.school_pages, padding=10)
        self.school_pages.add(overview_page, text="基础资料")
        self.school_pages.add(members_page, text="成员名册")
        self.school_pages.add(development_page, text="发展管理")

        ttk.Label(overview_page, text="宗门核心资料", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w")
        ttk.Label(overview_page, text="按用途分组填写；点击右上角“应用宗门资料”统一暂存。",
                  foreground="#62748c").pack(anchor="w", pady=(2, 10))
        dashboard = ttk.Frame(overview_page)
        dashboard.pack(fill="both", expand=True)
        resources = ttk.LabelFrame(dashboard, text="资源库存", padding=8)
        governance = ttk.LabelFrame(dashboard, text="治理状态", padding=8)
        identity = ttk.LabelFrame(dashboard, text="名称与规则", padding=8)
        resources.pack(fill="x", pady=(0, 8))
        governance.pack(fill="x", pady=8)
        identity.pack(fill="x", pady=(8, 0))
        self.school_vars = {}

        def field(parent, label, row, column, span=1, combo=False):
            ttk.Label(parent, text=label).grid(row=row, column=column * 2, padx=(2, 4), pady=3, sticky="e")
            variable = tk.StringVar()
            widget = ttk.Combobox(parent, textvariable=variable, width=10) if combo else ttk.Entry(
                parent, textvariable=variable, width=10)
            widget.grid(row=row, column=column * 2 + 1, columnspan=span * 2 - 1, padx=(0, 5), pady=3, sticky="ew")
            self.school_vars[label] = variable

        for parent in (resources, governance):
            for column in (1, 3):
                parent.columnconfigure(column, weight=1)
        field(resources, "灵石", 0, 0)
        field(resources, "宗门荣誉", 0, 1)
        field(resources, "药材", 1, 0)
        field(resources, "矿材", 1, 1)
        field(resources, "灵阁", 2, 0, span=2, combo=True)
        field(governance, "繁荣", 0, 0)
        field(governance, "忠诚", 0, 1)
        field(governance, "安定", 1, 0)
        field(governance, "记名弟子", 1, 1)
        field(governance, "立场", 2, 0, span=2, combo=True)
        identity.columnconfigure(1, weight=1)
        identity.columnconfigure(3, weight=1)
        field(identity, "宗门名", 0, 0)
        field(identity, "分舵名", 0, 1)
        field(identity, "宗门特质1", 1, 0, combo=True)
        field(identity, "宗门特质2", 1, 1, combo=True)
        field(identity, "宗门门规1", 2, 0, combo=True)
        field(identity, "宗门门规2", 2, 1, combo=True)

        roster = ttk.Frame(members_page)
        roster.pack(fill="both", expand=True)
        right = ttk.Frame(development_page)
        right.pack(fill="both", expand=True)

        member_tools = ttk.Frame(roster)
        member_tools.pack(fill="x", pady=(0, 8))
        self.school_member_query = tk.StringVar()
        self.school_member_query.trace_add("write", lambda *_: self.refresh_school_member_view())
        ttk.Label(member_tools, text="搜索成员").pack(side="left")
        ttk.Entry(member_tools, textvariable=self.school_member_query, width=24).pack(side="left", padx=(6, 12))
        ttk.Label(member_tools, text="职位").pack(side="left")
        self.school_post_filter = tk.StringVar(value="全部职位")
        self.school_post_box = ttk.Combobox(member_tools, textvariable=self.school_post_filter,
                                            values=["全部职位"], state="readonly", width=13)
        self.school_post_box.pack(side="left", padx=6)
        self.school_post_box.bind("<<ComboboxSelected>>", lambda _: self.refresh_school_member_view())
        self.school_member_count = tk.StringVar(value="0 名成员")
        ttk.Label(member_tools, textvariable=self.school_member_count, foreground="#62748c").pack(side="right")

        members_frame = ttk.LabelFrame(roster, text="宗门名册 · 右键可定位角色", padding=6)
        members_frame.pack(fill="both", expand=True)
        souls_frame = ttk.LabelFrame(roster, text="失联成员 / 一丝元魂", padding=6)
        souls_frame.pack(fill="x", pady=(7, 0))

        self.school_member_rows = []
        self.visible_school_member_rows = []
        self.school_soul_rows = []
        self.school_member_sort = {"column": "post", "descending": False}
        self.school_member_tree = ttk.Treeview(members_frame, columns=("name", "post", "grade"),
                                               show="headings", selectmode="extended")
        for column, heading, width in (("name", "姓名", 125), ("post", "职位", 90), ("grade", "境界", 105)):
            self.school_member_tree.heading(column, text=heading,
                                            command=lambda key=column: self.sort_school_members(key))
            self.school_member_tree.column(column, width=width)
        member_scroll = ttk.Scrollbar(members_frame, orient="vertical", command=self.school_member_tree.yview)
        self.school_member_tree.configure(yscrollcommand=member_scroll.set)
        member_scroll.pack(side="right", fill="y")
        self.school_member_tree.pack(fill="both", expand=True)
        self.school_member_tree.bind("<Button-3>", self.show_school_member_menu)

        self.school_soul_tree = ttk.Treeview(souls_frame, columns=("name", "grade"),
                                             show="headings", selectmode="extended")
        self.school_soul_tree.heading("name", text="姓名")
        self.school_soul_tree.heading("grade", text="境界")
        self.school_soul_tree.column("name", width=130)
        self.school_soul_tree.column("grade", width=110)
        self.school_soul_tree.configure(height=4)
        self.school_soul_tree.pack(fill="x")

        skill = ttk.LabelFrame(right, text="藏经阁主修体系", padding=8)
        skill.pack(fill="x")
        ttk.Label(skill, text="勾选宗门重点培养的资质方向，各体系可自由组合。",
                  foreground="#62748c").grid(row=0, column=0, columnspan=6, sticky="w", pady=(0, 8))
        self.school_skill_vars = {}
        for index, label in enumerate(SCHOOL_MAIN_SKILLS):
            variable = tk.BooleanVar()
            ttk.Checkbutton(skill, text=label, variable=variable).grid(
                row=1 + index // 6, column=index % 6, padx=12, pady=6, sticky="w")
            self.school_skill_vars[label] = variable
        ttk.Button(skill, text="保存主修功法", command=lambda: self.guard(self.save_school_skills)).grid(
            row=3, column=0, columnspan=6, pady=(10, 0), sticky="ew")

        other = ttk.LabelFrame(right, text="成员批量工具", padding=8)
        other.pack(fill="x", pady=(12, 0))
        scope = ttk.Frame(other)
        scope.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        ttk.Label(scope, text="执行范围：").pack(side="left")
        self.school_action_scope = tk.StringVar(value="全部成员")
        ttk.Radiobutton(scope, text="全部成员", variable=self.school_action_scope,
                        value="全部成员").pack(side="left", padx=5)
        ttk.Radiobutton(scope, text="名册中选中的成员", variable=self.school_action_scope,
                        value="选中成员").pack(side="left", padx=5)
        ttk.Separator(other).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        self.school_seed = tk.StringVar(value="空 · 0")
        seed_values = [f"{value.get('name', key)} · {key}" for key, value in self.catalog.taoist_seeds.items()]
        ttk.Combobox(other, textvariable=self.school_seed, values=seed_values, state="readonly").grid(
            row=2, column=1, padx=3, pady=6, sticky="ew")
        ttk.Button(other, text="全天骄", command=lambda: self.guard(self.school_make_all_genius)).grid(
            row=2, column=2, padx=5, pady=6, sticky="ew")
        ttk.Label(other, text="天骄培养").grid(row=2, column=0, padx=3, pady=6, sticky="w")
        ttk.Label(other, text="成员薪俸").grid(row=3, column=0, padx=3, pady=6, sticky="w")
        self.school_salary = tk.StringVar(value="1000000")
        ttk.Entry(other, textvariable=self.school_salary).grid(row=3, column=1, padx=3, pady=6, sticky="ew")
        ttk.Button(other, text="发工资", command=lambda: self.guard(self.school_pay_salary)).grid(
            row=3, column=2, padx=5, pady=6, sticky="ew")
        ttk.Label(other, text="关系维护").grid(row=4, column=0, padx=3, pady=6, sticky="w")
        self.school_intimacy = tk.StringVar(value="300")
        ttk.Entry(other, textvariable=self.school_intimacy).grid(row=4, column=1, padx=3, pady=6, sticky="ew")
        ttk.Button(other, text="全好友", command=lambda: self.guard(self.school_make_all_friends)).grid(
            row=4, column=2, padx=5, pady=6, sticky="ew")
        other.columnconfigure(1, weight=1)

    def refresh_school_tab(self):
        if not hasattr(self, "school_member_tree"):
            return
        self.school_member_tree.delete(*self.school_member_tree.get_children())
        self.school_soul_tree.delete(*self.school_soul_tree.get_children())
        self.school_member_rows, self.visible_school_member_rows, self.school_soul_rows = [], [], []
        self.school_member_count.set("0 名成员")
        if not self.doc or not self.school_doc or self.role_path is None:
            self.school_title.set("未读取到宗门建筑缓存，或尚未选择角色")
            for variable in self.school_vars.values():
                variable.set("")
            return
        data = school_data(self.school_doc, self.doc, self.role_path)
        if data is None:
            self.school_title.set("当前角色没有可识别的宗门数据")
            for variable in self.school_vars.values():
                variable.set("")
            return
        name = next((n for p, n in self.roles if p == self.role_path), "未命名角色")
        self.school_title.set(f"{name}所在宗门 · {data['id']}")
        for label, value in data["fields"].items():
            self.school_vars[label].set(str(value))
        for label, selected in data["main_skills"].items():
            self.school_skill_vars[label].set(selected)
        self.school_member_rows, self.school_soul_rows = school_members(
            self.school_doc, self.doc, self.role_path, self.catalog)
        posts = sorted({row["post"] for row in self.school_member_rows})
        self.school_post_box.configure(values=["全部职位"] + posts)
        if self.school_post_filter.get() not in (["全部职位"] + posts):
            self.school_post_filter.set("全部职位")
        self.refresh_school_member_view()
        for index, row in enumerate(self.school_soul_rows):
            self.school_soul_tree.insert("", "end", iid=str(index), values=(row["name"], row["grade"]))

    def refresh_school_member_view(self):
        if not hasattr(self, "school_member_tree"):
            return
        query = self.school_member_query.get().strip().casefold()
        post = self.school_post_filter.get()
        rows = [row for row in self.school_member_rows
                if (post == "全部职位" or row["post"] == post)
                and (not query or query in row["name"].casefold() or query in row["grade"].casefold())]
        column = self.school_member_sort["column"]
        descending = self.school_member_sort["descending"]
        post_order = {"宗主": 0, "大长老": 1, "长老": 2, "真传弟子": 3, "内门弟子": 4, "外门弟子": 5}
        if column == "post":
            rows.sort(key=lambda row: (post_order.get(row["post"], 99), row["name"]), reverse=descending)
        else:
            rows.sort(key=lambda row: str(row[column]).casefold(), reverse=descending)
        self.visible_school_member_rows = rows
        self.school_member_tree.delete(*self.school_member_tree.get_children())
        for index, row in enumerate(rows):
            self.school_member_tree.insert("", "end", iid=str(index),
                                           values=(row["name"], row["post"], row["grade"]))
        self.school_member_count.set(f"显示 {len(rows)} / {len(self.school_member_rows)} 名")

    def sort_school_members(self, column):
        if self.school_member_sort["column"] == column:
            self.school_member_sort["descending"] = not self.school_member_sort["descending"]
        else:
            self.school_member_sort = {"column": column, "descending": False}
        titles = {"name": "姓名", "post": "职位", "grade": "境界"}
        for key, title in titles.items():
            marker = " ↓" if key == column and self.school_member_sort["descending"] else (
                " ↑" if key == column else "")
            self.school_member_tree.heading(key, text=title + marker)
        self.refresh_school_member_view()

    def school_action_members(self):
        if self.school_action_scope.get() == "全部成员":
            if not self.school_member_rows:
                raise DataError("当前宗门没有可操作的成员")
            return self.school_member_rows
        selection = self.school_member_tree.selection()
        if not selection:
            raise DataError("请选择名册中的一个或多个成员，或将执行范围改为全部成员")
        return [self.visible_school_member_rows[int(item)] for item in selection]

    def save_school_properties(self):
        if not self.doc or not self.school_doc or self.role_path is None:
            raise DataError("请先读取存档并选择宗门成员")
        count = update_school(self.school_doc, self.doc, self.role_path,
                              {label: variable.get() for label, variable in self.school_vars.items()})
        self.refresh_school_tab()
        self.update_status()
        self.status.set(f"已暂存 {count} 项宗门属性；导出副本后才会写入文件")

    def save_school_skills(self):
        if not self.doc or not self.school_doc or self.role_path is None:
            raise DataError("请先读取存档并选择宗门成员")
        count = update_school_main_skills(self.school_doc, self.doc, self.role_path,
                                          {label: variable.get() for label, variable in self.school_skill_vars.items()})
        self.refresh_school_tab()
        self.update_status()
        self.status.set(f"已暂存宗门主修功法，共选择 {count} 类")

    def school_make_all_genius(self):
        seed_id = self.value_id(self.school_seed.get())
        seed = self.catalog.taoist_seeds.get(str(seed_id), {})
        count = school_batch_genius(self.doc, self.school_action_members(), seed_id, seed.get("HeartSkills", 0))
        self.refresh_inspectors()
        self.refresh_tree()
        self.update_status()
        self.status.set(f"已将 {count} 名宗门成员暂存为天骄")

    def school_pay_salary(self):
        count = school_batch_salary(self.doc, self.school_action_members(), self.school_salary.get())
        self.refresh_tree()
        self.update_status()
        self.status.set(f"已为 {count} 名拥有灵石条目的宗门成员暂存工资")

    def school_make_all_friends(self):
        count = school_batch_friend(self.doc, self.school_action_members(), self.school_intimacy.get())
        self.refresh_tree()
        self.update_status()
        self.status.set(f"已将 {count} 名宗门成员对主角好感暂存为 {self.school_intimacy.get()}")

    def show_school_member_menu(self, event):
        item = self.school_member_tree.identify_row(event.y)
        if not item:
            return
        self.school_member_tree.selection_set(item)
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="在左侧角色栏定位", command=lambda: self.guard(self.locate_school_member))
        menu.tk_popup(event.x_root, event.y_root)

    def locate_school_member(self):
        selection = self.school_member_tree.selection()
        if not selection:
            raise DataError("请先选择宗门成员")
        path = self.visible_school_member_rows[int(selection[0])]["path"]
        self.role_path = path
        self.filter_roles()
        name = next((name for role_path, name in self.roles if role_path == path), "未命名角色")
        self.render_role(name)
        self.refresh_inspectors()
        self.refresh_tree()

    def build_tree_tab(self):
        tab = ttk.Frame(self.book, padding=12)
        self.book.add(tab, text="完整数据")
        ttk.Label(tab, text="展开查看数据；编辑已有标量字段。大型节点分批加载，双击“加载更多”继续查看。").pack(anchor="w", pady=(0, 8))
        frame = ttk.Frame(tab)
        frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(frame, columns=("type", "value"), selectmode="browse")
        self.tree.heading("#0", text="字段")
        self.tree.heading("type", text="类型")
        self.tree.heading("value", text="值")
        self.tree.column("#0", width=300)
        self.tree.column("type", width=80, stretch=False)
        self.tree.column("value", width=520)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewOpen>>", lambda _: self.guard(self.expand_node))
        self.tree.bind("<<TreeviewSelect>>", lambda _: self.guard(self.select_scalar))
        self.tree.bind("<Double-1>", lambda _: self.guard(self.load_more))
        edit = ttk.Frame(tab, padding=(0, 12, 0, 0))
        edit.pack(fill="x")
        self.scalar = tk.StringVar()
        ttk.Entry(edit, textvariable=self.scalar).pack(side="left", fill="x", expand=True, padx=(0, 10))
        ttk.Button(edit, text="暂存字段修改", command=lambda: self.guard(self.apply_scalar)).pack(side="right")

    def open_file(self):
        if not self.confirm_discard():
            return
        path = filedialog.askopenfilename(filetypes=[("数据文件", "*.json *.cache"), ("所有文件", "*.*")])
        if not path:
            return
        self.begin_load(path)

    def begin_load(self, path):
        self.loading = True
        self.busy_message = "正在读取数据，请等待完成"
        self.status.set("正在读取存档并建立角色索引，请稍候…")
        def worker():
            try:
                doc = Document(path)
                roles = list(find_roles(doc.data))
                world_doc = None
                school_doc = None
                source = Path(path)
                companion = source.with_name(WORLD_CACHE) if source.name == UNIT_CACHE else None
                if companion and companion.is_file():
                    world_doc = Document(companion)
                school_companion = source.with_name(SCHOOL_CACHE) if source.name == UNIT_CACHE else None
                if school_companion and school_companion.is_file():
                    school_doc = Document(school_companion)
                self.load_results.put((doc, roles, world_doc, school_doc, None))
            except Exception as exc:
                self.load_results.put((None, None, None, None, exc))
        threading.Thread(target=worker, daemon=True).start()
        self.after(80, self.finish_load)

    def finish_load(self):
        try:
            doc, roles, world_doc, school_doc, error = self.load_results.get_nowait()
        except queue.Empty:
            self.after(80, self.finish_load)
            return
        self.loading = False
        if error:
            messagebox.showerror("读取失败", str(error), parent=self)
            self.update_status()
            return
        self.doc = doc
        self.world_doc = world_doc
        self.school_doc = school_doc
        self.role_path = None
        self.player_role_path = roles[0][0] if roles else None
        self.scalar_path = None
        self.roles = roles
        self.grade_filter.set("全部境界")
        grades = sorted({role_info(get_at(doc.data, p), self.catalog)["grade"] for p, _ in roles})
        self.grade_box.configure(values=["全部境界"] + grades)
        self.filter_roles()
        self.clear_form()
        self.refresh_inventory()
        self.refresh_potmon_tab()
        self.refresh_inspectors()
        self.refresh_tree()
        kind = "旧版缓存" if doc.kind == "legacy-cache" else "JSON"
        companion = "已读取壶妖世界缓存" if world_doc else "未找到壶妖世界缓存"
        school_status = "已读取宗门建筑缓存" if school_doc else "未找到宗门建筑缓存"
        self.info.set(f"{doc.source}  |  {kind}  |  识别到 {len(self.roles)} 个角色  |  {companion}  |  {school_status}")
        self.update_status()

    def filter_roles(self):
        needle = self.search.get().casefold()
        self.visible_roles = []
        for p, n in self.roles:
            if self.sidebar_player_only and p != self.player_role_path:
                continue
            info = role_info(get_at(self.doc.data, p), self.catalog)
            if not self.sidebar_player_only and self.sex_filter.get() != "全部性别" and info["sex"] != self.sex_filter.get():
                continue
            if not self.sidebar_player_only and self.grade_filter.get() != "全部境界" and info["grade"] != self.grade_filter.get():
                continue
            if not self.sidebar_player_only and needle and not any(needle in s.casefold() for s in (n, pointer(p), info["school"])):
                continue
            self.visible_roles.append((p, n))
        self.role_list.delete(0, "end")
        selected_index = None
        for index, (p, name) in enumerate(self.visible_roles):
            self.role_list.insert("end", f"{name or '未命名'}  · {pointer(p)}")
            if p == self.role_path:
                selected_index = index
        if selected_index is not None:
            self.role_list.selection_set(selected_index)
            self.role_list.see(selected_index)
        if self.sidebar_player_only:
            self.role_count.set("仅显示主角" if self.visible_roles else "未识别到主角")
        else:
            self.role_count.set(f"显示 {len(self.visible_roles)} / {len(self.roles)} 个角色")

    def clear_form(self):
        for child in self.form_frame.winfo_children():
            child.destroy()
        self.form = []
        self.special_form = []
        self.role_title.set("选择角色后编辑属性")
        self.role_details.set("")
        if hasattr(self, "special_tree"):
            self.special_tree.delete(*self.special_tree.get_children())
            self.special_paths.clear()
            self.special_choices.clear()
        if hasattr(self, "fate_widgets"):
            self.refresh_fate_tab()

    def select_role(self):
        selection = self.role_list.curselection()
        if not selection or not self.doc:
            return
        self.role_path, name = self.visible_roles[selection[0]]
        self.render_role(name)
        self.refresh_inspectors()
        self.refresh_tree()
        self.update_status()

    def render_role(self, name=None):
        self.clear_form()
        if name is None:
            name = next((n for p, n in self.roles if p == self.role_path), "未命名角色")
        self.role_title.set(name or "未命名角色")
        role = get_at(self.doc.data, self.role_path)
        info = role_info(role, self.catalog)
        self.role_details.set(f"{info['sex']}  ·  {info['age']}  ·  {info['grade']}  ·  位置 {info['position']}\n宗门编号：{info['school'] or '无'}")
        visible = []
        for label, field in FIELDS:
            path = tuple(field.split("."))
            try:
                value = get_at(role, path)
            except (KeyError, TypeError, IndexError):
                continue
            if type(value) in (int, float):
                visible.append((label, field, path, value))
        field_groups = {
            "生存": {"q.y", "q.u", "q.qx", "q.qc", "q.l", "q.z", "q.5", "q.6", "q.x", "q.c", "q.v", "q.b", "q.n", "q.m"},
            "战斗": {"q.1", "q.2", "q.3", "q.7", "q.9", "q.qw", "q.8", "q.qq", "q.qe", "q.qr", "q.j"},
            "资质与灵根": {"q.qd", "q.qs", "q.qa", "q.qf", "q.qg", "q.qh", "q.qt", "q.qy", "q.qu", "q.qo", "q.qp", "q.qi"},
            "技艺与声望": {"q.qj", "q.qk", "q.ql", "q.qz", "q.wq", "q.ww", "q.4", "q.k", "q.i", "q.a"},
        }
        frames = {}
        for column, group in enumerate(field_groups):
            frame = ttk.LabelFrame(self.form_frame, text=group, padding=8)
            frame.grid(row=0, column=column, sticky="nsew", padx=5, pady=5)
            frames[group] = frame
            self.form_frame.columnconfigure(column, weight=1)
        counters = {group: 0 for group in field_groups}
        for label, field, path, value in visible:
            group = next((name for name, fields in field_groups.items() if field in fields), "技艺与声望")
            row = counters[group]
            counters[group] += 1
            parent = frames[group]
            ttk.Label(parent, text=label, width=10).grid(row=row, column=0, padx=4, pady=4, sticky="w")
            variable = tk.StringVar(value=str(value))
            ttk.Entry(parent, textvariable=variable, width=12).grid(row=row, column=1, padx=4, pady=4)
            self.form.append((self.role_path + path, variable))
        special_groups = ("性格", "爱好", "关系", "道心", "身份")
        special_frames = {}
        for column, group in enumerate(special_groups):
            frame = ttk.LabelFrame(self.form_frame, text=group, padding=8)
            frame.grid(row=1, column=column, sticky="nsew", padx=5, pady=5)
            special_frames[group] = frame
            self.form_frame.columnconfigure(column, weight=1)
        special_counters = {group: 0 for group in special_groups}
        for item in special_attribute_rows(self.doc, self.role_path, self.catalog):
            group = item["group"]
            if group not in special_frames:
                continue
            row = special_counters[group]
            special_counters[group] += 1
            parent = special_frames[group]
            ttk.Label(parent, text=item["label"], width=10).grid(row=row, column=0, padx=4, pady=4, sticky="w")
            choices = item["choices"]
            values = [f"{data.get('name', key)} · {key}" for key, data in choices.items()]
            current = f"{item['name']} · {item['value']}" if choices else str(item["value"])
            variable = tk.StringVar(value=current)
            ttk.Combobox(parent, textvariable=variable, values=values, width=16).grid(
                row=row, column=1, padx=4, pady=4, sticky="ew")
            parent.columnconfigure(1, weight=1)
            self.special_form.append((item["path"], variable, item.get("mode", "set")))
        ttk.Label(self.form_frame, text="名称和 ID 均可选择或直接输入；天骄需要非零道种。双鱼佩和视野在实时连接页。",
                  foreground="#8b5a2b").grid(row=2, column=0, columnspan=5, sticky="w", padx=8, pady=(2, 8))
        self.refresh_fate_tab()
        self.refresh_inventory()

    def refresh_inspectors(self):
        self.refresh_appearance_tab()
        self.refresh_school_tab()
        self.refresh_potmon_tab()
        self.refresh_relation_tab()
        self.refresh_skill_tab()

    def refresh_potmon_tab(self):
        if not hasattr(self, "potmon_tree"):
            return
        previous = self.selected_potmon.get("sole_id") if self.selected_potmon else None
        self.potmon_tree.delete(*self.potmon_tree.get_children())
        self.potmon_skill_tree.delete(*self.potmon_skill_tree.get_children())
        self.potmon_skill_rows = []
        self.selected_potmon = None
        self.potmon_rows = potmon_records(self.world_doc, self.game_path.get()) if self.world_doc else []
        if not self.world_doc:
            self.potmon_title.set("未读取到同存档槽的世界缓存，无法显示壶妖")
            return
        self.potmon_title.set(f"主角壶妖 · {len(self.potmon_rows)} 只")
        selected_item = None
        for index, row in enumerate(self.potmon_rows):
            self.potmon_tree.insert("", "end", iid=str(index),
                                    values=("☑" if row["contract"] else "☐", row["name"], row["race"],
                                            row["health"], row["transform_state"]))
            if row["sole_id"] == previous:
                selected_item = str(index)
        if selected_item is None and self.potmon_rows:
            selected_item = "0"
        if selected_item is not None:
            self.potmon_tree.selection_set(selected_item)
            self.potmon_tree.focus(selected_item)
            self.select_potmon()

    def select_potmon(self):
        selection = self.potmon_tree.selection()
        if not selection:
            return
        row = self.potmon_rows[int(selection[0])]
        self.selected_potmon = row
        self.potmon_contract.set(row["contract"])
        self.potmon_name.set(row["name"])
        self.potmon_race.set(row["race"])
        self.potmon_sex.set(row["sex"])
        self.potmon_health.set(row["health"])
        self.potmon_transform.set(row["transform_state"])
        scale = row["raw"].get("monstPropertyScale", {})
        for label, key in POTMON_PROPERTY_FIELDS.items():
            value = scale.get(key, "") if isinstance(scale, dict) else ""
            self.potmon_property_vars[label].set(str(value).split("|", 1)[-1] if value is not None else "")
        state = "disabled" if row["transformed"] else "normal"
        for widget in self.potmon_basic_widgets:
            if isinstance(widget, ttk.Combobox):
                widget.configure(state="disabled" if row["transformed"] else "readonly")
            else:
                widget.configure(state=state)
        for entry in self.potmon_property_entries.values():
            entry.configure(state=state)
        self.potmon_save_button.configure(state=state)
        self.potmon_force_button.configure(state="disabled" if row["transformed"] else "normal")
        self.refresh_potmon_skills()

    def potmon_range_tip(self, label):
        if not self.selected_potmon:
            return "请先选择壶妖"
        key = POTMON_PROPERTY_FIELDS[label]
        configured = str(self.selected_potmon.get("ranges", {}).get(key, ""))
        if "_" in configured:
            low, high = configured.split("_", 1)
            return f"正确输入范围：{low} - {high}"
        return "当前种族未提供范围；允许 1 - 1000"

    def potmon_tree_click(self, event):
        if self.potmon_tree.identify_region(event.x, event.y) != "cell" or self.potmon_tree.identify_column(event.x) != "#1":
            return None
        item = self.potmon_tree.identify_row(event.y)
        if not item:
            return None
        self.potmon_tree.selection_set(item)
        self.potmon_tree.focus(item)
        self.select_potmon()
        self.potmon_contract.set(not self.selected_potmon["contract"])
        self.after(1, lambda: self.guard(self.toggle_potmon_contract))
        return "break"

    def potmon_context_menu(self, event):
        item = self.potmon_tree.identify_row(event.y)
        if not item:
            return
        self.potmon_tree.selection_set(item)
        self.potmon_tree.focus(item)
        self.select_potmon()
        menu = tk.Menu(self, tearoff=False)
        label = "取消契约" if self.selected_potmon["contract"] else "签订契约"

        def toggle():
            self.potmon_contract.set(not self.selected_potmon["contract"])
            self.guard(self.toggle_potmon_contract)

        menu.add_command(label=label, command=toggle)
        menu.add_command(label="保存属性", command=lambda: self.guard(self.save_potmon))
        menu.tk_popup(event.x_root, event.y_root)

    def toggle_potmon_contract(self):
        if not self.world_doc or not self.selected_potmon:
            raise DataError("请先选择壶妖")
        try:
            set_potmon_contract(self.world_doc, self.selected_potmon, self.potmon_contract.get())
        except Exception:
            self.potmon_contract.set(self.selected_potmon["contract"])
            raise
        self.refresh_potmon_tab()
        self.update_status()
        self.status.set("已暂存契约修改；签订数量不受游戏契约上限限制")

    def save_potmon(self):
        if not self.world_doc or not self.selected_potmon:
            raise DataError("请先选择壶妖")
        update_potmon(self.world_doc, self.selected_potmon, self.potmon_name.get(), self.potmon_sex.get(),
                      self.potmon_health.get(), {label: value.get() for label, value in self.potmon_property_vars.items()})
        self.refresh_potmon_tab()
        self.update_status()
        self.status.set("已暂存壶妖名称、性别、健康和未化形属性范围")

    def force_conver_selected_potmon(self):
        if not self.selected_potmon:
            raise DataError("请先选择壶妖")
        if self.selected_potmon["transformed"]:
            raise DataError("所选壶妖已经化形")
        if not self.live.connected:
            raise DataError("强制化形必须由游戏原生流程创建 NPC；请先启动游戏并连接 GGBH Bridge Mod")
        if not messagebox.askyesno(
                "强制化形",
                f"确定让“{self.selected_potmon['name']}”强制化形吗？\n\n"
                "该操作会在游戏主线程调用原生化形流程并创建 NPC，可能跳过正常培养条件。\n"
                "执行后请在游戏内保存，再由工作台重新读取最新存档。",
                parent=self):
            return
        self.live_send("forcePotmonConver", {"soleId": self.selected_potmon["sole_id"]})
        self.status.set("已发送强制化形指令，等待游戏主线程处理")

    def refresh_potmon_skills(self):
        self.potmon_skill_tree.delete(*self.potmon_skill_tree.get_children())
        self.potmon_skill_rows = []
        if not self.world_doc or not self.selected_potmon:
            return
        self.potmon_skill_rows = potmon_skills(self.world_doc, self.selected_potmon, self.game_path.get())
        for index, skill in enumerate(self.potmon_skill_rows):
            self.potmon_skill_tree.insert("", "end", iid=str(index), values=(skill["type"], skill["name"], skill["id"]))

    def open_potmon_skill_dialog(self):
        if not self.world_doc or not self.selected_potmon:
            raise DataError("请先选择壶妖")
        dialog = tk.Toplevel(self)
        dialog.title("选择壶妖技能")
        dialog.geometry("820x600")
        dialog.minsize(680, 480)
        dialog.transient(self)
        dialog.grab_set()
        outer = ttk.Frame(dialog, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="选择壶妖技能", font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w")
        ttk.Label(outer, text="可按名称、编号或拼音首字母搜索，使用 Ctrl / Shift 多选；红色表示已经拥有。",
                  foreground="#62748c").pack(anchor="w", pady=(3, 10))
        filters = ttk.Frame(outer)
        filters.pack(fill="x", pady=(0, 8))
        skill_type = tk.StringVar(value="全部技能")
        ttk.Combobox(filters, textvariable=skill_type, values=("全部技能", "战斗技能", "生活技能"),
                     state="readonly", width=13).pack(side="left")
        query = tk.StringVar()
        ttk.Entry(filters, textvariable=query).pack(side="left", fill="x", expand=True, padx=(8, 0))
        tree = ttk.Treeview(outer, columns=("type", "name", "id"), show="headings", selectmode="extended")
        for column, title, width in (("type", "类型", 100), ("name", "技能名称", 420), ("id", "编号", 130)):
            tree.heading(column, text=title)
            tree.column(column, width=width, stretch=column == "name")
        tree.tag_configure("owned", foreground="#c62828")
        tree.pack(fill="both", expand=True)
        catalog = potmon_catalog(self.game_path.get())
        candidates = []
        owned = {(skill["type"], skill["id"]) for skill in self.potmon_skill_rows}

        def fill(*_):
            candidates.clear()
            tree.delete(*tree.get_children())
            needle = query.get().strip().casefold()
            for skill in catalog["skills"]:
                if skill_type.get() != "全部技能" and skill["type"] != skill_type.get():
                    continue
                if needle and needle not in skill["name"].casefold() and needle not in str(skill["id"]) and needle not in pinyin_initials(skill["name"]):
                    continue
                index = len(candidates)
                candidates.append(skill)
                exists = (skill["type"], skill["id"]) in owned
                tree.insert("", "end", iid=str(index), values=(skill["type"], skill["name"], skill["id"]),
                            tags=("owned",) if exists else ())

        query.trace_add("write", fill)
        skill_type.trace_add("write", fill)
        fill()

        def commit():
            selection = tree.selection()
            if not selection:
                messagebox.showerror("操作未完成", "请至少选择一个技能", parent=dialog)
                return
            count = add_potmon_skills(self.world_doc, self.selected_potmon,
                                      [candidates[int(item)] for item in selection])
            self.refresh_potmon_tab()
            self.update_status()
            dialog.destroy()
            self.status.set(f"已暂存添加 {count} 个壶妖技能")

        buttons = ttk.Frame(outer, padding=(0, 10, 0, 0))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text="添加所选技能", command=commit).pack(side="right", padx=8)

    def delete_selected_potmon_skills(self):
        if not self.world_doc or not self.selected_potmon:
            raise DataError("请先选择壶妖")
        selection = self.potmon_skill_tree.selection()
        if not selection:
            raise DataError("请在技能栏选择一个或多个技能")
        count = delete_potmon_skills(self.world_doc, self.selected_potmon,
                                     [self.potmon_skill_rows[int(item)] for item in selection])
        self.refresh_potmon_tab()
        self.update_status()
        self.status.set(f"已暂存删除 {count} 个壶妖技能")

    def refresh_relation_tab(self):
        if not hasattr(self, "relation_widgets"):
            return
        for widget in self.relation_widgets.values():
            widget["tree"].delete(*widget["tree"].get_children())
            widget["rows"] = []
        if not self.doc or self.role_path is None:
            self.relation_title.set("先选择角色，再管理分类关系")
            return
        name = next((n for p, n in self.roles if p == self.role_path), "未命名角色")
        self.relation_title.set(f"{name} · 分类关系")
        groups = relationship_tables(self.doc, self.role_path)
        for kind, rows in groups.items():
            widget = self.relation_widgets[kind]
            widget["rows"] = rows
            for index, row in enumerate(rows):
                widget["tree"].insert("", "end", iid=str(index),
                                      values=(row["name"], row["id"], row["intimacy"]))

    def add_relation_from_table(self, kind):
        if not self.doc or self.role_path is None:
            raise DataError("请先选择当前角色")
        widget = self.relation_widgets[kind]
        target = self.relation_target_path(widget["target"].get())
        add_relationship(self.doc, self.role_path, target, kind, widget["intimacy"].get(),
                         widget["bidirectional"].get())
        self.refresh_relation_tab()
        self.refresh_tree()
        self.update_status()
        self.status.set(f"已暂存添加{kind}关系；请在修改预览中核对")

    def open_relation_batch_dialog(self, kind):
        self.open_relation_role_dialog(kind, True)

    def open_relation_role_dialog(self, kind, multiple=False):
        if not self.doc or self.role_path is None:
            raise DataError("请先选择当前角色")
        widget = self.relation_widgets[kind]
        dialog = tk.Toplevel(self)
        dialog.title(f"{'批量添加' if multiple else '搜索角色'} · {kind}")
        dialog.geometry("1040x650")
        dialog.minsize(820, 520)
        dialog.transient(self)
        dialog.grab_set()
        outer = ttk.Frame(dialog, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text=f"{'批量添加' if multiple else '搜索角色'} · {kind}",
                  font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w")
        hint = "单击一行可连续多选，再点一次取消；" if multiple else "双击角色也可完成选择；"
        ttk.Label(outer, text=f"可按姓名或编号搜索，并按好感、性别或修为排列；{hint}红色角色表示已存在于当前关系表。",
                  foreground="#62748c").pack(anchor="w", pady=(3, 10))
        filters = ttk.Frame(outer)
        filters.pack(fill="x", pady=(0, 8))
        query = tk.StringVar()
        ttk.Label(filters, text="姓名/编号").pack(side="left")
        search_entry = ttk.Entry(filters, textvariable=query, width=34)
        search_entry.pack(side="left", fill="x", expand=True, padx=(6, 14))
        ttk.Label(filters, text="排列方式").pack(side="left")
        order = tk.StringVar(value="好感高→低")
        order_box = ttk.Combobox(filters, textvariable=order, state="readonly", width=18,
                                 values=("好感高→低", "好感低→高", "性别", "修为高→低", "修为低→高", "姓名"))
        order_box.pack(side="left", padx=(6, 0))
        tree_frame = ttk.Frame(outer)
        tree_frame.pack(fill="both", expand=True)
        columns = ("name", "sex", "grade", "intimacy", "id", "state")
        tree = ttk.Treeview(tree_frame, columns=columns, show="headings",
                            selectmode="extended" if multiple else "browse")
        heading_specs = (("name", "角色姓名", 210), ("sex", "性别", 70),
                         ("grade", "修为", 170), ("intimacy", "好感", 90),
                         ("id", "角色编号", 220), ("state", "状态", 80))
        heading_titles = {column: title for column, title, _width in heading_specs}
        heading_sort = {"column": None, "descending": False}
        for column, title, width in heading_specs:
            tree.heading(column, text=title, command=lambda c=column: sort_by_heading(c))
            tree.column(column, width=width, stretch=column == "name")
        tree.tag_configure("owned", foreground="#c62828")
        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)
        if multiple:
            tree.bind("<Button-1>", lambda event: self.toggle_tree_click(tree, event))
        candidate_rows = []
        owned_ids = {str(row["id"]) for row in relationship_tables(self.doc, self.role_path)[kind]}
        current = get_at(self.doc.data, self.role_path)
        relation_data = current.get("x", {}).get("d", {}) if isinstance(current.get("x"), dict) else {}
        if not isinstance(relation_data, dict):
            relation_data = {}

        def number(value, default=-1):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        def sort_key(row):
            column = heading_sort["column"]
            if column == "name":
                return row["name"].casefold()
            if column == "sex":
                return ({"男": 0, "女": 1}.get(row["sex"], 2), row["name"].casefold())
            if column == "grade":
                return (row["grade_id"], row["name"].casefold())
            if column == "intimacy":
                return (row["intimacy"], row["name"].casefold())
            if column == "id":
                return (number(row["id"], 2 ** 63), row["id"].casefold())
            if column == "state":
                return (row["owned"], row["name"].casefold())
            mode = order.get()
            if mode == "好感高→低":
                return (-row["intimacy"], row["name"].casefold())
            if mode == "好感低→高":
                return (row["intimacy"], row["name"].casefold())
            if mode == "性别":
                return ({"男": 0, "女": 1}.get(row["sex"], 2), row["name"].casefold())
            if mode == "修为高→低":
                return (-row["grade_id"], row["name"].casefold())
            if mode == "修为低→高":
                return (row["grade_id"], row["name"].casefold())
            return row["name"].casefold()

        def fill_candidates(*_):
            candidate_rows.clear()
            tree.delete(*tree.get_children())
            needle = query.get().strip().casefold()
            for path, name in self.roles:
                unit_id = str(path[-1])
                if path == self.role_path:
                    continue
                name = str(name or "未命名")
                if needle and needle not in unit_id.casefold() and needle not in name.casefold():
                    continue
                role = get_at(self.doc.data, path)
                info = role_info(role, self.catalog)
                candidate_rows.append({
                    "path": path, "id": unit_id, "name": name, "sex": info["sex"], "grade": info["grade"],
                    "grade_id": number(role.get("q", {}).get("d")),
                    "intimacy": number(relation_data.get(unit_id), 0), "owned": unit_id in owned_ids,
                })
            candidate_rows.sort(key=sort_key, reverse=bool(heading_sort["column"] and heading_sort["descending"]))
            for index, row in enumerate(candidate_rows):
                tree.insert("", "end", iid=str(index),
                            values=(row["name"], row["sex"], row["grade"], row["intimacy"], row["id"],
                                    "已存在" if row["owned"] else "可添加"),
                            tags=("owned",) if row["owned"] else ())

        def reset_heading_labels():
            for column, title in heading_titles.items():
                marker = " ▼" if heading_sort["column"] == column and heading_sort["descending"] else (
                    " ▲" if heading_sort["column"] == column else "")
                tree.heading(column, text=title + marker, command=lambda c=column: sort_by_heading(c))

        def sort_by_heading(column):
            if heading_sort["column"] == column:
                heading_sort["descending"] = not heading_sort["descending"]
            else:
                heading_sort["column"] = column
                heading_sort["descending"] = column in ("grade", "intimacy")
            reset_heading_labels()
            fill_candidates()

        def order_changed(*_):
            heading_sort["column"] = None
            heading_sort["descending"] = False
            reset_heading_labels()
            fill_candidates()

        query.trace_add("write", fill_candidates)
        order.trace_add("write", order_changed)
        fill_candidates()
        buttons = ttk.Frame(outer, padding=(0, 12, 0, 0))
        buttons.pack(fill="x")

        def commit():
            selected = tree.selection()
            if not selected:
                messagebox.showerror("操作未完成", "请至少选择一个角色", parent=dialog)
                return
            if not multiple:
                row = candidate_rows[int(selected[0])]
                widget["target"].set(f"{row['name']} · {row['id']}")
                dialog.destroy()
                return
            added, skipped = 0, []
            for item in selected:
                target = candidate_rows[int(item)]["path"]
                try:
                    add_relationship(self.doc, self.role_path, target, kind, widget["intimacy"].get(),
                                     widget["bidirectional"].get())
                    added += 1
                except DataError as exc:
                    skipped.append(f"{target[-1]}：{exc}")
            self.refresh_relation_tab()
            self.refresh_tree()
            self.update_status()
            self.status.set(f"已批量添加 {added} 个{kind}关系；跳过 {len(skipped)} 个")
            dialog.destroy()
            if skipped:
                messagebox.showinfo("批量添加完成", f"成功添加 {added} 个，跳过 {len(skipped)} 个。\n\n" +
                                    "\n".join(skipped[:12]), parent=self)

        tree.bind("<Double-1>", lambda _event: commit() if not multiple else None)
        ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text="确认批量添加" if multiple else "选中角色", command=commit).pack(side="right", padx=8)
        search_entry.focus_set()

    def delete_relation_from_table(self, kind):
        if not self.doc or self.role_path is None:
            raise DataError("请先选择当前角色")
        widget = self.relation_widgets[kind]
        selection = widget["tree"].selection()
        if not selection:
            raise DataError(f"请先在{kind}表格中选择一个或多个角色")
        selected_rows = [widget["rows"][int(item)] for item in selection]
        removed, skipped = 0, []
        for row in selected_rows:
            try:
                target = self.relation_target_path(row["id"])
                remove_relationship(self.doc, self.role_path, target, kind, widget["bidirectional"].get())
                removed += 1
            except DataError as exc:
                skipped.append(f"{row['id']}：{exc}")
        self.refresh_relation_tab()
        self.refresh_tree()
        self.update_status()
        self.status.set(f"已批量删除 {removed} 个{kind}关系；跳过 {len(skipped)} 个。请在修改预览中核对")
        if skipped:
            messagebox.showinfo("批量删除完成", f"成功删除 {removed} 个，跳过 {len(skipped)} 个。\n\n" +
                                "\n".join(skipped[:12]), parent=self)

    def refresh_skill_tab(self):
        if not hasattr(self, "skill_tree"):
            return
        previous = self.skill_tree.selection()
        previous_id = self.skill_rows_by_item.get(previous[0], {}).get("uuid") if previous else None
        self.skill_tree.delete(*self.skill_tree.get_children())
        self.skill_rows_by_item.clear()
        if not self.doc or self.role_path is None:
            self.skill_tree_title.set("先选择角色，再选择已学习功法")
            return
        name = next((n for p, n in self.roles if p == self.role_path), "未命名角色")
        self.skill_tree_title.set(f"{name} · 已学习功法")
        selected_item = None
        for record in skill_records(self.doc, self.role_path, self.catalog):
            item = self.skill_tree.insert("", "end", values=(record["equipped"], record["name"], record["type"],
                                                               record["grade"], record["progress"]))
            self.skill_rows_by_item[item] = record
            if record["uuid"] == previous_id:
                selected_item = item
        if selected_item:
            self.skill_tree.selection_set(selected_item)
            self.skill_tree.focus(selected_item)
            self.select_skill_record()

    def refresh_skill_name_choices(self):
        try:
            type_id = int(self.value_id(self.skill_type_value.get()))
        except (TypeError, ValueError):
            self.skill_info_boxes["功法名称"].configure(values=[])
            return
        values = []
        for key, data in self.catalog.skill_info.items():
            if int(data.get("TypeID", -1)) == type_id:
                values.append(f"{data.get('name', key)} · {key}")
        self.skill_info_boxes["功法名称"].configure(values=values)
        self.refresh_skill_effect_choices()

    def refresh_skill_effect_choices(self):
        try:
            type_id = int(self.value_id(self.skill_type_value.get()))
            info_id = int(self.value_id(self.skill_name_value.get()))
            grade_id = int(self.value_id(self.skill_grade_value.get()))
        except (TypeError, ValueError):
            choices = ["空 · 0"]
        else:
            choices = ["空 · 0"] + [
                f"{str(name).replace(chr(10), ' ')[:90]} · {effect_id}"
                for effect_id, name in skill_effect_candidates(self.catalog, type_id, info_id, grade_id)]
        for box in self.skill_effect_boxes:
            box.configure(values=choices)
        self.skill_effect_candidate_box.configure(values=choices[1:])

    def select_skill_record(self):
        selection = self.skill_tree.selection()
        if not selection or selection[0] not in self.skill_rows_by_item:
            return
        record = self.skill_rows_by_item[selection[0]]
        type_name = self.catalog.skill_types.get(str(record["type_id"]), {}).get("name", record["type"])
        grade_name = self.catalog.skill_grades.get(str(record["grade_id"]), {}).get("name", record["grade"])
        self.skill_type_value.set(f"{type_name} · {record['type_id']}")
        self.refresh_skill_name_choices()
        self.skill_name_value.set(f"{record['name']} · {record['info_id']}")
        self.skill_grade_value.set(f"{grade_name} · {record['grade_id']}")
        self.skill_inheritance_value.set(("是 · 1" if record["inheritance"] else "否 · 0"))
        self.skill_progress_value.set(str(record["progress"]))
        self.refresh_skill_effect_choices()
        names = dict(skill_effect_candidates(
            self.catalog, record["type_id"], record["info_id"], record["grade_id"]))
        ids = list(record["effects"]) + [0] * (11 - len(record["effects"]))
        exps = list(record["effect_exp"]) + [0] * (11 - len(record["effect_exp"]))
        for index, (effect_var, exp_var) in enumerate(self.skill_effect_vars):
            effect_id = ids[index]
            effect_var.set(f"{names.get(effect_id, '未知词条' if effect_id else '空')} · {effect_id}")
            exp_var.set(str(exps[index]))

    def place_skill_effect(self):
        value = self.skill_effect_candidate.get().strip()
        if not value:
            raise DataError("请先在词条添加栏选择词条")
        index = int(self.skill_effect_target.get().split()[-1]) - 1
        self.skill_effect_vars[index][0].set(value)

    def clear_skill_effect_slot(self):
        index = int(self.skill_effect_target.get().split()[-1]) - 1
        self.skill_effect_vars[index][0].set("空 · 0")
        self.skill_effect_vars[index][1].set("0")

    def skill_form_perfect(self):
        for effect_var, exp_var in self.skill_effect_vars:
            if self.value_id(effect_var.get()) not in ("", "0"):
                exp_var.set("600")

    def skill_form_enable(self):
        self.skill_progress_value.set("9999999")

    def save_skill_form(self):
        skill_id = self.selected_skill_id()
        effects = [self.value_id(effect.get()) or "0" for effect, _exp in self.skill_effect_vars]
        exps = [exp.get() for _effect, exp in self.skill_effect_vars]
        update_skill(
            self.doc, self.role_path, skill_id,
            type_id=self.value_id(self.skill_type_value.get()),
            info_id=self.value_id(self.skill_name_value.get()),
            grade_id=self.value_id(self.skill_grade_value.get()),
            inheritance=self.value_id(self.skill_inheritance_value.get()),
            progress=self.skill_progress_value.get(), effects=effects, effect_exp=exps)
        self.refresh_skill_tab()
        self.refresh_tree()
        self.update_status()
        self.status.set("已统一暂存所选功法的信息、传承、进度和词条修改；请在修改预览中核对")

    def select_inspector_value(self, attribute):
        tree = getattr(self, attribute)
        selection = tree.selection()
        variable = getattr(self, attribute + "_value")
        variable.set("")
        if not selection or selection[0] not in self.inspector_paths[attribute]:
            return
        path = self.inspector_paths[attribute][selection[0]]
        value = get_at(self.doc.data, path)
        variable.set(str(value).lower() if isinstance(value, bool) else str(value))

    def apply_inspector_value(self, attribute):
        tree = getattr(self, attribute)
        selection = tree.selection()
        if not self.doc or not selection or selection[0] not in self.inspector_paths[attribute]:
            raise DataError("请选择一个可编辑的已有字段；复合关系和列表保持只读")
        path = self.inspector_paths[attribute][selection[0]]
        self.doc.set_many([(path, getattr(self, attribute + "_value").get())])
        self.refresh_inspectors()
        self.refresh_tree()
        self.update_status()

    def selected_skill_id(self):
        selection = self.skill_tree.selection()
        if not self.doc or self.role_path is None or not selection:
            raise DataError("请先选择角色和一项功法")
        record = self.skill_rows_by_item.get(selection[0])
        if not record:
            raise DataError("所选功法结构无法安全修改")
        return record["uuid"]

    def perfect_selected_skill(self):
        skill_id = self.selected_skill_id()
        skills, effects = perfect_skill_comprehension(self.doc, self.role_path, skill_id)
        self.refresh_inspectors()
        self.refresh_tree()
        self.update_status()
        self.status.set(f"已暂存 {skills} 项功法、{effects} 条词条的完美参悟值；请查看修改预览")

    def enable_selected_skill(self):
        skill_id = self.selected_skill_id()
        count = enable_skill_effects(self.doc, self.role_path, skill_id)
        self.refresh_inspectors()
        self.refresh_tree()
        self.update_status()
        self.status.set(f"已暂存 {count} 项功法的词条生效值；请查看修改预览")

    def perfect_all_skills(self):
        if not self.doc or self.role_path is None:
            raise DataError("请先选择角色")
        skills, effects = perfect_skill_comprehension(self.doc, self.role_path)
        enabled = enable_skill_effects(self.doc, self.role_path)
        self.refresh_inspectors()
        self.refresh_tree()
        self.update_status()
        self.status.set(f"已暂存 {skills} 项功法、{effects} 条词条完美参悟，并使 {enabled} 项功法词条生效")

    def relation_target_path(self, text):
        unit_id = text.rsplit(" · ", 1)[-1].strip()
        matches = [path for path, name in self.roles if str(path[-1]) == unit_id or name == text.strip()]
        if len(matches) != 1:
            raise DataError("请选择下拉列表中的唯一目标角色")
        return matches[0]

    def add_relation_single(self):
        if not self.doc or self.role_path is None:
            raise DataError("请先在属性页选择当前角色")
        target = self.relation_target_path(self.relation_target.get())
        add_relationship(self.doc, self.role_path, target, self.relation_kind.get(), self.relation_intimacy.get())
        self.refresh_inspectors()
        self.refresh_tree()
        self.update_status()

    def add_relation_batch(self):
        if not self.doc or self.role_path is None:
            raise DataError("请先在属性页选择当前角色")
        targets = [self.visible_roles[index][0] for index in self.role_list.curselection()
                   if self.visible_roles[index][0] != self.role_path]
        if not targets:
            raise DataError("请在属性页按 Ctrl 或 Shift 多选目标角色；当前角色不会添加给自己")
        added, skipped = 0, []
        for target in targets:
            try:
                add_relationship(self.doc, self.role_path, target, self.relation_kind.get(), self.relation_intimacy.get())
                added += 1
            except DataError as exc:
                skipped.append(f"{target[-1]}：{exc}")
        self.refresh_inspectors()
        self.refresh_tree()
        self.update_status()
        self.status.set(f"已批量添加 {added} 个关系；跳过 {len(skipped)} 个。请在修改预览中核对")

    @staticmethod
    def value_id(text):
        text = str(text).strip()
        if " · " in text:
            text = text.rsplit(" · ", 1)[-1].strip()
        return text

    def refresh_special_attributes(self):
        if not hasattr(self, "special_tree"):
            return
        self.special_tree.delete(*self.special_tree.get_children())
        self.special_paths.clear()
        self.special_choices.clear()
        self.special_value.set("")
        if not self.doc or self.role_path is None:
            return
        for row in special_attribute_rows(self.doc, self.role_path, self.catalog):
            item = self.special_tree.insert("", "end", text=f"{row['group']} / {row['label']}",
                                            values=(row["name"], row["value"]))
            self.special_paths[item] = row["path"]
            self.special_choices[item] = row["choices"]

    def select_special_attribute(self):
        selection = self.special_tree.selection()
        self.special_value.set("")
        self.special_box.configure(values=[])
        if not selection or selection[0] not in self.special_paths:
            return
        item = selection[0]
        value = get_at(self.doc.data, self.special_paths[item])
        choices = self.special_choices.get(item, {})
        values = [f"{data.get('name', key)} · {key}" for key, data in choices.items()]
        self.special_box.configure(values=values)
        name = choices.get(str(value), {}).get("name")
        self.special_value.set(f"{name} · {value}" if name else str(value))

    def apply_special_attribute(self):
        selection = self.special_tree.selection()
        if not self.doc or self.role_path is None or not selection or selection[0] not in self.special_paths:
            raise DataError("请选择一个身份、性格或爱好字段")
        path = self.special_paths[selection[0]]
        value = self.value_id(self.special_value.get())
        if path[-2:] == ("qe", "u") and value == "2":
            seed = get_at(self.doc.data, self.role_path + ("qe", "y"))
            if not seed:
                raise DataError("设为天骄前必须先选择非零道种，否则人物面板会异常")
        self.doc.set_many([(path, value)])
        self.refresh_special_attributes()
        self.refresh_tree()
        self.update_status()

    def refresh_fate_tab(self):
        if not hasattr(self, "fate_widgets"):
            return
        for section, widget in self.fate_widgets.items():
            tree = widget["tree"]
            tree.delete(*tree.get_children())
            widget["entries"] = []
            if not self.doc or self.role_path is None:
                continue
            entries = fate_entries(self.doc, self.role_path, section, self.catalog)
            widget["entries"] = entries
            needle = widget["search"].get().strip().casefold()
            for index, entry in enumerate(entries):
                if needle and needle not in str(entry["id"]).casefold() and needle not in entry["name"].casefold():
                    continue
                tree.insert("", "end", iid=str(index), values=(entry["id"], entry["name"]))

    def add_fate_ui(self, section):
        if not self.doc or self.role_path is None:
            raise DataError("请先在属性页选择角色")
        self.open_fate_dialog(section, "add")

    def selected_fate_entry(self, section):
        widget = self.fate_widgets[section]
        selection = widget["tree"].selection()
        if not selection:
            raise DataError(f"请先选择一条{section}")
        return widget["entries"][int(selection[0])]

    def replace_fate_ui(self, section):
        if not self.doc or self.role_path is None:
            raise DataError("请先在属性页选择角色")
        self.open_fate_dialog(section, "replace")

    def delete_fate_ui(self, section):
        if not self.doc or self.role_path is None:
            raise DataError("请先在属性页选择角色")
        self.open_fate_dialog(section, "delete")

    def open_fate_dialog(self, section, action):
        titles = {"add": "添加气运", "replace": "替换气运", "delete": "删除气运"}
        dialog = tk.Toplevel(self)
        dialog.title(f"{titles[action]} · {section}")
        dialog.geometry("920x620")
        dialog.minsize(720, 500)
        dialog.transient(self)
        dialog.grab_set()
        outer = ttk.Frame(dialog, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text=f"{section} · {titles[action]}", font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w")
        ttk.Label(outer, text="可按名称或编号搜索；选择目标后点击底部确认。候选列表中红色项目表示角色已经拥有。",
                  foreground="#62748c").pack(anchor="w", pady=(3, 12))
        content = ttk.Frame(outer)
        content.pack(fill="both", expand=True)
        current_entries = fate_entries(self.doc, self.role_path, section, self.catalog)
        current_tree = None
        candidate_tree = None
        candidate_rows = []

        def make_tree(parent, label, selectmode="browse"):
            frame = ttk.LabelFrame(parent, text=label, padding=8)
            frame.pack(side="left", fill="both", expand=True, padx=(0, 8))
            query = tk.StringVar()
            ttk.Entry(frame, textvariable=query).pack(fill="x", pady=(0, 7))
            tree = ttk.Treeview(frame, columns=("id", "name"), show="headings", selectmode=selectmode)
            tree.heading("id", text="编号")
            tree.heading("name", text="气运名称")
            tree.column("id", width=130, stretch=False)
            tree.column("name", width=260)
            scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=scroll.set)
            scroll.pack(side="right", fill="y")
            tree.pack(fill="both", expand=True)
            return tree, query

        if action in ("replace", "delete"):
            current_tree, current_query = make_tree(content, "角色当前已有气运")

            def fill_current(*_):
                current_tree.delete(*current_tree.get_children())
                needle = current_query.get().strip().casefold()
                for index, entry in enumerate(current_entries):
                    if needle and needle not in str(entry["id"]).casefold() and needle not in entry["name"].casefold():
                        continue
                    current_tree.insert("", "end", iid=str(index), values=(entry["id"], entry["name"]))

            current_query.trace_add("write", fill_current)
            fill_current()
            selected = self.fate_widgets[section]["tree"].selection()
            if selected and current_tree.exists(selected[0]):
                current_tree.selection_set(selected[0])
                current_tree.focus(selected[0])

        if action in ("add", "replace"):
            candidate_tree, candidate_query = make_tree(
                content, "可选择的气运资料 · 添加时可用 Ctrl / Shift 多选",
                "extended" if action == "add" else "browse")
            candidate_tree.tag_configure("owned", foreground="#c62828")
            owned_ids = {int(entry["id"]) for entry in current_entries}

            def fill_candidates(*_):
                nonlocal candidate_rows
                candidate_tree.delete(*candidate_tree.get_children())
                candidate_rows = fate_candidates(self.catalog, section, candidate_query.get())
                for index, (fate_id, name) in enumerate(candidate_rows):
                    tags = ("owned",) if int(fate_id) in owned_ids else ()
                    candidate_tree.insert("", "end", iid=str(index), values=(fate_id, name), tags=tags)

            candidate_query.trace_add("write", fill_candidates)
            fill_candidates()

        buttons = ttk.Frame(outer, padding=(0, 12, 0, 0))
        buttons.pack(fill="x")

        def selected_current():
            selection = current_tree.selection() if current_tree else ()
            if not selection:
                raise DataError("请先选择角色当前的一条气运")
            return current_entries[int(selection[0])]

        def selected_candidates():
            selection = candidate_tree.selection() if candidate_tree else ()
            if not selection:
                raise DataError("请至少选择一条候选气运")
            return [candidate_rows[int(item)][0] for item in selection]

        def commit():
            try:
                if action == "add":
                    add_fates(self.doc, self.role_path, section, selected_candidates())
                elif action == "replace":
                    replace_fate(self.doc, self.role_path, section, selected_current(), selected_candidates()[0])
                else:
                    delete_fate(self.doc, self.role_path, section, selected_current())
                self.refresh_fate_tab()
                self.refresh_tree()
                self.update_status()
                dialog.destroy()
            except Exception as exc:
                messagebox.showerror("操作未完成", str(exc), parent=dialog)

        ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text=f"确认{titles[action]}", command=commit).pack(side="right", padx=8)

    def flush_form(self):
        if self.doc and (self.form or self.special_form):
            edits = [(p, v.get()) for p, v in self.form]
            edits.extend((p, self.value_id(v.get())) for p, v, mode in self.special_form if mode == "set")
            self.doc.set_many(edits)

    def apply_role(self):
        if not self.doc or self.role_path is None:
            raise DataError("请先选择角色")
        special_values = {path: self.value_id(variable.get()) for path, variable, mode in self.special_form if mode == "set"}
        append_values = [(path, self.value_id(variable.get())) for path, variable, mode in self.special_form if mode == "append"]
        hero_path = self.role_path + ("qe", "u")
        seed_path = self.role_path + ("qe", "y")
        if special_values.get(hero_path) == "2":
            seed = special_values.get(seed_path, get_at(self.doc.data, seed_path))
            if str(seed) in ("", "0"):
                raise DataError("设为天骄前必须先选择非零道种，否则人物面板会异常")
        edits = [(p, v.get()) for p, v in self.form]
        edits.extend(special_values.items())
        self.doc.set_many(edits)
        for path, value in append_values:
            if value not in ("", "0"):
                self.doc.append(path, int(value))
        self.render_role()
        self.refresh_inspectors()
        self.refresh_tree()
        self.update_status()

    def refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        self.nodes.clear()
        self.paging.clear()
        self.scalar_path = None
        if self.doc:
            root = self.insert_node("", "数据", (), self.doc.data)
            self.populate(root)
            self.tree.item(root, open=True)

    def insert_node(self, parent, label, path, value):
        composite = isinstance(value, (dict, list))
        summary = f"{len(value)} 项" if composite else json.dumps(value, ensure_ascii=False)
        node = self.tree.insert(parent, "end", text=str(label), values=(type(value).__name__, summary[:300]))
        self.nodes[node] = path
        if composite and value:
            self.tree.insert(node, "end", text="展开加载…")
        return node

    def populate(self, node, offset=0):
        children = self.tree.get_children(node)
        if not offset and (not children or children[0] in self.nodes):
            return
        if not offset:
            self.tree.delete(*children)
        path = self.nodes[node]
        value = get_at(self.doc.data, path)
        items = value.items() if isinstance(value, dict) else enumerate(value)
        for i, (key, item) in enumerate(items):
            if i < offset:
                continue
            if i == offset + 500:
                more = self.tree.insert(node, "end", text=f"加载更多（已显示 {i} / {len(value)}）")
                self.paging[more] = (node, i)
                break
            self.insert_node(node, key, path + (key,), item)

    def load_more(self):
        node = self.tree.focus()
        if node in self.paging:
            parent, offset = self.paging.pop(node)
            self.tree.delete(node)
            self.populate(parent, offset)

    def expand_node(self):
        node = self.tree.focus()
        if node in self.nodes:
            self.populate(node)

    def select_scalar(self):
        self.scalar_path = None
        selection = self.tree.selection()
        if not selection or selection[0] not in self.nodes:
            return
        path = self.nodes[selection[0]]
        value = get_at(self.doc.data, path)
        if value is None or isinstance(value, (dict, list)):
            self.scalar.set("")
            return
        self.scalar_path = path
        self.scalar.set(str(value).lower() if isinstance(value, bool) else str(value))

    def apply_scalar(self):
        if not self.doc or self.scalar_path is None:
            raise DataError("请先选择一个可编辑字段")
        self.flush_form()
        self.doc.set_many([(self.scalar_path, self.scalar.get())])
        node = self.tree.selection()[0]
        value = get_at(self.doc.data, self.scalar_path)
        self.tree.item(node, values=(type(value).__name__, json.dumps(value, ensure_ascii=False)[:300]))
        # Remove stale role inputs after a generic edit.
        self.role_path = None
        self.clear_form()
        self.refresh_inventory()
        self.update_status()

    def choose_save(self):
        slots = discover_saves()
        window = tk.Toplevel(self)
        window.title("本机存档 · 只读打开")
        window.geometry("760x500")
        ttk.Label(window, text="按最近修改时间排序；仅读取数据，导出不会覆盖存档。", padding=16).pack(anchor="w")
        rows = ttk.Treeview(window, columns=("modified", "size"), selectmode="browse")
        rows.heading("#0", text="槽位")
        rows.heading("modified", text="修改时间")
        rows.heading("size", text="角色缓存大小")
        for i, slot in enumerate(slots):
            rows.insert("", "end", iid=str(i), text=slot.label,
                        values=(datetime.fromtimestamp(slot.modified).strftime("%Y-%m-%d %H:%M"), f"{slot.size / 1024 / 1024:.1f} MB"))
        if not slots:
            ttk.Label(window, text="未找到有效槽位，可使用“打开文件”手动选择备份。", padding=16).pack()
        def open_selected():
            selection = rows.selection()
            if selection and self.confirm_discard():
                path = slots[int(selection[0])].path
                window.destroy()
                self.begin_load(path)
        ttk.Button(window, text="打开所选槽位", command=lambda: self.guard(open_selected)).pack(side="bottom", pady=12)
        rows.pack(fill="both", expand=True, padx=16)
        rows.bind("<Double-1>", lambda _: self.guard(open_selected))

    def open_latest_save(self):
        if not self.confirm_discard():
            return
        slots = discover_saves()
        if not slots:
            raise DataError("未找到有效存档槽位，可使用“打开文件”手动选择备份")
        self.begin_load(slots[0].path)

    def copy_attributes(self):
        if not self.doc or self.role_path is None:
            raise DataError("请先选择角色")
        self.flush_form()
        self.attribute_clipboard = attribute_values(self.doc, self.role_path)
        self.update_status()
        self.status.set(f"已复制 {len(self.attribute_clipboard)} 个基础属性，可粘贴到另一角色；不含姓名、关系和身份编号")

    def paste_attributes(self):
        if not self.doc or self.role_path is None or not self.attribute_clipboard:
            raise DataError("请先复制属性，再选择目标角色")
        self.flush_form()
        count = paste_attributes(self.doc, self.role_path, self.attribute_clipboard)
        self.render_role()
        self.refresh_tree()
        self.update_status()
        self.status.set(f"已向当前角色暂存 {count} 个基础属性；请查看修改预览")

    def refill_selected(self):
        if not self.doc:
            raise DataError("请先打开存档")
        selection = self.role_list.curselection()
        if not selection:
            raise DataError("请先选择一个或多个角色")
        self.flush_form()
        paths = [self.visible_roles[i][0] for i in selection]
        count = refill(self.doc, paths)
        if self.role_path is not None:
            self.render_role()
        self.refresh_tree()
        self.update_status()
        self.status.set(f"已为 {len(paths)} 个所选角色暂存补满状态，共检查 {count} 个字段；请查看修改预览")

    def build_inventory_tab(self):
        self.inventory_tab = ttk.Frame(self.book, padding=12)
        self.book.add(self.inventory_tab, text="物品")
        self.inventory_title = tk.StringVar(value="先在角色页选择角色")
        ttk.Label(self.inventory_tab, textvariable=self.inventory_title, font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w")
        ttk.Label(self.inventory_tab, text="左侧管理角色背包，右侧从完整物品资料中按分类、名称或拼音首字母搜索并批量添加。",
                  wraplength=1000, foreground="#62748c").pack(anchor="w", pady=(4, 10))
        panes = ttk.Panedwindow(self.inventory_tab, orient="horizontal")
        panes.pack(fill="both", expand=True)
        bag = ttk.LabelFrame(panes, text="角色背包", padding=8)
        catalog = ttk.LabelFrame(panes, text="全物品分类栏", padding=8)
        panes.add(bag, weight=1)
        panes.add(catalog, weight=1)

        self.item_search = tk.StringVar()
        self.item_search.trace_add("write", lambda *_: self.filter_inventory())
        bag_search = ttk.Frame(bag)
        bag_search.pack(fill="x", pady=(0, 7))
        self.bag_item_type = tk.StringVar(value="全部分类")
        self.bag_item_type_box = ttk.Combobox(bag_search, textvariable=self.bag_item_type,
                                              values=["全部分类"], state="readonly", width=11)
        self.bag_item_type_box.pack(side="left")
        self.bag_item_type_box.bind("<<ComboboxSelected>>", lambda _: self.filter_inventory())
        ttk.Label(bag_search, text="搜索").pack(side="left")
        ttk.Entry(bag_search, textvariable=self.item_search).pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.item_rows = []
        self.visible_item_rows = []
        self.item_sort = {"column": "name", "descending": False}
        self.item_heading_titles = {"name": "名称", "type": "类型", "quantity": "数量", "id": "编号"}
        self.items_tree = ttk.Treeview(bag, columns=("name", "type", "quantity", "id"),
                                       show="headings", selectmode="extended")
        for column, width in (("name", 210), ("type", 90), ("quantity", 75), ("id", 110)):
            self.items_tree.heading(column, text=self.item_heading_titles[column],
                                    command=lambda c=column: self.sort_inventory(c))
            self.items_tree.column(column, width=width, stretch=column == "name")
        bag_scroll = ttk.Scrollbar(bag, orient="vertical", command=self.items_tree.yview)
        self.items_tree.configure(yscrollcommand=bag_scroll.set)
        bag_scroll.pack(side="right", fill="y")
        self.items_tree.pack(fill="both", expand=True)
        self.items_tree.bind("<<TreeviewSelect>>", self.select_item)
        bag_bottom = ttk.Frame(bag, padding=(0, 9, 0, 0))
        bag_bottom.pack(fill="x")
        ttk.Label(bag_bottom, text="数量").pack(side="left", padx=(0, 6))
        self.item_quantity = tk.StringVar()
        ttk.Entry(bag_bottom, textvariable=self.item_quantity, width=12).pack(side="left")
        ttk.Button(bag_bottom, text="修改所选数量", command=lambda: self.guard(self.apply_quantity)).pack(side="left", padx=8)
        ttk.Button(bag_bottom, text="强制删除所选", command=lambda: self.guard(self.force_delete_inventory_items)).pack(side="left", padx=4)

        catalog_filters = ttk.Frame(catalog)
        catalog_filters.pack(fill="x", pady=(0, 7))
        self.catalog_item_type = tk.StringVar(value="全部分类")
        item_types = sorted({str(prop.get("type", "未分类")) for prop in self.catalog.props.values()})
        self.catalog_item_type_box = ttk.Combobox(catalog_filters, textvariable=self.catalog_item_type,
                                                  values=["全部分类"] + item_types, state="readonly", width=13)
        self.catalog_item_type_box.pack(side="left")
        self.catalog_item_type_box.bind("<<ComboboxSelected>>", lambda _: self.filter_catalog_items())
        self.catalog_item_search = tk.StringVar()
        self.catalog_item_search.trace_add("write", lambda *_: self.filter_catalog_items())
        ttk.Entry(catalog_filters, textvariable=self.catalog_item_search).pack(side="left", fill="x", expand=True, padx=(7, 0))
        self.catalog_item_rows = [
            {"id": int(prop_id), "name": str(prop.get("name", f"未知物品 #{prop_id}")),
             "type": str(prop.get("type", "未分类")), "pinyin": pinyin_initials(prop.get("name", ""))}
            for prop_id, prop in self.catalog.props.items() if str(prop_id).isdigit()
        ]
        self.visible_catalog_item_rows = []
        self.catalog_item_sort = {"column": "name", "descending": False}
        self.catalog_heading_titles = {"name": "名称", "type": "类型", "id": "编号"}
        self.catalog_items_tree = ttk.Treeview(catalog, columns=("name", "type", "id"), show="headings",
                                               selectmode="extended")
        for column, width in (("name", 250), ("type", 90), ("id", 120)):
            self.catalog_items_tree.heading(column, text=self.catalog_heading_titles[column],
                                             command=lambda c=column: self.sort_catalog_items(c))
            self.catalog_items_tree.column(column, width=width, stretch=column == "name")
        catalog_scroll = ttk.Scrollbar(catalog, orient="vertical", command=self.catalog_items_tree.yview)
        self.catalog_items_tree.configure(yscrollcommand=catalog_scroll.set)
        catalog_scroll.pack(side="right", fill="y")
        self.catalog_items_tree.pack(fill="both", expand=True)
        catalog_bottom = ttk.Frame(catalog, padding=(0, 9, 0, 0))
        catalog_bottom.pack(fill="x")
        ttk.Label(catalog_bottom, text="添加数量").pack(side="left")
        self.catalog_item_quantity = tk.StringVar(value="1")
        ttk.Entry(catalog_bottom, textvariable=self.catalog_item_quantity, width=12).pack(side="left", padx=6)
        ttk.Button(catalog_bottom, text="添加所选物品", command=lambda: self.guard(
            self.add_selected_catalog_items)).pack(side="left", padx=4)
        ttk.Label(catalog_bottom, text="Ctrl / Shift 多选", foreground="#62748c").pack(side="right")
        self.filter_catalog_items()

    def show_inventory(self):
        if not self.doc or self.role_path is None:
            raise DataError("请先选择角色")
        self.flush_form()
        self.refresh_inventory()
        self.book.select(self.inventory_tab)

    def refresh_inventory(self):
        self.item_rows = inventory(self.doc, self.role_path, self.catalog) if self.doc and self.role_path is not None else []
        name = next((n for p, n in self.roles if p == self.role_path), "未选择角色")
        self.inventory_title.set(f"{name} · {len(self.item_rows)} 个可编辑物品条目")
        types = sorted({row["type"] for row in self.item_rows})
        self.bag_item_type_box.configure(values=["全部分类"] + types)
        if self.bag_item_type.get() not in (["全部分类"] + types):
            self.bag_item_type.set("全部分类")
        self.filter_inventory()

    def filter_inventory(self):
        if not hasattr(self, "items_tree"):
            return
        self.items_tree.delete(*self.items_tree.get_children())
        self.item_quantity.set("")
        needle = self.item_search.get().strip().casefold()
        selected_type = self.bag_item_type.get()
        self.visible_item_rows = [
            row for row in self.item_rows
            if (selected_type == "全部分类" or row["type"] == selected_type)
            and (not needle or needle in row["name"].casefold() or needle in str(row["id"])
                 or needle in pinyin_initials(row["name"]))
        ]
        column = self.item_sort["column"]
        self.visible_item_rows.sort(key=lambda row: (row[column].casefold() if isinstance(row[column], str) else row[column],
                                                     row["name"].casefold()),
                                    reverse=self.item_sort["descending"])
        for i, row in enumerate(self.visible_item_rows):
            self.items_tree.insert("", "end", iid=str(i),
                                   values=(row["name"], row["type"], row["quantity"], row["id"]))

    def sort_inventory(self, column):
        if self.item_sort["column"] == column:
            self.item_sort["descending"] = not self.item_sort["descending"]
        else:
            self.item_sort = {"column": column, "descending": column == "quantity"}
        for key, title in self.item_heading_titles.items():
            marker = " ▼" if key == column and self.item_sort["descending"] else (" ▲" if key == column else "")
            self.items_tree.heading(key, text=title + marker, command=lambda c=key: self.sort_inventory(c))
        self.filter_inventory()

    def select_item(self, _=None):
        selection = self.items_tree.selection()
        if selection:
            self.item_quantity.set(str(self.visible_item_rows[int(selection[0])]["quantity"]))

    def apply_quantity(self):
        selection = self.items_tree.selection()
        if not self.doc or not selection:
            raise DataError("请选择一个物品条目")
        if len(selection) != 1:
            raise DataError("修改数量时只能选择一个物品；批量选择用于强制删除")
        row = self.visible_item_rows[int(selection[0])]
        set_quantity(self.doc, row, self.item_quantity.get())
        row["quantity"] = get_at(self.doc.data, row["path"])
        self.filter_inventory()
        self.refresh_tree()
        self.update_status()

    def force_delete_inventory_items(self):
        if not self.doc or self.role_path is None:
            raise DataError("请先选择角色")
        selection = self.items_tree.selection()
        if not selection:
            raise DataError("请在左侧角色背包中选择一个或多个物品")
        rows = [self.visible_item_rows[int(item)] for item in selection]
        names = "、".join(row["name"] for row in rows[:6])
        if len(rows) > 6:
            names += f" 等 {len(rows)} 项"
        if not messagebox.askyesno(
                "强制删除背包物品",
                f"确定从当前角色背包强制删除以下物品吗？\n\n{names}\n\n"
                "修改将暂存在内存副本中，可在导出前使用“撤销全部”恢复。",
                parent=self):
            return
        count = delete_items(self.doc, self.role_path, rows)
        self.refresh_inventory()
        self.refresh_tree()
        self.update_status()
        self.status.set(f"已强制删除 {count} 个背包物品；导出前请检查修改预览")

    def filter_catalog_items(self):
        if not hasattr(self, "catalog_items_tree"):
            return
        self.catalog_items_tree.delete(*self.catalog_items_tree.get_children())
        needle = self.catalog_item_search.get().strip().casefold()
        selected_type = self.catalog_item_type.get()
        self.visible_catalog_item_rows = [
            row for row in self.catalog_item_rows
            if (selected_type == "全部分类" or row["type"] == selected_type)
            and (not needle or needle in row["name"].casefold() or needle in str(row["id"]) or needle in row["pinyin"])
        ]
        column = self.catalog_item_sort["column"]
        self.visible_catalog_item_rows.sort(
            key=lambda row: (row[column].casefold() if isinstance(row[column], str) else row[column], row["name"].casefold()),
            reverse=self.catalog_item_sort["descending"])
        for index, row in enumerate(self.visible_catalog_item_rows):
            self.catalog_items_tree.insert("", "end", iid=str(index), values=(row["name"], row["type"], row["id"]))

    def sort_catalog_items(self, column):
        if self.catalog_item_sort["column"] == column:
            self.catalog_item_sort["descending"] = not self.catalog_item_sort["descending"]
        else:
            self.catalog_item_sort = {"column": column, "descending": False}
        for key, title in self.catalog_heading_titles.items():
            marker = " ▼" if key == column and self.catalog_item_sort["descending"] else (" ▲" if key == column else "")
            self.catalog_items_tree.heading(key, text=title + marker, command=lambda c=key: self.sort_catalog_items(c))
        self.filter_catalog_items()

    def add_selected_catalog_items(self):
        if not self.doc or self.role_path is None:
            raise DataError("请先选择角色")
        selection = self.catalog_items_tree.selection()
        if not selection:
            raise DataError("请在右侧物品清单中选择一个或多个物品")
        added, skipped = [], []
        for item in selection:
            row = self.visible_catalog_item_rows[int(item)]
            try:
                add_item(self.doc, self.role_path, str(row["id"]), self.catalog_item_quantity.get(), self.catalog)
                added.append(row["name"])
            except DataError as exc:
                skipped.append(f"{row['name']}：{exc}")
        self.refresh_inventory()
        self.refresh_tree()
        self.update_status()
        self.status.set(f"已批量添加 {len(added)} 个物品；跳过 {len(skipped)} 个。导出前请检查修改预览")
        if skipped:
            messagebox.showinfo("批量添加完成", f"成功添加 {len(added)} 个，跳过 {len(skipped)} 个。\n\n" +
                                "\n".join(skipped[:12]), parent=self)

    def build_skill_package_tab(self):
        tab = ttk.Frame(self.book, padding=16)
        self.book.add(tab, text="技能包")
        self.skill_package_templates = skill_package_templates()
        self.runtime_roles = []
        self.runtime_source_skills = []
        self.skill_package = None

        heading = ttk.Frame(tab)
        heading.pack(fill="x")
        ttk.Label(heading, text="角色技能包 · 复制、离线编辑与流派模板", font=("Microsoft YaHei UI", 14, "bold")).pack(side="left")
        ttk.Button(heading, text="刷新游戏角色", command=lambda: self.guard(self.refresh_runtime_roles)).pack(side="right")
        ttk.Label(tab, text="先从来源角色读取功法，再选择模板筛选或手动多选；写入目标角色前会保留品级、词条和修炼数据。",
                  foreground="#5d6f86").pack(anchor="w", pady=(5, 12))

        selectors = ttk.LabelFrame(tab, text="来源与目标", padding=9)
        selectors.pack(fill="x")
        self.package_source_role = tk.StringVar()
        self.package_target_role = tk.StringVar()
        self.package_source_box = ttk.Combobox(selectors, textvariable=self.package_source_role, state="readonly", width=36)
        self.package_target_box = ttk.Combobox(selectors, textvariable=self.package_target_role, state="readonly", width=36)
        ttk.Label(selectors, text="人物 A（来源）").grid(row=0, column=0, sticky="w")
        self.package_source_box.grid(row=0, column=1, padx=7)
        ttk.Button(selectors, text="读取 A 的技能", command=lambda: self.guard(self.read_skill_package_source)).grid(row=0, column=2, padx=(0, 18))
        ttk.Label(selectors, text="人物 B（目标）").grid(row=0, column=3, sticky="w")
        self.package_target_box.grid(row=0, column=4, padx=7)

        template_bar = ttk.LabelFrame(tab, text="一键流派模板", padding=9)
        template_bar.pack(fill="x", pady=10)
        self.package_template = tk.StringVar(value=self.skill_package_templates[0]["name"])
        self.package_template_box = ttk.Combobox(template_bar, textvariable=self.package_template,
                                                  values=[row["name"] for row in self.skill_package_templates],
                                                  state="readonly", width=28)
        self.package_template_box.pack(side="left")
        self.package_template_box.bind("<<ComboboxSelected>>", lambda _event: self.show_skill_template())
        ttk.Button(template_bar, text="按模板选择来源技能", command=lambda: self.guard(self.apply_skill_template_filter)).pack(side="left", padx=7)
        self.package_template_note = tk.StringVar()
        ttk.Label(template_bar, textvariable=self.package_template_note, foreground="#375f88", wraplength=640).pack(side="left", padx=8)

        panes = ttk.Panedwindow(tab, orient="horizontal")
        panes.pack(fill="both", expand=True)
        left = ttk.LabelFrame(panes, text="来源角色功法 · 可多选", padding=7)
        right = ttk.LabelFrame(panes, text="技能包离线编辑", padding=7)
        panes.add(left, weight=3)
        panes.add(right, weight=2)
        self.package_skill_tree = ttk.Treeview(left, columns=("name", "type", "grade", "exp"), show="headings", selectmode="extended")
        for key, label, width in (("name", "名称", 210), ("type", "类型", 70), ("grade", "品级/境界", 95), ("exp", "修炼", 95)):
            self.package_skill_tree.heading(key, text=label)
            self.package_skill_tree.column(key, width=width, stretch=key == "name")
        self.package_skill_tree.pack(fill="both", expand=True)
        self.package_skill_tree.bind("<<TreeviewSelect>>", lambda _event: self.select_package_skill())

        self.package_name = tk.StringVar(value="我的技能包")
        self.package_grade = tk.StringVar()
        self.package_exp = tk.StringVar()
        self.package_raw = tk.StringVar()
        for row, (label, variable) in enumerate((("技能包名称", self.package_name), ("品级/境界", self.package_grade),
                                                 ("修炼经验", self.package_exp), ("原始词条数据", self.package_raw))):
            ttk.Label(right, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(right, textvariable=variable, width=48).grid(row=row, column=1, sticky="ew", padx=7, pady=4)
        right.columnconfigure(1, weight=1)
        ttk.Button(right, text="保存当前技能编辑", command=lambda: self.guard(self.save_package_skill_edit)).grid(row=4, column=1, sticky="e", pady=6)
        self.package_adapt_grade = tk.BooleanVar(value=True)
        self.package_sync_attributes = tk.BooleanVar(value=False)
        ttk.Checkbutton(right, text="按目标角色境界自动适配品级", variable=self.package_adapt_grade).grid(row=5, column=0, columnspan=2, sticky="w", pady=3)
        ttk.Checkbutton(right, text="同步补足功法所需资质与属性", variable=self.package_sync_attributes).grid(row=6, column=0, columnspan=2, sticky="w", pady=3)
        file_actions = ttk.Frame(right)
        file_actions.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(12, 5))
        ttk.Button(file_actions, text="保存技能包文件", command=lambda: self.guard(self.save_skill_package_file)).pack(side="left")
        ttk.Button(file_actions, text="载入技能包文件", command=lambda: self.guard(self.load_skill_package_file)).pack(side="left", padx=6)
        ttk.Button(right, text="一键复制所选技能到人物 B", command=lambda: self.guard(self.apply_skill_package_to_target)).grid(
            row=8, column=0, columnspan=2, sticky="ew", pady=8)
        self.show_skill_template()

    def selected_runtime_role(self, value):
        unit_id = self.value_id(value)
        return next((row for row in self.runtime_roles if str(row.get("unitId")) == str(unit_id)), None)

    def refresh_runtime_roles(self):
        self.live_send_as("getRuntimeRoles", {"offset": 0, "limit": 1000}, "skillPackageRoles")

    def read_skill_package_source(self):
        role = self.selected_runtime_role(self.package_source_role.get())
        if not role:
            raise DataError("请先刷新并选择人物 A")
        self.live_send_as("getRuntimeRoleData", {"unitId": role["unitId"]}, "skillPackageSource")

    def show_skill_template(self):
        template = next((row for row in self.skill_package_templates if row["name"] == self.package_template.get()), self.skill_package_templates[0])
        slots = "、".join(f"{slot}:{'/'.join(names)}" for slot, names, _required, _recommended in template["slots"])
        self.package_template_note.set(f"{template['summary']}  核心：{slots}")

    def apply_skill_template_filter(self):
        if not self.runtime_source_skills:
            raise DataError("请先读取人物 A 的技能")
        template = next(row for row in self.skill_package_templates if row["name"] == self.package_template.get())
        matched, missing = select_template_skills(template, self.runtime_source_skills)
        self.package_skill_tree.selection_remove(*self.package_skill_tree.selection())
        matched_ids = {id(row) for row in matched}
        for index, row in enumerate(self.runtime_source_skills):
            if id(row) in matched_ids:
                self.package_skill_tree.selection_add(str(index))
        self.status.set(f"模板“{template['name']}”已匹配 {len(matched)} 项；缺少 {len(missing)} 项")
        if missing:
            messagebox.showinfo("模板匹配结果", "未在人物 A 中找到：\n" + "\n".join(missing) +
                                "\n\n可更换来源角色，或手动补选相近功法。", parent=self)

    def fill_package_skills(self, skills):
        self.runtime_source_skills = list(skills or [])
        self.package_skill_tree.delete(*self.package_skill_tree.get_children())
        for index, skill in enumerate(self.runtime_source_skills):
            self.package_skill_tree.insert("", "end", iid=str(index), values=(skill.get("name"), skill.get("type"),
                                           skill.get("grade", skill.get("level")), skill.get("exp", 0)))

    def select_package_skill(self):
        selection = self.package_skill_tree.selection()
        if not selection:
            return
        skill = self.runtime_source_skills[int(selection[0])]
        raw = skill.get("rawValues") or []
        self.package_grade.set(str(skill.get("grade", raw[1] if len(raw) > 1 else 0)))
        self.package_exp.set(str(skill.get("exp", 0)))
        self.package_raw.set(",".join(str(value) for value in raw))

    def save_package_skill_edit(self):
        selection = self.package_skill_tree.selection()
        if len(selection) != 1:
            raise DataError("离线编辑时请只选择一项功法")
        try:
            grade, exp = int(self.package_grade.get()), int(self.package_exp.get())
            raw = [int(value.strip()) for value in self.package_raw.get().split(",") if value.strip()]
        except ValueError as exc:
            raise DataError("品级、修炼和词条原始数据必须是整数") from exc
        if not raw:
            raise DataError("原始词条数据不能为空")
        skill = self.runtime_source_skills[int(selection[0])]
        skill.update({"grade": grade, "exp": exp, "rawValues": raw})
        self.fill_package_skills(self.runtime_source_skills)
        self.status.set("已在工作台内更新技能包内容，尚未写入游戏")

    def current_skill_package(self):
        selection = self.package_skill_tree.selection()
        rows = [self.runtime_source_skills[int(item)] for item in selection] if selection else self.runtime_source_skills
        source = self.selected_runtime_role(self.package_source_role.get()) or {}
        template = next((row for row in self.skill_package_templates if row["name"] == self.package_template.get()), None)
        return build_package(self.package_name.get(), source, rows, template["id"] if template else None)

    def save_skill_package_file(self):
        package = self.current_skill_package()
        path = filedialog.asksaveasfilename(title="保存技能包", defaultextension=".json",
                                            filetypes=[("玄枢技能包", "*.json")], initialfile=package["name"] + ".json")
        if path:
            Path(path).write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
            self.status.set(f"技能包已保存：{path}")

    def load_skill_package_file(self):
        path = filedialog.askopenfilename(title="载入技能包", filetypes=[("玄枢技能包", "*.json"), ("全部文件", "*.*")])
        if not path:
            return
        package = json.loads(Path(path).read_text(encoding="utf-8"))
        if package.get("format") != "XuanShu.SkillPackage/1" or not isinstance(package.get("skills"), list):
            raise DataError("该文件不是受支持的玄枢技能包")
        self.skill_package = package
        self.package_name.set(package.get("name") or Path(path).stem)
        self.fill_package_skills(package["skills"])
        self.status.set(f"已载入技能包：{self.package_name.get()}")

    def apply_skill_package_to_target(self):
        target = self.selected_runtime_role(self.package_target_role.get())
        if not target:
            raise DataError("请先选择人物 B")
        package = self.current_skill_package()
        self.live_send_as("applySkillPackage", {"targetUnitId": target["unitId"], "skills": package["skills"],
                          "adaptGrade": self.package_adapt_grade.get(),
                          "syncAttributes": self.package_sync_attributes.get()}, "applySkillPackage")

    def build_credits_tab(self):
        tab = ttk.Frame(self.book, padding=24)
        self.book.add(tab, text="致谢")
        ttk.Label(tab, text="致谢与资料来源", font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w")
        text = tk.Text(tab, wrap="word", borderwidth=0, background="#eef2f6", font=("Microsoft YaHei UI", 10))
        text.pack(fill="both", expand=True, pady=(12, 0))
        text.insert("end", (
            "参考工具与源码\n\n"
            "• 大鬼编辑器 / 大鬼工具盒：参考旧版源码中的数据结构、交互范围和游戏调用思路。\n"
            "• F8 修改器：参考游戏内 Mod 的组织方式与部分操作流程。\n"
            "以上均仅作为兼容性研究与功能设计参考；玄枢使用独立界面、独立结构和独立通信实现，不代表原作者参与或授权。\n\n"
            "攻略与视频资料\n\n"
            "• TapTap 鬼谷八荒攻略作者：嘎嘎嘎嘎嘎、爱玩游戏的吐鲁番等。\n"
            "• Bilibili 视频与合集提供者：落锦墨（UID 263687361）及用户提供视频中列出的相关创作者。\n"
            "• 流派模板仅整理功法组合、词条优先级和适配规则，不转载视频或攻略正文。每个模板保留来源链接。\n\n"
            "项目组件\n\n"
            "• Python、Tk、Pillow、PyInstaller、Newtonsoft.Json，以及游戏官方 Mod 开发模板。\n\n"
            "若署名或链接需要修正，请提供准确名称；后续版本会及时补充。"
        ))
        text.configure(state="disabled")

    def build_live_tab(self):
        tab = ttk.Frame(self.book, padding=20)
        self.book.add(tab, text="实时连接")
        self.live_status = tk.StringVar(value="工作台服务端正在启动")
        ttk.Label(tab, text="游戏客户端连接", font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w")
        ttk.Label(tab, textvariable=self.live_status, foreground="#315c8c").pack(anchor="w", pady=(6, 14))
        actions = ttk.Frame(tab)
        actions.pack(fill="x")
        ttk.Button(actions, text="读取游戏状态", command=lambda: self.guard(lambda: self.live_send("getStatus"))).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="读取当前玩家", command=lambda: self.guard(lambda: self.live_send("getPlayer"))).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="引用修改：补满状态", command=lambda: self.guard(lambda: self.live_send("refillPlayer"))).pack(side="left")
        player = ttk.LabelFrame(tab, text="当前玩家 · 基础值用于修改，游戏显示值包含气运/功法/装备加成", padding=10)
        player.pack(fill="x", pady=(16, 0))
        self.live_player_name = tk.StringVar(value="尚未读取")
        ttk.Label(player, textvariable=self.live_player_name, font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", pady=(0, 6))
        self.live_attr_tree = ttk.Treeview(player, columns=("field", "base", "shown"), show="headings", height=4, selectmode="browse")
        for column, text, width in (("field", "属性", 170), ("base", "基础值（写入）", 150), ("shown", "游戏显示值", 150)):
            self.live_attr_tree.heading(column, text=text)
            self.live_attr_tree.column(column, width=width, anchor="center")
        self.live_attr_tree.pack(fill="x")
        self.live_attr_tree.bind("<<TreeviewSelect>>", self.select_live_attribute)
        editor = ttk.LabelFrame(tab, text="当前玩家基础属性 · 点击引用修改后才写入游戏", padding=12)
        editor.pack(fill="x", pady=12)
        self.live_field = tk.StringVar(value="attack")
        fields = ["hp", "hpMax", "mp", "mpMax", "sp", "spMax", "attack", "defense", "luck", "talent",
                  "health", "healthMax", "energy", "energyMax", "mood", "moodMax"]
        ttk.Label(editor, text="字段").grid(row=0, column=0, sticky="w")
        ttk.Combobox(editor, textvariable=self.live_field, values=fields, state="readonly", width=20).grid(row=0, column=1, padx=8)
        self.live_value = tk.StringVar()
        ttk.Label(editor, text="新值").grid(row=0, column=2, sticky="w", padx=(12, 0))
        ttk.Entry(editor, textvariable=self.live_value, width=22).grid(row=0, column=3, padx=8)
        ttk.Button(editor, text="引用修改", command=lambda: self.guard(self.live_apply_scalar)).grid(row=0, column=4, padx=8)
        profile = ttk.LabelFrame(tab, text="客户端上报的身份与世界数据 · 工作台服务端接收", padding=10)
        profile.pack(fill="x", pady=(0, 10))
        self.live_profile_tree = ttk.Treeview(profile, columns=("field", "value"), show="headings", height=5, selectmode="browse")
        self.live_profile_tree.heading("field", text="字段")
        self.live_profile_tree.heading("value", text="当前值")
        self.live_profile_tree.column("field", width=260)
        self.live_profile_tree.column("value", width=220)
        self.live_profile_tree.pack(side="left", fill="x", expand=True)
        self.live_profile_tree.bind("<<TreeviewSelect>>", self.select_live_profile)
        profile_edit = ttk.Frame(profile, padding=(10, 0, 0, 0))
        profile_edit.pack(side="right", fill="y")
        self.live_profile_field = tk.StringVar(value="inTrait")
        profile_fields = ["inTrait", "outTrait1", "outTrait2", "hobby1", "hobby2", "hobby3",
                          "intimacyToPlayer", "taoistId", "taoistState", "grade", "soul", "sex",
                          "direction", "isHero", "fishJade", "playerView"]
        ttk.Combobox(profile_edit, textvariable=self.live_profile_field, values=profile_fields,
                     state="readonly", width=22).pack(fill="x", pady=(0, 5))
        self.live_profile_value = tk.StringVar()
        ttk.Entry(profile_edit, textvariable=self.live_profile_value, width=24).pack(fill="x", pady=(0, 5))
        ttk.Button(profile_edit, text="引用修改身份/世界字段", command=lambda: self.guard(self.live_apply_profile)).pack(fill="x")
        self.live_output = tk.Text(tab, height=6, wrap="word", background="#f9fbfd", borderwidth=0)
        self.live_output.pack(fill="both", expand=True)
        self.live_output.insert("end", "等待 GGBH Bridge Mod 连接。测试 DLL 尚未自动安装到游戏目录。")
        self.live_output.configure(state="disabled")

    def live_send(self, command, payload=None):
        if not self.live.connected:
            raise DataError("游戏客户端尚未连接；请先安装测试 Mod 并启动游戏")
        request_id = self.live.request(command, payload)
        self.live_requests[request_id] = command
        self.live_status.set(f"已发送 {command}，等待游戏主线程处理")

    def live_send_as(self, command, payload, response_key):
        if not self.live.connected:
            raise DataError("游戏客户端尚未连接；请在游戏模组列表启用玄枢游戏桥后进入存档")
        request_id = self.live.request(command, payload)
        self.live_requests[request_id] = response_key
        self.live_status.set(f"已发送 {command}，等待游戏主线程处理")

    def live_apply_scalar(self):
        try:
            value = int(self.live_value.get())
        except ValueError as exc:
            raise DataError("实时属性值必须是整数") from exc
        if not -(2**31) <= value <= 2**31 - 1:
            raise DataError("实时属性值超出 32 位整数范围")
        self.live_send("setPlayerScalar", {"field": self.live_field.get(), "value": value})

    def live_apply_profile(self):
        try:
            value = int(self.live_profile_value.get())
        except ValueError as exc:
            raise DataError("实时身份值必须是整数") from exc
        if not -(2**31) <= value <= 2**31 - 1:
            raise DataError("实时身份值超出 32 位整数范围")
        self.live_send("setPlayerProfileField", {"field": self.live_profile_field.get(), "value": value})

    def select_live_attribute(self, _=None):
        selection = self.live_attr_tree.selection()
        if not selection:
            return
        field = selection[0]
        _label, base, _shown = self.live_attr_tree.item(field, "values")
        self.live_field.set(field)
        self.live_value.set(str(base))

    def select_live_profile(self, _=None):
        selection = self.live_profile_tree.selection()
        if not selection:
            return
        field = selection[0]
        _label, value = self.live_profile_tree.item(field, "values")
        self.live_profile_field.set(field)
        self.live_profile_value.set(str(value))

    def update_live_player(self, payload):
        attributes = payload.get("attributes") or {}
        shown = payload.get("shownAttributes") or attributes
        labels = {
            "hp": "体力", "hpMax": "体力上限", "mp": "灵力", "mpMax": "灵力上限",
            "sp": "念力", "spMax": "念力上限", "attack": "攻击", "defense": "防御",
            "luck": "幸运", "talent": "悟性", "health": "健康", "healthMax": "健康上限",
            "energy": "精力", "energyMax": "精力上限", "mood": "心情", "moodMax": "心情上限",
        }
        self.live_player_name.set(f"{payload.get('name') or '未命名角色'}  ·  {payload.get('unitId') or '无编号'}")
        self.live_attr_tree.delete(*self.live_attr_tree.get_children())
        for field, base in attributes.items():
            item = self.live_attr_tree.insert("", "end", iid=field, values=(f"{labels.get(field, field)} ({field})", base, shown.get(field, base)))
            self.live_attr_tree.item(item, tags=("odd" if len(self.live_attr_tree.get_children()) % 2 else "even",))
        self.live_attr_tree.tag_configure("odd", background="#f4f7fa")
        if self.live_field.get() in attributes:
            self.live_value.set(str(attributes[self.live_field.get()]))
        profile = payload.get("profile") or {}
        flat_profile = dict(profile)
        hobbies = flat_profile.pop("hobbies", []) or []
        for index, value in enumerate(hobbies[:3], 1):
            flat_profile[f"hobby{index}"] = value
        profile_labels = {
            "inTrait": "内在性格", "outTrait1": "外在性格一", "outTrait2": "外在性格二",
            "hobby1": "爱好一", "hobby2": "爱好二", "hobby3": "爱好三",
            "intimacyToPlayer": "对主角好感", "taoistId": "道心/道种 ID", "taoistState": "道心阶段",
            "grade": "境界 ID", "soul": "神魂 ID", "sex": "性别", "direction": "发展方向",
            "isHero": "是否天骄", "fishJade": "双鱼佩次数", "playerView": "视野/迷雾值",
        }
        self.live_profile_tree.delete(*self.live_profile_tree.get_children())
        for field, value in flat_profile.items():
            if isinstance(value, bool):
                value = 1 if value else 0
            self.live_profile_tree.insert("", "end", iid=field, values=(f"{profile_labels.get(field, field)} ({field})", value))
        if self.live_profile_field.get() in flat_profile:
            value = flat_profile[self.live_profile_field.get()]
            self.live_profile_value.set(str(1 if value is True else 0 if value is False else value))

    def poll_live(self):
        self.live_status.set(self.live.detail)
        for response in self.live.poll():
            command = self.live_requests.pop(response.get("requestId", ""), response.get("type", "响应"))
            self.live_output.configure(state="normal")
            if response.get("ok"):
                payload = response.get("payload") or {}
                if command == "getPlayer":
                    self.update_live_player(payload)
                if command == "skillPackageRoles":
                    self.runtime_roles = list(payload.get("roles") or [])
                    choices = [f"{row.get('name') or '未命名'} · {row.get('unitId')}" for row in self.runtime_roles]
                    self.package_source_box.configure(values=choices)
                    self.package_target_box.configure(values=choices)
                    if choices and not self.package_source_role.get():
                        self.package_source_role.set(choices[0])
                    if choices and not self.package_target_role.get():
                        self.package_target_role.set(choices[0])
                    self.status.set(f"已从游戏读取 {len(choices)} 名角色，可选择人物 A 与人物 B")
                if command == "skillPackageSource":
                    role = payload.get("role") or {}
                    self.fill_package_skills(payload.get("skills") or [])
                    self.package_name.set(f"{role.get('name') or '角色'}的技能包")
                    self.status.set(f"已读取 {role.get('name') or '人物 A'} 的 {len(self.runtime_source_skills)} 项功法")
                if command == "applySkillPackage":
                    results = payload.get("results") or []
                    success = sum(1 for row in results if row.get("ok"))
                    failed = len(results) - success
                    self.status.set(f"技能包写入完成：成功 {success} 项，失败 {failed} 项")
                    messagebox.showinfo("技能包写入结果", f"已处理 {len(results)} 项功法。\n成功：{success}\n失败：{failed}\n\n请在游戏内确认并保存。", parent=self)
                if command == "forcePotmonConver":
                    self.status.set("壶妖已在游戏内强制化形；请保存游戏后重新读取最新存档")
                    messagebox.showinfo("强制化形完成",
                                        f"游戏原生化形流程已完成。\nNPC 编号：{payload.get('unitId') or '等待游戏生成'}\n\n"
                                        "请在游戏内保存，然后点击工作台的“读取最新存档”。", parent=self)
                self.live_output.insert("end", f"\n\n[{command}] 成功\n{json.dumps(payload, ensure_ascii=False, indent=2)}")
                if command in ("setPlayerScalar", "setPlayerProfileField", "refillPlayer"):
                    self.live_send("getPlayer")
            else:
                self.live_output.insert("end", f"\n\n[{command}] 失败：{response.get('errorCode')} · {response.get('message')}")
            self.live_output.see("end")
            self.live_output.configure(state="disabled")
        if self.winfo_exists():
            self.live_after = self.after(250, self.poll_live)

    def build_diagnostics_tab(self):
        tab = ttk.Frame(self.book, padding=20)
        self.book.add(tab, text="游戏与连接检测")
        ttk.Label(tab, text="检测当前 GGBH Bridge、实时连接和 ModExportData；不安装组件、不发送修改指令。", wraplength=1000).pack(anchor="w", pady=(0, 14))
        row = ttk.Frame(tab)
        row.pack(fill="x")
        self.game_path = tk.StringVar(value=str(DEFAULT_GAME))
        ttk.Entry(row, textvariable=self.game_path).pack(side="left", fill="x", expand=True, padx=(0, 10))
        ttk.Button(row, text="选择目录", command=lambda: self.guard(self.choose_game)).pack(side="left")
        ttk.Button(row, text="开始检测", command=lambda: self.guard(self.diagnose)).pack(side="left", padx=8)
        self.diagnostic_text = tk.Text(tab, wrap="word", font=("Microsoft YaHei UI", 11), borderwidth=0, background="#f9fbfd")
        self.diagnostic_text.pack(fill="both", expand=True, pady=16)
        self.diagnostic_text.insert("end", "点击开始检测。\n\n当前方案使用 Mods/GGBH.BridgeMod.dll 与工作台命名管道通信，不依赖旧版 HTScript.dll。")
        self.diagnostic_text.configure(state="disabled")

    def choose_game(self):
        path = filedialog.askdirectory(initialdir=self.game_path.get())
        if path:
            self.game_path.set(path)

    def diagnose(self):
        status = installation_status(self.game_path.get())
        lines = [f"{'已找到' if found else '未找到'}  {label}" for label, found in status.items()]
        lines += ["", f"实时通信：{'游戏客户端已连接' if self.live.connected else '尚未连接'}",
                  f"连接详情：{self.live.detail}",
                  "通信方案：GGBH.Workbench.v1 本机命名管道；指令在游戏主线程执行。"]
        mods = discover_mods(self.game_path.get())
        lines += ["", f"自动识别到 {len(mods)} 个 ModExportData 目录："]
        for mod in mods[:80]:
            marker = "  [参考修改器]" if mod["name"] in ("F8修改器", "大鬼工具盒》修改器！") else ""
            lines.append(f"- {mod['name']}（{mod['files']} 个文件）{marker}")
        if len(mods) > 80:
            lines.append(f"……其余 {len(mods) - 80} 个未展开")
        lines += ["", "说明：文件齐全只表示桥接客户端具备加载条件；页面功能仍以实机读写结果为准。"]
        self.diagnostic_text.configure(state="normal")
        self.diagnostic_text.delete("1.0", "end")
        self.diagnostic_text.insert("end", "\n".join(lines))
        self.diagnostic_text.configure(state="disabled")

    def preview(self):
        if not self.doc:
            raise DataError("请先打开文件")
        self.flush_form()
        self.update_status()
        window = tk.Toplevel(self)
        window.title("修改预览 · 已暂存字段")
        window.geometry("900x550")
        text = tk.Text(window, wrap="word", font=("Microsoft YaHei UI", 10))
        text.pack(fill="both", expand=True, padx=16, pady=16)
        documents = [("人物缓存", self.doc), ("世界缓存 / 壶妖", self.world_doc),
                     ("宗门建筑缓存", self.school_doc)]
        for label, document in documents:
            if not document or not document.change_count:
                continue
            text.insert("end", f"===== {label} =====\n\n")
            for path, (old, new) in document.changes.items():
                text.insert("end", f"{pointer(path)}\n  原值：{json.dumps(old, ensure_ascii=False)}\n  新值：{json.dumps(new, ensure_ascii=False)}\n\n")
            for operation, path, index, item in document.structural_changes:
                actions = {"append": "新增列表项", "dict_add": "新增对象字段",
                           "list_remove": "删除列表项", "dict_remove": "删除对象字段"}
                action = actions.get(operation, operation)
                text.insert("end", f"{pointer(path + (index,))}\n  操作：{action}\n  内容：{json.dumps(item, ensure_ascii=False)}\n\n")
        if not self.total_change_count():
            text.insert("end", "暂无已暂存修改。输入后需点击“暂存修改”才会进入导出数据。")
        text.configure(state="disabled")

    def reset(self):
        if self.doc and self.confirm_discard():
            self.doc.reset()
            if self.world_doc:
                self.world_doc.reset()
            if self.school_doc:
                self.school_doc.reset()
            self.role_path = None
            self.clear_form()
            self.refresh_inventory()
            self.refresh_potmon_tab()
            self.refresh_inspectors()
            self.refresh_tree()
            self.update_status()

    def export(self):
        if not self.doc:
            raise DataError("请先打开文件")
        self.flush_form()
        suffix = ".cache" if self.doc.kind == "legacy-cache" else ".json"
        destination = filedialog.asksaveasfilename(initialfile=self.doc.source.stem + ".edited" + suffix,
                                                  defaultextension=suffix,
                                                  filetypes=[("原始格式", "*" + suffix)])
        if destination:
            self.loading = True
            self.busy_message = "正在导出并备份数据，请等待完成"
            self.status.set(self.busy_message)
            document = self.doc
            world_document = self.world_doc
            school_document = self.school_doc
            def worker():
                try:
                    outputs = [(destination, document.export(destination))]
                    if world_document and world_document.change_count:
                        requested = Path(destination)
                        world_destination = requested.with_name(world_document.source.stem + ".edited" + requested.suffix)
                        outputs.append((str(world_destination), world_document.export(world_destination)))
                    if school_document and school_document.change_count:
                        requested = Path(destination)
                        school_destination = requested.with_name(school_document.source.stem + ".edited" + requested.suffix)
                        outputs.append((str(school_destination), school_document.export(school_destination)))
                    self.export_results.put((outputs, None))
                except Exception as exc:
                    self.export_results.put((None, exc))
            threading.Thread(target=worker, daemon=True).start()
            self.after(80, self.finish_export)

    def finish_export(self):
        try:
            outputs, error = self.export_results.get_nowait()
        except queue.Empty:
            self.after(80, self.finish_export)
            return
        self.loading = False
        if error:
            messagebox.showerror("导出失败", str(error), parent=self)
            self.update_status()
            return
        lines = []
        for destination, backup in outputs:
            lines.append(f"输出：{destination}\n原始备份：{backup}")
        messagebox.showinfo("副本已导出", "\n\n".join(lines) + "\n\n已验证数据编解码，尚未验证游戏内回读。", parent=self)
        self.status.set(f"已导出 {self.total_change_count()} 处暂存修改；原文件保持不变")

    def total_change_count(self):
        return ((self.doc.change_count if self.doc else 0) +
                (self.world_doc.change_count if self.world_doc else 0) +
                (self.school_doc.change_count if self.school_doc else 0))

    def update_status(self):
        self.status.set(f"已暂存 {self.total_change_count()} 处修改 · 点击修改预览核对后导出副本" if self.doc else "就绪")


def run():
    Editor().mainloop()
