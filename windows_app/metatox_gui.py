"""MetaTox Windows GUI launcher."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from metatox_runner import (
    MetaToxOptions,
    check_environment,
    get_application_dir,
    open_path,
    resolve_metatox_root,
    resolve_output_directory,
    run_pipeline,
    summarize_outputs,
)


BIOTRANS_OPTIONS = [
    ("allHuman", "All human biotransformations"),
    ("ecbased", "EC-based metabolism"),
    ("cyp450", "CYP450 metabolism"),
    ("phaseII", "Phase II conjugation"),
    ("hgut", "Human gut microbial"),
    ("superbio", "Superbio ordered steps"),
    ("envimicro", "Environmental microbial"),
]

GLORYX_OPTIONS = [
    ("phase_1_and_2", "Phase 1 and phase 2"),
    ("phase_1", "Phase 1 only"),
    ("phase_2", "Phase 2 only"),
]


class MetaToxApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("MetaTox")
        self.geometry("920x760")
        self.minsize(820, 680)

        self._cancel_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._last_output_dir: Path | None = None

        self.input_file = tk.StringVar()
        self.output_dir = tk.StringVar(value="Results_Prediction")
        self.metatox_root = tk.StringVar(value=str(resolve_metatox_root()))
        self.biotrans_type = tk.StringVar(value="allHuman")
        self.nstep = tk.StringVar(value="1")
        self.cmode = tk.StringVar(value="3")
        self.phase1 = tk.StringVar(value="1")
        self.phase2 = tk.StringVar(value="1")
        self.phase_gloryx = tk.StringVar(value="phase_1_and_2")
        self.predictor_activate = tk.BooleanVar(value=False)
        self.keep_tmp = tk.BooleanVar(value=False)
        self.status_text = tk.StringVar(value="Ready")

        self._build_ui()
        self.after(200, self.refresh_environment_status)

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        header = ttk.Label(
            container,
            text="MetaTox — metabolite prediction",
            font=("Segoe UI", 16, "bold"),
        )
        header.pack(anchor=tk.W)

        subtitle = ttk.Label(
            container,
            text="Windows GUI for BioTransformer3, SygMa, GLORYx, MetaTrans, and optional Meta-Predictor.",
        )
        subtitle.pack(anchor=tk.W, pady=(0, 12))

        notebook = ttk.Notebook(container)
        notebook.pack(fill=tk.BOTH, expand=True)

        run_tab = ttk.Frame(notebook, padding=12)
        options_tab = ttk.Frame(notebook, padding=12)
        environment_tab = ttk.Frame(notebook, padding=12)
        notebook.add(run_tab, text="Run")
        notebook.add(options_tab, text="Options")
        notebook.add(environment_tab, text="Environment")

        self._build_run_tab(run_tab)
        self._build_options_tab(options_tab)
        self._build_environment_tab(environment_tab)

        status_bar = ttk.Label(container, textvariable=self.status_text, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, pady=(12, 0))

    def _build_run_tab(self, parent: ttk.Frame) -> None:
        files_frame = ttk.LabelFrame(parent, text="Input and output", padding=10)
        files_frame.pack(fill=tk.X)

        self._add_path_row(files_frame, "Input file", self.input_file, self._browse_input)
        self._add_path_row(files_frame, "Output folder name", self.output_dir, None, is_directory_name=True)
        self._add_path_row(files_frame, "MetaTox folder", self.metatox_root, self._browse_metatox_root)

        helper = ttk.Label(
            files_frame,
            text="Input format: one molecule per line as MoleculeName,SMILES",
        )
        helper.pack(anchor=tk.W, pady=(8, 0))

        actions = ttk.Frame(parent)
        actions.pack(fill=tk.X, pady=12)

        self.run_button = ttk.Button(actions, text="Run prediction", command=self.start_run)
        self.run_button.pack(side=tk.LEFT)

        self.cancel_button = ttk.Button(actions, text="Cancel", command=self.cancel_run, state=tk.DISABLED)
        self.cancel_button.pack(side=tk.LEFT, padx=(8, 0))

        self.open_output_button = ttk.Button(
            actions,
            text="Open output folder",
            command=self.open_output_folder,
            state=tk.DISABLED,
        )
        self.open_output_button.pack(side=tk.LEFT, padx=(8, 0))

        log_frame = ttk.LabelFrame(parent, text="Log", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_widget = scrolledtext.ScrolledText(log_frame, height=20, wrap=tk.WORD, state=tk.DISABLED)
        self.log_widget.pack(fill=tk.BOTH, expand=True)

    def _build_options_tab(self, parent: ttk.Frame) -> None:
        biotrans_frame = ttk.LabelFrame(parent, text="BioTransformer3", padding=10)
        biotrans_frame.pack(fill=tk.X)

        ttk.Label(biotrans_frame, text="Model").grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        biotrans_combo = ttk.Combobox(
            biotrans_frame,
            textvariable=self.biotrans_type,
            values=[value for value, _ in BIOTRANS_OPTIONS],
            state="readonly",
            width=24,
        )
        biotrans_combo.grid(row=0, column=1, sticky=tk.W, pady=4)
        ttk.Label(biotrans_frame, text="Description").grid(row=1, column=0, sticky=tk.NW, padx=(0, 8), pady=4)
        self.biotrans_description = ttk.Label(biotrans_frame, wraplength=620, justify=tk.LEFT)
        self.biotrans_description.grid(row=1, column=1, sticky=tk.W, pady=4)
        biotrans_combo.bind("<<ComboboxSelected>>", self._update_biotrans_description)
        self._update_biotrans_description()

        ttk.Label(biotrans_frame, text="Prediction steps").grid(row=2, column=0, sticky=tk.W, pady=4)
        ttk.Entry(biotrans_frame, textvariable=self.nstep, width=8).grid(row=2, column=1, sticky=tk.W, pady=4)
        ttk.Label(biotrans_frame, text="CYP450 mode (1-3)").grid(row=3, column=0, sticky=tk.W, pady=4)
        ttk.Entry(biotrans_frame, textvariable=self.cmode, width=8).grid(row=3, column=1, sticky=tk.W, pady=4)

        sygma_frame = ttk.LabelFrame(parent, text="SygMa", padding=10)
        sygma_frame.pack(fill=tk.X, pady=(12, 0))
        ttk.Label(sygma_frame, text="Phase 1 cycles").grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Entry(sygma_frame, textvariable=self.phase1, width=8).grid(row=0, column=1, sticky=tk.W, pady=4)
        ttk.Label(sygma_frame, text="Phase 2 cycles").grid(row=1, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Entry(sygma_frame, textvariable=self.phase2, width=8).grid(row=1, column=1, sticky=tk.W, pady=4)

        gloryx_frame = ttk.LabelFrame(parent, text="GLORYx", padding=10)
        gloryx_frame.pack(fill=tk.X, pady=(12, 0))
        ttk.Label(gloryx_frame, text="Metabolism phase").grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Combobox(
            gloryx_frame,
            textvariable=self.phase_gloryx,
            values=[value for value, _ in GLORYX_OPTIONS],
            state="readonly",
            width=24,
        ).grid(row=0, column=1, sticky=tk.W, pady=4)

        extra_frame = ttk.LabelFrame(parent, text="Additional options", padding=10)
        extra_frame.pack(fill=tk.X, pady=(12, 0))
        ttk.Checkbutton(
            extra_frame,
            text="Enable Meta-Predictor (requires CUDA setup inside WSL)",
            variable=self.predictor_activate,
        ).pack(anchor=tk.W)
        ttk.Checkbutton(
            extra_frame,
            text="Keep intermediate files in tmp/",
            variable=self.keep_tmp,
        ).pack(anchor=tk.W, pady=(6, 0))

    def _build_environment_tab(self, parent: ttk.Frame) -> None:
        intro = ttk.Label(
            parent,
            text=(
                "MetaTox uses Singularity containers and therefore runs inside WSL2 on Windows. "
                "Install WSL2, Singularity, and the optional Meta-Predictor conda environment in Linux."
            ),
            wraplength=820,
            justify=tk.LEFT,
        )
        intro.pack(anchor=tk.W)

        button_row = ttk.Frame(parent)
        button_row.pack(fill=tk.X, pady=12)
        ttk.Button(button_row, text="Refresh checks", command=self.refresh_environment_status).pack(side=tk.LEFT)
        ttk.Button(
            button_row,
            text="Open setup guide",
            command=self.open_setup_guide,
        ).pack(side=tk.LEFT, padx=(8, 0))

        self.environment_widget = scrolledtext.ScrolledText(parent, height=24, wrap=tk.WORD, state=tk.DISABLED)
        self.environment_widget.pack(fill=tk.BOTH, expand=True)

    def _add_path_row(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.StringVar,
        browse_command,
        is_directory_name: bool = False,
    ) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text=label, width=18).pack(side=tk.LEFT)
        entry = ttk.Entry(row, textvariable=variable)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        if browse_command:
            ttk.Button(row, text="Browse", command=browse_command).pack(side=tk.LEFT)
        elif not is_directory_name:
            ttk.Button(row, text="Browse", state=tk.DISABLED).pack(side=tk.LEFT)

    def _browse_input(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select input file",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialdir=str(get_application_dir()),
        )
        if selected:
            self.input_file.set(selected)

    def _browse_metatox_root(self) -> None:
        selected = filedialog.askdirectory(
            title="Select MetaTox installation folder",
            initialdir=str(get_application_dir()),
        )
        if selected:
            self.metatox_root.set(selected)
            self.refresh_environment_status()

    def _update_biotrans_description(self, *_args) -> None:
        descriptions = {value: label for value, label in BIOTRANS_OPTIONS}
        self.biotrans_description.configure(text=descriptions.get(self.biotrans_type.get(), ""))

    def append_log(self, message: str) -> None:
        self.log_widget.configure(state=tk.NORMAL)
        self.log_widget.insert(tk.END, message + "\n")
        self.log_widget.see(tk.END)
        self.log_widget.configure(state=tk.DISABLED)

    def clear_log(self) -> None:
        self.log_widget.configure(state=tk.NORMAL)
        self.log_widget.delete("1.0", tk.END)
        self.log_widget.configure(state=tk.DISABLED)

    def refresh_environment_status(self) -> None:
        status = check_environment(self.metatox_root.get() or None)
        lines = [
            "Environment checks",
            "==================",
            f"WSL available: {'Yes' if status.wsl_available else 'No'}",
            f"WSL distribution: {status.wsl_distro or 'Not detected'}",
            f"Singularity in WSL: {'Yes' if status.singularity_available else 'No'}",
            f"MetaTox root: {status.metatox_root}",
            f"Metatox.sh found: {'Yes' if status.metatox_script_found else 'No'}",
            "",
        ]
        if status.notes:
            lines.append("Notes:")
            lines.extend(f"- {note}" for note in status.notes)
            lines.append("")
        if status.issues:
            lines.append("Issues:")
            lines.extend(f"- {issue}" for issue in status.issues)
        else:
            lines.append("All required checks passed.")

        self.environment_widget.configure(state=tk.NORMAL)
        self.environment_widget.delete("1.0", tk.END)
        self.environment_widget.insert(tk.END, "\n".join(lines))
        self.environment_widget.configure(state=tk.DISABLED)

        if status.issues:
            self.status_text.set("Environment setup incomplete")
        else:
            self.status_text.set("Ready")

    def open_setup_guide(self) -> None:
        guide = Path(__file__).resolve().parent / "README_WINDOWS.md"
        if guide.is_file():
            open_path(guide)
        else:
            messagebox.showinfo(
                "Setup guide",
                "See windows_app/README_WINDOWS.md in the MetaTox repository for setup instructions.",
            )

    def _collect_options(self) -> MetaToxOptions:
        if not self.input_file.get().strip():
            raise ValueError("Select an input file before running MetaTox.")
        return MetaToxOptions(
            input_file=self.input_file.get().strip(),
            outdir=self.output_dir.get().strip() or "Results_Prediction",
            biotrans_type=self.biotrans_type.get(),
            nstep=int(self.nstep.get() or "1"),
            cmode=int(self.cmode.get() or "3"),
            phase1=int(self.phase1.get() or "1"),
            phase2=int(self.phase2.get() or "1"),
            phase_gloryx=self.phase_gloryx.get(),
            predictor_activate=self.predictor_activate.get(),
            keep_tmp=self.keep_tmp.get(),
            metatox_root=self.metatox_root.get().strip() or None,
        )

    def start_run(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        try:
            options = self._collect_options()
        except ValueError as exc:
            messagebox.showerror("Invalid input", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Invalid options", str(exc))
            return

        self._cancel_event.clear()
        self.clear_log()
        self.run_button.configure(state=tk.DISABLED)
        self.cancel_button.configure(state=tk.NORMAL)
        self.open_output_button.configure(state=tk.DISABLED)
        self.status_text.set("Running prediction...")

        def worker() -> None:
            try:
                output_dir = run_pipeline(
                    options,
                    log_callback=lambda message: self.after(0, self.append_log, message),
                    cancel_event=self._cancel_event,
                )
            except Exception as exc:  # noqa: BLE001
                self.after(0, self._on_run_failed, str(exc))
                return
            self.after(0, self._on_run_finished, output_dir)

        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()

    def cancel_run(self) -> None:
        self._cancel_event.set()
        self.status_text.set("Cancelling...")

    def _on_run_failed(self, error_message: str) -> None:
        self.append_log("")
        self.append_log(f"ERROR: {error_message}")
        self.run_button.configure(state=tk.NORMAL)
        self.cancel_button.configure(state=tk.DISABLED)
        self.status_text.set("Run failed")
        messagebox.showerror("MetaTox failed", error_message)

    def _on_run_finished(self, output_dir: Path) -> None:
        self._last_output_dir = output_dir
        self.append_log("")
        self.append_log(summarize_outputs(output_dir))
        self.run_button.configure(state=tk.NORMAL)
        self.cancel_button.configure(state=tk.DISABLED)
        self.open_output_button.configure(state=tk.NORMAL)
        self.status_text.set("Run completed")
        messagebox.showinfo("MetaTox completed", f"Results exported to:\n{output_dir}")

    def open_output_folder(self) -> None:
        target = self._last_output_dir
        if target is None:
            try:
                options = self._collect_options()
                target = resolve_output_directory(options)
            except Exception:
                messagebox.showinfo("No output", "Run a prediction first.")
                return
        if target.exists():
            open_path(target)
        else:
            messagebox.showinfo("No output", f"Output folder not found:\n{target}")


def main() -> None:
    app = MetaToxApp()
    app.mainloop()


if __name__ == "__main__":
    main()
