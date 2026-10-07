from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from pathlib import Path


class UILab(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("KAREEM UI LAB")
        self.geometry("900x700")
        self.minsize(760, 560)

        self.text_var = tk.StringVar(value="")
        self.check_var = tk.BooleanVar(value=False)
        self.radio_var = tk.StringVar(value="A")
        self.combo_var = tk.StringVar(value="Basic")
        self.slider_var = tk.DoubleVar(value=25)
        self.status_var = tk.StringVar(value="READY")

        root = ttk.Frame(self, padding=18)
        root.pack(fill="both", expand=True)

        header = ttk.Label(root, text="KAREEM_AGENT UNIVERSAL UI LAB", font=("Segoe UI", 18, "bold"))
        header.pack(anchor="w", pady=(0, 10))
        ttk.Label(root, text="Generic Windows UI capability fixture â€” no app-specific selectors").pack(anchor="w", pady=(0, 12))

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True)

        basic = ttk.Frame(nb, padding=18)
        advanced = ttk.Frame(nb, padding=18)
        nb.add(basic, text="Basic")
        nb.add(advanced, text="Advanced")

        # Basic controls
        ttk.Label(basic, text="Universal Text").grid(row=0, column=0, sticky="w", pady=6)
        self.entry = ttk.Entry(basic, textvariable=self.text_var, width=55)
        self.entry.grid(row=0, column=1, sticky="ew", pady=6, padx=10)

        self.check = ttk.Checkbutton(basic, text="Ready Check", variable=self.check_var)
        self.check.grid(row=1, column=0, columnspan=2, sticky="w", pady=6)

        ttk.Label(basic, text="Profile").grid(row=2, column=0, sticky="w", pady=6)
        self.combo = ttk.Combobox(basic, textvariable=self.combo_var, values=["Basic", "Expert", "Automation"], state="readonly", width=25)
        self.combo.grid(row=2, column=1, sticky="w", pady=6, padx=10)

        ttk.Label(basic, text="Radio").grid(row=3, column=0, sticky="nw", pady=6)
        radio_box = ttk.Frame(basic)
        radio_box.grid(row=3, column=1, sticky="w", pady=6, padx=10)
        ttk.Radiobutton(radio_box, text="Option A", variable=self.radio_var, value="A").pack(side="left", padx=(0, 10))
        ttk.Radiobutton(radio_box, text="Option B", variable=self.radio_var, value="B").pack(side="left")

        ttk.Label(basic, text="Items").grid(row=4, column=0, sticky="nw", pady=6)
        self.listbox = tk.Listbox(basic, height=5, exportselection=False)
        for item in ["Alpha", "Beta", "Gamma", "Delta"]:
            self.listbox.insert("end", item)
        self.listbox.grid(row=4, column=1, sticky="w", pady=6, padx=10)

        self.run_button = ttk.Button(basic, text="Run Universal Test", command=self.run_universal_test)
        self.run_button.grid(row=5, column=0, columnspan=2, sticky="w", pady=(18, 6))

        self.status = ttk.Label(basic, textvariable=self.status_var)
        self.status.grid(row=6, column=0, columnspan=2, sticky="w", pady=6)

        basic.columnconfigure(1, weight=1)

        # Advanced controls
        ttk.Label(advanced, text="Range Value").grid(row=0, column=0, sticky="w", pady=6)
        self.scale = ttk.Scale(advanced, from_=0, to=100, variable=self.slider_var, orient="horizontal", length=360)
        self.scale.grid(row=0, column=1, sticky="w", pady=6, padx=10)

        ttk.Label(advanced, text="Tree").grid(row=1, column=0, sticky="nw", pady=6)
        self.tree = ttk.Treeview(advanced, height=8)
        parent = self.tree.insert("", "end", text="Parent")
        self.tree.insert(parent, "end", text="Child A")
        self.tree.insert(parent, "end", text="Child B")
        self.tree.grid(row=1, column=1, sticky="w", pady=6, padx=10)

        ttk.Label(advanced, text="Dialog capability").grid(row=2, column=0, sticky="w", pady=6)
        self.dialog_button = ttk.Button(advanced, text="Open Native Dialog", command=self.open_native_dialog)
        self.dialog_button.grid(row=2, column=1, sticky="w", pady=6, padx=10)

    def open_native_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("KAREEM LAB DIALOG")
        dialog.transient(self)
        dialog.grab_set()
        ttk.Label(dialog, text="Universal modal dialog").pack(padx=25, pady=(20, 10))
        ttk.Entry(dialog).pack(padx=25, pady=8)
        ttk.Button(dialog, text="Close Dialog", command=dialog.destroy).pack(padx=25, pady=(4, 20))

    def run_universal_test(self):
        text_ok = bool(self.text_var.get())
        check_ok = bool(self.check_var.get())
        combo_ok = self.combo_var.get() == "Expert"
        list_ok = bool(self.listbox.curselection()) and self.listbox.get(self.listbox.curselection()[0]) == "Gamma"
        radio_ok = self.radio_var.get() == "B"
        range_ok = 69 <= float(self.slider_var.get()) <= 81
        if all([text_ok, check_ok, combo_ok, list_ok, radio_ok, range_ok]):
            self.status_var.set("PASS â€” universal controls verified")
            self.title("KAREEM UI LAB â€” PASS")
        else:
            self.status_var.set("FAIL â€” inspect state and retry")
            self.title("KAREEM UI LAB â€” FAIL")


if __name__ == "__main__":
    app = UILab()
    app.mainloop()
