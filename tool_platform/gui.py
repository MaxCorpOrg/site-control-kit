from __future__ import annotations

import argparse
import json
import traceback

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except ModuleNotFoundError as exc:  # pragma: no cover - depends on system packages
    tk = None
    messagebox = None
    ttk = None
    TKINTER_IMPORT_ERROR = exc
else:  # pragma: no cover - trivial branch
    TKINTER_IMPORT_ERROR = None

from .catalog import DEFAULT_REGISTRY_PATH, ToolManifest, find_action, load_catalog
from .cli import execute_action


if tk is not None:

    class ToolPlatformPanel(tk.Tk):
        def __init__(self, registry_path: str) -> None:
            super().__init__()
            self.registry_path = registry_path
            self.catalog = load_catalog(registry_path)
            self._tool_ids: list[str] = []
            self.title(self.catalog.platform_name)
            self.geometry("1180x760")
            self.minsize(960, 640)
            self.summary_var = tk.StringVar()
            self.tool_list = tk.Listbox(self, exportselection=False)
            self.action_list = tk.Listbox(self, exportselection=False)
            self.details = None
            self._build_ui()
            self._reload_catalog(initial=True)

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
            ttk.Button(header, text="Reload", command=self._reload_catalog).pack(side=tk.RIGHT)

            body = ttk.Panedwindow(outer, orient="horizontal")
            body.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

            left_frame = ttk.Frame(body, padding=8)
            body.add(left_frame, weight=1)
            ttk.Label(left_frame, text="Registered Tools").pack(anchor="w")
            self.tool_list.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
            self.tool_list.bind("<<ListboxSelect>>", self._on_tool_select)

            right_frame = ttk.Frame(body, padding=8)
            body.add(right_frame, weight=3)

            details_frame = ttk.Frame(right_frame)
            details_frame.pack(fill=tk.BOTH, expand=True)
            ttk.Label(details_frame, text="Tool Details").pack(anchor="w")
            self.details = ttk.Treeview(
                details_frame,
                columns=("value",),
                show="tree headings",
                selectmode="browse",
                height=20,
            )
            self.details.heading("#0", text="Field")
            self.details.heading("value", text="Value")
            self.details.column("#0", width=220, stretch=False)
            self.details.column("value", width=720, stretch=True)
            self.details.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

            actions_frame = ttk.Frame(right_frame)
            actions_frame.pack(fill=tk.BOTH, expand=False, pady=(12, 0))
            ttk.Label(actions_frame, text="Actions").pack(anchor="w")
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

        def _reload_catalog(self, initial: bool = False) -> None:
            try:
                self.catalog = load_catalog(self.registry_path)
            except Exception as exc:  # pragma: no cover - GUI fallback
                messagebox.showerror("Tool Platform", f"Failed to load catalog:\n{exc}")
                if initial:
                    raise
                return
            self.summary_var.set(
                f"{self.catalog.platform_name}: {len(self.catalog.tools)} registered tools"
            )
            self._tool_ids = [tool.tool_id for tool in self.catalog.tools]
            self.tool_list.delete(0, tk.END)
            for tool in self.catalog.tools:
                standalone = "standalone" if tool.standalone else "embedded"
                self.tool_list.insert(tk.END, f"{tool.display_name} [{standalone}]")
            self.action_list.delete(0, tk.END)
            self._clear_details()
            if self.catalog.tools:
                self.tool_list.selection_set(0)
                self._show_tool(self.catalog.tools[0])

        def _clear_details(self) -> None:
            if self.details is None:
                return
            for item in self.details.get_children():
                self.details.delete(item)

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

        def _show_tool(self, tool: ToolManifest) -> None:
            self._clear_details()
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
                    self.details.insert("", tk.END, text=key, values=(value,))
            if tool.docs:
                parent = self.details.insert("", tk.END, text="docs", values=("",))
                for doc in tool.docs:
                    self.details.insert(parent, tk.END, text=doc.label, values=(str(doc.path),))
            if tool.artifacts:
                parent = self.details.insert("", tk.END, text="artifacts", values=("",))
                for key, value in tool.artifacts.items():
                    self.details.insert(parent, tk.END, text=key, values=(value,))
            self.action_list.delete(0, tk.END)
            for action in tool.actions:
                self.action_list.insert(tk.END, f"{action.label} [{action.action_id}]")

        def _on_tool_select(self, _event: object) -> None:
            tool = self._selected_tool()
            if tool is not None:
                self._show_tool(tool)

        def _on_action_select(self, _event: object) -> None:
            return

        def _run_action(self, dry_run: bool = False) -> None:
            tool = self._selected_tool()
            action_id = self._selected_action_id()
            if tool is None or action_id is None:
                messagebox.showinfo("Tool Platform", "Select a tool action first.")
                return
            action = find_action(tool, action_id)
            try:
                result = execute_action(action, dry_run=dry_run)
            except Exception as exc:  # pragma: no cover - GUI fallback
                messagebox.showerror(
                    "Tool Platform",
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
        description="Open the unified graphical control panel for registered tools.",
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
