from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path
from typing import Any

try:
    import tkinter as tk
    from tkinter import filedialog, font as tkfont, messagebox, ttk
except ModuleNotFoundError as exc:  # pragma: no cover - depends on system packages
    tk = None
    filedialog = None
    tkfont = None
    messagebox = None
    ttk = None
    TKINTER_IMPORT_ERROR = exc
else:  # pragma: no cover - trivial branch
    TKINTER_IMPORT_ERROR = None

from .catalog import DEFAULT_REGISTRY_PATH, ToolManifest, find_action, load_catalog
from .cli import execute_action
from .telegram_profiles import (
    DEFAULT_OUTPUT_ROOT,
    adopt_existing_profile,
    format_profile_label,
    get_profile_status,
    import_tdata_profile,
    launch_profile,
    list_portable_profiles,
)


def format_profile_details(profile: dict[str, Any]) -> str:
    account = profile.get("account") if isinstance(profile.get("account"), dict) else {}
    windows = profile.get("windows") if isinstance(profile.get("windows"), list) else []
    first_window = windows[0] if windows else {}
    running_text = "running" if profile.get("running") else "stopped"
    lines = [
        "Profile Overview",
        f"Name: {profile.get('profile_name') or 'unknown'}",
        f"Account username: {account.get('username') or 'not set'}",
        f"Account label: {account.get('label') or 'not set'}",
        f"Runtime state: {running_text}",
        f"PID count: {len(profile.get('pids') or [])}",
        "",
        "Paths",
        f"Profile dir: {profile.get('profile_dir') or '-'}",
        f"tdata dir: {profile.get('tdata_dir') or '-'}",
        f"Metadata path: {profile.get('metadata_path') or '-'}",
        f"Telegram log: {profile.get('telegram_log_path') or '-'}",
        "",
        "Window",
        f"Window title: {first_window.get('title') or 'not available'}",
        f"Window id: {first_window.get('window_id') or 'not available'}",
    ]
    return "\n".join(lines)


def format_workflow_details(tool: ToolManifest) -> str:
    lines = [
        "Workflow Overview",
        f"Display name: {tool.display_name}",
        f"Tool id: {tool.tool_id}",
        f"Kind: {tool.kind}",
        f"Source: {tool.source_label}",
        f"Standalone: {'yes' if tool.standalone else 'no'}",
        f"Root dir: {tool.root_dir}",
        f"Manifest: {tool.manifest_path}",
    ]
    if tool.description:
        lines.extend(["", "Description", tool.description])
    if tool.capabilities:
        lines.extend(["", "Capabilities", *[f"- {item}" for item in tool.capabilities]])
    if tool.tags:
        lines.extend(["", "Tags", *[f"- {item}" for item in tool.tags]])
    if tool.docs:
        lines.extend(["", "Docs", *[f"- {doc.label}: {doc.path}" for doc in tool.docs]])
    if tool.artifacts:
        lines.extend(
            ["", "Artifacts", *[f"- {key}: {value}" for key, value in tool.artifacts.items()]]
        )
    return "\n".join(lines)


