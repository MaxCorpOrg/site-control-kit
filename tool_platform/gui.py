from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path
from typing import Any

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ModuleNotFoundError as exc:  # pragma: no cover - depends on system packages
    tk = None
    filedialog = None
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


if tk is not None:

    class ToolPlatformPanel(tk.Tk):
        def __init__(self, registry_path: str) -> None:
            super().__init__()
            self.registry_path = registry_path
            self.catalog = load_catalog(registry_path)
            self.title(self.catalog.platform_name)
            self.geometry("1360x860")
            self.minsize(1120, 720)
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
            self.profile_combo = None
            self.profile_details = None
            self.tool_list = tk.Listbox(self, exportselection=False)
            self.action_list = tk.Listbox(self, exportselection=False)
            self.workflow_details = None
            self._build_ui()
            self._reload_catalog(initial=True)
            self._reload_profiles(initial=True)

        def _build_ui(self) -> None:
            outer = ttk.Frame(self, padding=12)
            outer.pack(fill=tk.BOTH, expand=True)

            header = ttk.Frame(outer)
            header.pack(fill="x")
            ttk.Label(
                header,
                textvariable=self.summary_var,
                font=("Sans", 12, "bold"),
            ).pack(side=tk.LEFT, fill="x", expand=True)
            ttk.Button(header, text="Reload Workflows", command=self._reload_catalog).pack(
                side=tk.RIGHT
            )
            ttk.Button(header, text="Reload Profiles", command=self._reload_profiles).pack(
                side=tk.RIGHT,
                padx=(0, 8),
            )

            body = ttk.Panedwindow(outer, orient="horizontal")
            body.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

            left_frame = ttk.Frame(body, padding=8)
            body.add(left_frame, weight=3)
            self._build_profile_ui(left_frame)

            right_frame = ttk.Frame(body, padding=8)
            body.add(right_frame, weight=2)
            self._build_workflow_ui(right_frame)

        def _build_profile_ui(self, parent: ttk.Frame) -> None:
            ttk.Label(parent, text="Telegram Profiles").pack(anchor="w")

            root_frame = ttk.Frame(parent)
            root_frame.pack(fill="x", pady=(8, 0))
            ttk.Label(root_frame, text="Profiles Root").pack(side=tk.LEFT)
            ttk.Entry(root_frame, textvariable=self.output_root_var).pack(
                side=tk.LEFT,
                fill="x",
                expand=True,
                padx=(8, 8),
            )
            ttk.Button(root_frame, text="Reload", command=self._reload_profiles).pack(side=tk.RIGHT)

            select_frame = ttk.Frame(parent)
            select_frame.pack(fill="x", pady=(12, 0))
            ttk.Label(select_frame, text="Current User").pack(side=tk.LEFT)
            self.profile_combo = ttk.Combobox(
                select_frame,
                textvariable=self.profile_choice_var,
                state="readonly",
            )
            self.profile_combo.pack(side=tk.LEFT, fill="x", expand=True, padx=(8, 8))
            self.profile_combo.bind("<<ComboboxSelected>>", self._on_profile_select)
            ttk.Button(
                select_frame,
                text="Refresh Status",
                command=self._refresh_selected_profile_status,
            ).pack(side=tk.RIGHT)
            ttk.Button(
                select_frame,
                text="Launch",
                command=self._launch_selected_profile,
            ).pack(side=tk.RIGHT, padx=(0, 8))

            details_frame = ttk.Frame(parent)
            details_frame.pack(fill=tk.BOTH, expand=True, pady=(12, 0))
            ttk.Label(details_frame, text="Profile Details").pack(anchor="w")
            self.profile_details = ttk.Treeview(
                details_frame,
                columns=("value",),
                show="tree headings",
                selectmode="browse",
                height=16,
            )
            self.profile_details.heading("#0", text="Field")
            self.profile_details.heading("value", text="Value")
            self.profile_details.column("#0", width=220, stretch=False)
            self.profile_details.column("value", width=720, stretch=True)
            self.profile_details.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

            import_frame = ttk.Labelframe(parent, text="Add New User By tdata", padding=10)
            import_frame.pack(fill="x", pady=(12, 0))
            self._build_import_form(import_frame)

            adopt_frame = ttk.Labelframe(parent, text="Register Existing Portable Folder", padding=10)
            adopt_frame.pack(fill="x", pady=(12, 0))
            self._build_adopt_form(adopt_frame)

        def _build_workflow_ui(self, parent: ttk.Frame) -> None:
            ttk.Label(parent, text="Telegram Workflows").pack(anchor="w")
            self.tool_list.pack(in_=parent, fill=tk.BOTH, expand=False, pady=(8, 0))
            self.tool_list.bind("<<ListboxSelect>>", self._on_tool_select)

            details_frame = ttk.Frame(parent)
            details_frame.pack(fill=tk.BOTH, expand=True, pady=(12, 0))
            ttk.Label(details_frame, text="Workflow Details").pack(anchor="w")
            self.workflow_details = ttk.Treeview(
                details_frame,
                columns=("value",),
                show="tree headings",
                selectmode="browse",
                height=16,
            )
            self.workflow_details.heading("#0", text="Field")
            self.workflow_details.heading("value", text="Value")
            self.workflow_details.column("#0", width=220, stretch=False)
            self.workflow_details.column("value", width=520, stretch=True)
            self.workflow_details.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

            actions_frame = ttk.Frame(parent)
            actions_frame.pack(fill=tk.BOTH, expand=False, pady=(12, 0))
            ttk.Label(actions_frame, text="Workflow Actions").pack(anchor="w")
            action_body = ttk.Frame(actions_frame)
            action_body.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
            self.action_list.pack(
                in_=action_body,
                side=tk.LEFT,
                fill=tk.BOTH,
                expand=True,
            )
            self.action_list.bind("<<ListboxSelect>>", self._on_action_select)
            action_buttons = ttk.Frame(action_body)
            action_buttons.pack(side=tk.RIGHT, fill=tk.Y, padx=(12, 0))
            ttk.Button(action_buttons, text="Run Action", command=self._run_action).pack(
                fill="x"
            )
            ttk.Button(
                action_buttons,
                text="Preview Action",
                command=lambda: self._run_action(dry_run=True),
            ).pack(fill="x", pady=(8, 0))

        def _build_import_form(self, parent: ttk.Labelframe) -> None:
            zip_row = ttk.Frame(parent)
            zip_row.pack(fill="x")
            ttk.Label(zip_row, text="tdata Zip").pack(side=tk.LEFT)
            ttk.Entry(zip_row, textvariable=self.import_zip_var).pack(
                side=tk.LEFT,
                fill="x",
                expand=True,
                padx=(8, 8),
            )
            ttk.Button(zip_row, text="Browse", command=self._choose_import_zip).pack(side=tk.RIGHT)

            name_row = ttk.Frame(parent)
            name_row.pack(fill="x", pady=(8, 0))
            ttk.Label(name_row, text="Profile Name").pack(side=tk.LEFT)
            ttk.Entry(name_row, textvariable=self.import_profile_name_var).pack(
                side=tk.LEFT,
                fill="x",
                expand=True,
                padx=(8, 0),
            )

            username_row = ttk.Frame(parent)
            username_row.pack(fill="x", pady=(8, 0))
            ttk.Label(username_row, text="Account Username").pack(side=tk.LEFT)
            ttk.Entry(username_row, textvariable=self.import_account_username_var).pack(
                side=tk.LEFT,
                fill="x",
                expand=True,
                padx=(8, 0),
            )

            label_row = ttk.Frame(parent)
            label_row.pack(fill="x", pady=(8, 0))
            ttk.Label(label_row, text="Account Label").pack(side=tk.LEFT)
            ttk.Entry(label_row, textvariable=self.import_account_label_var).pack(
                side=tk.LEFT,
                fill="x",
                expand=True,
                padx=(8, 0),
            )

            button_row = ttk.Frame(parent)
            button_row.pack(fill="x", pady=(10, 0))
            ttk.Button(button_row, text="Import And Launch", command=self._import_profile).pack(
                side=tk.RIGHT
            )

        def _build_adopt_form(self, parent: ttk.Labelframe) -> None:
            dir_row = ttk.Frame(parent)
            dir_row.pack(fill="x")
            ttk.Label(dir_row, text="Profile Dir").pack(side=tk.LEFT)
            ttk.Entry(dir_row, textvariable=self.adopt_profile_dir_var).pack(
                side=tk.LEFT,
                fill="x",
                expand=True,
                padx=(8, 8),
            )
            ttk.Button(dir_row, text="Browse", command=self._choose_adopt_dir).pack(side=tk.RIGHT)

            name_row = ttk.Frame(parent)
            name_row.pack(fill="x", pady=(8, 0))
            ttk.Label(name_row, text="Profile Name").pack(side=tk.LEFT)
            ttk.Entry(name_row, textvariable=self.adopt_profile_name_var).pack(
                side=tk.LEFT,
                fill="x",
                expand=True,
                padx=(8, 0),
            )

            username_row = ttk.Frame(parent)
            username_row.pack(fill="x", pady=(8, 0))
            ttk.Label(username_row, text="Account Username").pack(side=tk.LEFT)
            ttk.Entry(username_row, textvariable=self.adopt_account_username_var).pack(
                side=tk.LEFT,
                fill="x",
                expand=True,
                padx=(8, 0),
            )

            label_row = ttk.Frame(parent)
            label_row.pack(fill="x", pady=(8, 0))
            ttk.Label(label_row, text="Account Label").pack(side=tk.LEFT)
            ttk.Entry(label_row, textvariable=self.adopt_account_label_var).pack(
                side=tk.LEFT,
                fill="x",
                expand=True,
                padx=(8, 0),
            )

            button_row = ttk.Frame(parent)
            button_row.pack(fill="x", pady=(10, 0))
            ttk.Button(button_row, text="Adopt Profile", command=self._adopt_profile).pack(
                side=tk.RIGHT
            )

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
            for tool in self.catalog.tools:
                self.tool_list.insert(tk.END, tool.display_name)
            self.action_list.delete(0, tk.END)
            self._clear_workflow_details()
            if self.catalog.tools:
                self.tool_list.selection_set(0)
                self._show_tool(self.catalog.tools[0])
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
            self.profile_choice_var.set("")
            self._clear_profile_details()
            if not self._profiles:
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
                f"{self.catalog.platform_name}: "
                f"{len(self.catalog.tools)} workflows, "
                f"{len(self._profiles)} profiles under {self.output_root_var.get()}"
            )

        def _clear_profile_details(self) -> None:
            if self.profile_details is None:
                return
            for item in self.profile_details.get_children():
                self.profile_details.delete(item)

        def _clear_workflow_details(self) -> None:
            if self.workflow_details is None:
                return
            for item in self.workflow_details.get_children():
                self.workflow_details.delete(item)

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
            self._clear_profile_details()
            account = profile.get("account") if isinstance(profile.get("account"), dict) else {}
            windows = profile.get("windows") if isinstance(profile.get("windows"), list) else []
            first_window = windows[0] if windows else {}
            rows = [
                ("profile_name", str(profile.get("profile_name") or "")),
                ("account_username", str(account.get("username") or "")),
                ("account_label", str(account.get("label") or "")),
                ("running", "yes" if profile.get("running") else "no"),
                ("profile_dir", str(profile.get("profile_dir") or "")),
                ("tdata_dir", str(profile.get("tdata_dir") or "")),
                ("window_title", str(first_window.get("title") or "")),
                ("window_id", str(first_window.get("window_id") or "")),
                ("pid_count", str(len(profile.get("pids") or []))),
            ]
            for key, value in rows:
                if value:
                    self.profile_details.insert("", tk.END, text=key, values=(value,))

        def _show_tool(self, tool: ToolManifest) -> None:
            self._clear_workflow_details()
            rows = [
                ("tool_id", tool.tool_id),
                ("display_name", tool.display_name),
                ("kind", tool.kind),
                ("standalone", str(tool.standalone).lower()),
                ("source", tool.source_label),
                ("root_dir", str(tool.root_dir)),
                ("manifest", str(tool.manifest_path)),
                ("description", tool.description),
                ("capabilities", ", ".join(tool.capabilities)),
                ("tags", ", ".join(tool.tags)),
            ]
            for key, value in rows:
                if value:
                    self.workflow_details.insert("", tk.END, text=key, values=(value,))
            if tool.docs:
                parent = self.workflow_details.insert("", tk.END, text="docs", values=("",))
                for doc in tool.docs:
                    self.workflow_details.insert(
                        parent,
                        tk.END,
                        text=doc.label,
                        values=(str(doc.path),),
                    )
            if tool.artifacts:
                parent = self.workflow_details.insert("", tk.END, text="artifacts", values=("",))
                for key, value in tool.artifacts.items():
                    self.workflow_details.insert(parent, tk.END, text=key, values=(value,))
            self.action_list.delete(0, tk.END)
            for action in tool.actions:
                self.action_list.insert(tk.END, f"{action.label} [{action.action_id}]")

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