if tk is not None:

    class ToolPlatformPanel(tk.Tk):
        def __init__(self, registry_path: str) -> None:
            super().__init__()
            self.registry_path = registry_path
            self.catalog = load_catalog(registry_path)
            self._colors = {
                "bg": "#f3efe7",
                "surface": "#fffaf2",
                "surface_alt": "#f7f1e7",
                "field": "#fffdf8",
                "border": "#d9cfbf",
                "text": "#182126",
                "muted": "#5f6b73",
                "accent": "#176b87",
                "accent_active": "#12546a",
                "accent_text": "#ffffff",
                "selection": "#dfeef5",
            }
            self._fonts: dict[str, Any] = {}
            self._configure_styles()

            self.title(self.catalog.platform_name)
            self.geometry("1460x980")
            self.minsize(1200, 780)

            self.summary_var = tk.StringVar()
            self.output_root_var = tk.StringVar(value=str(DEFAULT_OUTPUT_ROOT))
            self.profile_choice_var = tk.StringVar()
            self.import_zip_var = tk.StringVar()
            self.import_profile_name_var = tk.StringVar()
            self.import_account_username_var = tk.StringVar()
            self.import_account_label_var = tk.StringVar()
            self.adopt_profile_dir_var = tk.StringVar()
            self.adopt_profile_name_var = tk.StringVar()
            self.adopt_account_username_var = tk.StringVar()
            self.adopt_account_label_var = tk.StringVar()

            self._profiles: list[dict[str, Any]] = []
            self._tool_ids: list[str] = []

            self.profile_combo: ttk.Combobox | None = None
            self.profile_details: tk.Text | None = None
            self.workflow_details: tk.Text | None = None

            self.tool_list = self._create_listbox(self, height=6)
            self.action_list = self._create_listbox(self, height=6)

            self._build_ui()
            self._reload_catalog(initial=True)
            self._reload_profiles(initial=True)

        def _configure_styles(self) -> None:
            if ttk is None or tkfont is None:
                return
            style = ttk.Style(self)
            try:
                style.theme_use("clam")
            except tk.TclError:
                pass

            base_font = tkfont.nametofont("TkDefaultFont").copy()
            base_font.configure(size=11)
            label_font = base_font.copy()
            label_font.configure(weight="bold")
            section_font = base_font.copy()
            section_font.configure(size=12, weight="bold")
            hero_font = base_font.copy()
            hero_font.configure(size=20, weight="bold")
            small_font = base_font.copy()
            small_font.configure(size=10)
            mono_font = tkfont.Font(self, family="Noto Sans Mono", size=10)
            self._fonts = {
                "base": base_font,
                "label": label_font,
                "section": section_font,
                "hero": hero_font,
                "small": small_font,
                "mono": mono_font,
            }

            self.configure(bg=self._colors["bg"])
            self.option_add("*tearOff", False)

            style.configure(".", background=self._colors["bg"], foreground=self._colors["text"])
            style.configure("App.TFrame", background=self._colors["bg"])
            style.configure("Card.TFrame", background=self._colors["surface"])
            style.configure(
                "HeroTitle.TLabel",
                background=self._colors["bg"],
                foreground=self._colors["text"],
                font=self._fonts["hero"],
            )
            style.configure(
                "HeroSub.TLabel",
                background=self._colors["bg"],
                foreground=self._colors["muted"],
                font=self._fonts["small"],
            )
            style.configure(
                "CardTitle.TLabel",
                background=self._colors["surface"],
                foreground=self._colors["text"],
                font=self._fonts["section"],
            )
            style.configure(
                "CardSubtitle.TLabel",
                background=self._colors["surface"],
                foreground=self._colors["muted"],
                font=self._fonts["small"],
            )
            style.configure(
                "Surface.TLabel",
                background=self._colors["surface"],
                foreground=self._colors["text"],
                font=self._fonts["base"],
            )
            style.configure(
                "Field.TLabel",
                background=self._colors["surface"],
                foreground=self._colors["muted"],
                font=self._fonts["small"],
            )
            style.configure(
                "TEntry",
                fieldbackground=self._colors["field"],
                foreground=self._colors["text"],
                padding=(10, 8),
                bordercolor=self._colors["border"],
                lightcolor=self._colors["border"],
                darkcolor=self._colors["border"],
            )
            style.configure(
                "TCombobox",
                fieldbackground=self._colors["field"],
                foreground=self._colors["text"],
                padding=(8, 6),
                bordercolor=self._colors["border"],
                lightcolor=self._colors["border"],
                darkcolor=self._colors["border"],
                arrowsize=16,
            )
            style.map(
                "TCombobox",
                fieldbackground=[("readonly", self._colors["field"])],
                selectbackground=[("readonly", self._colors["field"])],
                selectforeground=[("readonly", self._colors["text"])],
            )
            style.configure(
                "TButton",
                font=self._fonts["base"],
                padding=(12, 8),
                background=self._colors["surface_alt"],
                foreground=self._colors["text"],
                bordercolor=self._colors["border"],
                lightcolor=self._colors["border"],
                darkcolor=self._colors["border"],
            )
            style.map(
                "TButton",
                background=[("active", self._colors["field"])],
            )
            style.configure(
                "Accent.TButton",
                font=self._fonts["label"],
                padding=(14, 9),
                background=self._colors["accent"],
                foreground=self._colors["accent_text"],
                bordercolor=self._colors["accent"],
                lightcolor=self._colors["accent"],
                darkcolor=self._colors["accent"],
            )
            style.map(
                "Accent.TButton",
                background=[("active", self._colors["accent_active"])],
                foreground=[("active", self._colors["accent_text"])],
            )
            style.configure("TNotebook", background=self._colors["surface"], borderwidth=0)
            style.configure(
                "TNotebook.Tab",
                background=self._colors["surface_alt"],
                foreground=self._colors["muted"],
                font=self._fonts["base"],
                padding=(14, 8),
            )
            style.map(
                "TNotebook.Tab",
                background=[
                    ("selected", self._colors["field"]),
                    ("active", self._colors["field"]),
                ],
                foreground=[
                    ("selected", self._colors["text"]),
                    ("active", self._colors["text"]),
                ],
            )

        def _create_listbox(self, parent: tk.Widget, height: int) -> tk.Listbox:
            return tk.Listbox(
                parent,
                activestyle="none",
                bg=self._colors["field"],
                fg=self._colors["text"],
                selectbackground=self._colors["accent"],
                selectforeground=self._colors["accent_text"],
                highlightbackground=self._colors["border"],
                highlightcolor=self._colors["accent"],
                highlightthickness=1,
                borderwidth=0,
                relief="flat",
                font=self._fonts["base"],
                exportselection=False,
                height=height,
            )

        def _create_readonly_text(self, parent: ttk.Frame, *, height: int) -> tk.Text:
            widget = tk.Text(
                parent,
                wrap="word",
                height=height,
                bg=self._colors["field"],
                fg=self._colors["text"],
                insertbackground=self._colors["text"],
                highlightbackground=self._colors["border"],
                highlightcolor=self._colors["accent"],
                highlightthickness=1,
                relief="flat",
                borderwidth=0,
                padx=14,
                pady=12,
                spacing1=2,
                spacing3=4,
                font=self._fonts["base"],
            )
            widget.configure(state="disabled", cursor="arrow")
            return widget

        def _set_readonly_text(self, widget: tk.Text | None, content: str) -> None:
            if widget is None:
                return
            widget.configure(state="normal")
            widget.delete("1.0", tk.END)
            widget.insert("1.0", content.strip() + "\n")
            widget.configure(state="disabled")

        def _create_card(self, parent: ttk.Frame, title: str, subtitle: str) -> ttk.Frame:
            card = ttk.Frame(parent, style="Card.TFrame", padding=16)
            card.pack(fill="both", expand=False, pady=(0, 14))
            ttk.Label(card, text=title, style="CardTitle.TLabel").pack(anchor="w")
            if subtitle:
                ttk.Label(card, text=subtitle, style="CardSubtitle.TLabel").pack(
                    anchor="w", pady=(4, 12)
                )
            body = ttk.Frame(card, style="Card.TFrame")
            body.pack(fill="both", expand=True)
            return body

        def _build_ui(self) -> None:
            outer = ttk.Frame(self, style="App.TFrame", padding=20)
            outer.pack(fill=tk.BOTH, expand=True)

            header = ttk.Frame(outer, style="App.TFrame")
            header.pack(fill="x")

            hero = ttk.Frame(header, style="App.TFrame")
            hero.pack(side=tk.LEFT, fill="x", expand=True)
            ttk.Label(hero, text=self.catalog.platform_name, style="HeroTitle.TLabel").pack(
                anchor="w"
            )
            ttk.Label(hero, textvariable=self.summary_var, style="HeroSub.TLabel").pack(
                anchor="w", pady=(4, 0)
            )

            header_actions = ttk.Frame(header, style="App.TFrame")
            header_actions.pack(side=tk.RIGHT, anchor="ne")
            ttk.Button(
                header_actions,
                text="Refresh Profiles",
                command=self._reload_profiles,
            ).pack(side=tk.LEFT)
            ttk.Button(
                header_actions,
                text="Refresh Workflows",
                command=self._reload_catalog,
            ).pack(side=tk.LEFT, padx=(10, 0))

            ttk.Separator(outer, orient="horizontal").pack(fill="x", pady=(16, 18))

            content = ttk.Frame(outer, style="App.TFrame")
            content.pack(fill=tk.BOTH, expand=True)
            content.columnconfigure(0, weight=7)
            content.columnconfigure(1, weight=5)
            content.rowconfigure(0, weight=1)

            left_frame = ttk.Frame(content, style="App.TFrame")
            left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
            right_frame = ttk.Frame(content, style="App.TFrame")
            right_frame.grid(row=0, column=1, sticky="nsew")

            self._build_profile_ui(left_frame)
            self._build_workflow_ui(right_frame)

        def _build_profile_ui(self, parent: ttk.Frame) -> None:
            profile_body = self._create_card(
                parent,
                "Portable Profiles",
                "Choose the active Telegram Desktop user, then refresh status or launch the profile.",
            )
            profile_body.columnconfigure(1, weight=1)

            ttk.Label(profile_body, text="Profiles root", style="Field.TLabel").grid(
                row=0, column=0, sticky="w"
            )
            ttk.Entry(profile_body, textvariable=self.output_root_var).grid(
                row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0)
            )
            ttk.Button(
                profile_body,
                text="Reload",
                command=self._reload_profiles,
            ).grid(row=1, column=2, sticky="ew", padx=(10, 0))

            ttk.Label(profile_body, text="Current user", style="Field.TLabel").grid(
                row=2, column=0, sticky="w", pady=(14, 0)
            )
            self.profile_combo = ttk.Combobox(
                profile_body,
                textvariable=self.profile_choice_var,
                state="readonly",
            )
            self.profile_combo.grid(
                row=3,
                column=0,
                columnspan=2,
                sticky="ew",
                pady=(4, 0),
            )
            self.profile_combo.bind("<<ComboboxSelected>>", self._on_profile_select)
            ttk.Button(
                profile_body,
                text="Launch",
                style="Accent.TButton",
                command=self._launch_selected_profile,
            ).grid(row=3, column=2, sticky="ew", padx=(10, 0))
            ttk.Button(
                profile_body,
                text="Refresh Status",
                command=self._refresh_selected_profile_status,
            ).grid(row=3, column=3, sticky="ew", padx=(10, 0))

            ttk.Label(profile_body, text="Profile details", style="Field.TLabel").grid(
                row=4, column=0, sticky="w", pady=(16, 0)
            )
            self.profile_details = self._create_readonly_text(profile_body, height=12)
            self.profile_details.grid(
                row=5,
                column=0,
                columnspan=4,
                sticky="nsew",
                pady=(6, 0),
            )
            profile_body.rowconfigure(5, weight=1)

            intake_body = self._create_card(
                parent,
                "Profile Intake",
                "Bring in a new user by tdata archive or register a folder that already exists on disk.",
            )
            notebook = ttk.Notebook(intake_body)
            notebook.pack(fill="both", expand=True)

            import_tab = ttk.Frame(notebook, style="Card.TFrame", padding=12)
            adopt_tab = ttk.Frame(notebook, style="Card.TFrame", padding=12)
            notebook.add(import_tab, text="Import tdata")
            notebook.add(adopt_tab, text="Adopt Folder")
            self._build_import_form(import_tab)
            self._build_adopt_form(adopt_tab)

        def _build_workflow_ui(self, parent: ttk.Frame) -> None:
            workflows_body = self._create_card(
                parent,
                "Telegram Workflows",
                "Keep the tools separate, inspect what each one does, and preview an action before you run it.",
            )
            self.tool_list.pack(in_=workflows_body, fill=tk.X, expand=False)
            self.tool_list.bind("<<ListboxSelect>>", self._on_tool_select)

            details_body = self._create_card(
                parent,
                "Selected Workflow",
                "Manifest details are rendered as readable text so long paths and descriptions stay visible.",
            )
            self.workflow_details = self._create_readonly_text(details_body, height=18)
            self.workflow_details.pack(fill="both", expand=True)

            actions_body = self._create_card(
                parent,
                "Workflow Actions",
                "Preview first for safe commands, then run the exact workflow action you need.",
            )
            action_layout = ttk.Frame(actions_body, style="Card.TFrame")
            action_layout.pack(fill="both", expand=True)
            self.action_list.pack(in_=action_layout, side=tk.LEFT, fill=tk.BOTH, expand=True)
            self.action_list.bind("<<ListboxSelect>>", self._on_action_select)
            action_buttons = ttk.Frame(action_layout, style="Card.TFrame")
            action_buttons.pack(side=tk.RIGHT, fill=tk.Y, padx=(12, 0))
            ttk.Button(
                action_buttons,
                text="Run Action",
                style="Accent.TButton",
                command=self._run_action,
            ).pack(fill="x")
            ttk.Button(
                action_buttons,
                text="Preview Action",
                command=lambda: self._run_action(dry_run=True),
            ).pack(fill="x", pady=(10, 0))

        def _build_import_form(self, parent: ttk.Frame) -> None:
            parent.columnconfigure(0, weight=1)

            ttk.Label(parent, text="tdata zip", style="Field.TLabel").grid(
                row=0, column=0, sticky="w"
            )
            zip_row = ttk.Frame(parent, style="Card.TFrame")
            zip_row.grid(row=1, column=0, sticky="ew", pady=(4, 10))
            zip_row.columnconfigure(0, weight=1)
            ttk.Entry(zip_row, textvariable=self.import_zip_var).grid(row=0, column=0, sticky="ew")
            ttk.Button(zip_row, text="Browse", command=self._choose_import_zip).grid(
                row=0, column=1, padx=(10, 0)
            )

            ttk.Label(parent, text="Profile name", style="Field.TLabel").grid(
                row=2, column=0, sticky="w"
            )
            ttk.Entry(parent, textvariable=self.import_profile_name_var).grid(
                row=3, column=0, sticky="ew", pady=(4, 10)
            )

            ttk.Label(parent, text="Account username", style="Field.TLabel").grid(
                row=4, column=0, sticky="w"
            )
            ttk.Entry(parent, textvariable=self.import_account_username_var).grid(
                row=5, column=0, sticky="ew", pady=(4, 10)
            )

            ttk.Label(parent, text="Account label", style="Field.TLabel").grid(
                row=6, column=0, sticky="w"
            )
            ttk.Entry(parent, textvariable=self.import_account_label_var).grid(
                row=7, column=0, sticky="ew", pady=(4, 14)
            )

            ttk.Button(
                parent,
                text="Import and Launch",
                style="Accent.TButton",
                command=self._import_profile,
            ).grid(row=8, column=0, sticky="e")

        def _build_adopt_form(self, parent: ttk.Frame) -> None:
            parent.columnconfigure(0, weight=1)

            ttk.Label(parent, text="Portable profile folder", style="Field.TLabel").grid(
                row=0, column=0, sticky="w"
            )
            dir_row = ttk.Frame(parent, style="Card.TFrame")
            dir_row.grid(row=1, column=0, sticky="ew", pady=(4, 10))
            dir_row.columnconfigure(0, weight=1)
            ttk.Entry(dir_row, textvariable=self.adopt_profile_dir_var).grid(
                row=0, column=0, sticky="ew"
            )
            ttk.Button(dir_row, text="Browse", command=self._choose_adopt_dir).grid(
                row=0, column=1, padx=(10, 0)
            )

            ttk.Label(parent, text="Profile name", style="Field.TLabel").grid(
                row=2, column=0, sticky="w"
            )
            ttk.Entry(parent, textvariable=self.adopt_profile_name_var).grid(
                row=3, column=0, sticky="ew", pady=(4, 10)
            )

            ttk.Label(parent, text="Account username", style="Field.TLabel").grid(
                row=4, column=0, sticky="w"
            )
            ttk.Entry(parent, textvariable=self.adopt_account_username_var).grid(
                row=5, column=0, sticky="ew", pady=(4, 10)
            )

            ttk.Label(parent, text="Account label", style="Field.TLabel").grid(
                row=6, column=0, sticky="w"
            )
            ttk.Entry(parent, textvariable=self.adopt_account_label_var).grid(
                row=7, column=0, sticky="ew", pady=(4, 14)
            )

            ttk.Button(
                parent,
                text="Adopt Profile",
                style="Accent.TButton",
                command=self._adopt_profile,
            ).grid(row=8, column=0, sticky="e")

        def _reload_catalog(self, initial: bool = False) -> None:
            try:
                self.catalog = load_catalog(self.registry_path)
            except Exception as exc:  # pragma: no cover - GUI fallback
                messagebox.showerror("Telegram Control Center", f"Failed to load workflows:\n{exc}")
                if initial:
                    raise
                return
            self._tool_ids = [tool.tool_id for tool in self.catalog.tools]
            self.tool_list.delete(0, tk.END)
            self.action_list.delete(0, tk.END)
            for tool in self.catalog.tools:
                self.tool_list.insert(tk.END, tool.display_name)
            if self.catalog.tools:
                self.tool_list.selection_clear(0, tk.END)
                self.tool_list.selection_set(0)
                self.tool_list.activate(0)
                self._show_tool(self.catalog.tools[0])
            else:
                self._set_readonly_text(self.workflow_details, "No workflows are registered.")
            self._refresh_summary()

        def _reload_profiles(
            self,
            initial: bool = False,
            preferred_profile_dir: str | None = None,
        ) -> None:
            try:
                self._profiles = list_portable_profiles(self.output_root_var.get())
            except Exception as exc:  # pragma: no cover - GUI fallback
                messagebox.showerror("Telegram Control Center", f"Failed to load profiles:\n{exc}")
                if initial:
                    raise
                return

            labels = [format_profile_label(profile) for profile in self._profiles]
            if self.profile_combo is not None:
                self.profile_combo["values"] = labels

            if not self._profiles:
                self.profile_choice_var.set("")
                self._set_readonly_text(
                    self.profile_details,
                    "No Telegram portable profiles were found under the selected root.",
                )
                self._refresh_summary()
                return

            index = 0
            if preferred_profile_dir:
                for candidate_index, profile in enumerate(self._profiles):
                    if str(profile.get("profile_dir")) == str(preferred_profile_dir):
                        index = candidate_index
                        break
            if self.profile_combo is not None:
                self.profile_combo.current(index)
            self._show_profile(self._profiles[index])
            self._refresh_summary()

        def _refresh_summary(self) -> None:
            self.summary_var.set(
                f"{len(self.catalog.tools)} workflows available · "
                f"{len(self._profiles)} portable profiles found under {self.output_root_var.get()}"
            )

        def _selected_profile(self) -> dict[str, Any] | None:
            if self.profile_combo is None:
                return None
            index = self.profile_combo.current()
            if index < 0 or index >= len(self._profiles):
                return None
            return self._profiles[index]

        def _selected_tool(self) -> ToolManifest | None:
            selection = self.tool_list.curselection()
            if not selection:
                return None
            return self.catalog.tools[selection[0]]

        def _selected_action_id(self) -> str | None:
            selection = self.action_list.curselection()
            tool = self._selected_tool()
            if tool is None or not selection:
                return None
            return tool.actions[selection[0]].action_id

        def _show_profile(self, profile: dict[str, Any]) -> None:
            self._set_readonly_text(self.profile_details, format_profile_details(profile))

        def _show_tool(self, tool: ToolManifest) -> None:
            self._set_readonly_text(self.workflow_details, format_workflow_details(tool))
            self.action_list.delete(0, tk.END)
            for action in tool.actions:
                self.action_list.insert(tk.END, action.label)
            if tool.actions:
                self.action_list.selection_clear(0, tk.END)
                self.action_list.selection_set(0)
                self.action_list.activate(0)

        def _on_profile_select(self, _event: object) -> None:
            profile = self._selected_profile()
            if profile is not None:
                self._show_profile(profile)

        def _on_tool_select(self, _event: object) -> None:
            tool = self._selected_tool()
            if tool is not None:
                self._show_tool(tool)

        def _on_action_select(self, _event: object) -> None:
            return

        def _choose_import_zip(self) -> None:
            if filedialog is None:  # pragma: no cover - depends on tkinter extras
                return
            selected = filedialog.askopenfilename(
                title="Select tdata zip",
                filetypes=[("Zip archives", "*.zip"), ("All files", "*")],
            )
            if selected:
                self.import_zip_var.set(selected)
                if not self.import_profile_name_var.get().strip():
                    self.import_profile_name_var.set(Path(selected).stem)

        def _choose_adopt_dir(self) -> None:
            if filedialog is None:  # pragma: no cover - depends on tkinter extras
                return
            selected = filedialog.askdirectory(title="Select existing Telegram portable folder")
            if selected:
                self.adopt_profile_dir_var.set(selected)
                if not self.adopt_profile_name_var.get().strip():
                    self.adopt_profile_name_var.set(Path(selected).name)

        def _refresh_selected_profile_status(self) -> None:
            profile = self._selected_profile()
            if profile is None:
                messagebox.showinfo("Telegram Control Center", "Select a Telegram profile first.")
                return
            try:
                fresh = get_profile_status(str(profile.get("profile_dir") or ""))
            except Exception as exc:  # pragma: no cover - GUI fallback
                messagebox.showerror("Telegram Control Center", f"Status refresh failed:\n{exc}")
                return
            index = self.profile_combo.current() if self.profile_combo is not None else -1
            if 0 <= index < len(self._profiles):
                self._profiles[index] = fresh
            self._show_profile(fresh)
            self._refresh_summary()
            messagebox.showinfo(
                "Telegram Profile Status",
                json.dumps(fresh, ensure_ascii=False, indent=2),
            )

        def _launch_selected_profile(self) -> None:
            profile = self._selected_profile()
            if profile is None:
                messagebox.showinfo("Telegram Control Center", "Select a Telegram profile first.")
                return
            try:
                result = launch_profile(str(profile.get("profile_dir") or ""))
            except Exception as exc:  # pragma: no cover - GUI fallback
                messagebox.showerror("Telegram Control Center", f"Launch failed:\n{exc}")
                return
            self._reload_profiles(preferred_profile_dir=str(profile.get("profile_dir") or ""))
            messagebox.showinfo(
                "Launch Result",
                json.dumps(result, ensure_ascii=False, indent=2),
            )

        def _import_profile(self) -> None:
            zip_path = self.import_zip_var.get().strip()
            if not zip_path:
                messagebox.showinfo("Telegram Control Center", "Select a tdata zip first.")
                return
            try:
                result = import_tdata_profile(
                    zip_path=zip_path,
                    output_root=self.output_root_var.get(),
                    profile_name=self.import_profile_name_var.get(),
                    account_username=self.import_account_username_var.get(),
                    account_label=self.import_account_label_var.get(),
                    launch=True,
                )
            except Exception as exc:  # pragma: no cover - GUI fallback
                messagebox.showerror("Telegram Control Center", f"Import failed:\n{exc}")
                return
            self._reload_profiles(preferred_profile_dir=str(result.get("profile_dir") or ""))
            messagebox.showinfo(
                "Import Result",
                json.dumps(result, ensure_ascii=False, indent=2),
            )

        def _adopt_profile(self) -> None:
            profile_dir = self.adopt_profile_dir_var.get().strip()
            if not profile_dir:
                messagebox.showinfo(
                    "Telegram Control Center",
                    "Select an existing Telegram portable folder first.",
                )
                return
            try:
                result = adopt_existing_profile(
                    profile_dir=profile_dir,
                    profile_name=self.adopt_profile_name_var.get(),
                    account_username=self.adopt_account_username_var.get(),
                    account_label=self.adopt_account_label_var.get(),
                )
            except Exception as exc:  # pragma: no cover - GUI fallback
                messagebox.showerror("Telegram Control Center", f"Adopt failed:\n{exc}")
                return
            self._reload_profiles(preferred_profile_dir=str(result.get("profile_dir") or ""))
            messagebox.showinfo(
                "Adopt Result",
                json.dumps(result, ensure_ascii=False, indent=2),
            )

        def _run_action(self, dry_run: bool = False) -> None:
            tool = self._selected_tool()
            action_id = self._selected_action_id()
            if tool is None or action_id is None:
                messagebox.showinfo("Telegram Control Center", "Select a workflow action first.")
                return
            action = find_action(tool, action_id)
            try:
                result = execute_action(action, dry_run=dry_run)
            except Exception as exc:  # pragma: no cover - GUI fallback
                messagebox.showerror(
                    "Telegram Control Center",
                    f"Action failed:\n{exc}\n\n{traceback.format_exc()}",
                )
                return
            messagebox.showinfo(
                f"Action: {action.label}",
                json.dumps(result, ensure_ascii=False, indent=2),
            )

else:

    class ToolPlatformPanel:
        def __init__(self, _registry_path: str) -> None:
            raise RuntimeError(
                "tkinter is not installed in this environment; the graphical "
                "tool platform panel cannot be launched here."
            ) from TKINTER_IMPORT_ERROR


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tool-platform-panel",
        description="Open the Telegram graphical control panel for profiles and workflows.",
    )
    parser.add_argument(
        "--registry",
        default=str(DEFAULT_REGISTRY_PATH),
        help="Path to tool registry JSON.",
    )
    args = parser.parse_args(argv)
    if tk is None:
        parser.exit(
            1,
            "tkinter is not installed in this environment; "
            "the graphical control panel is unavailable.\n",
        )
    panel = ToolPlatformPanel(args.registry)
    panel.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
