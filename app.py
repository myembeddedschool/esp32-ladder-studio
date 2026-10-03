"""ESP32 Ladder Studio v0.1 — run with Python 3 and Tkinter."""
import copy
import json
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from model import TAGS, COILS, TIMERS, validate, parse_branch, branch_text, scan, stopped, example, wire_rungs, branch_around, dol_example, blink_example

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None

BG = "#111b2b"
PANEL = "#1b2940"
INK = "#dce8f5"
GREEN = "#45e3b2"
GRAY = "#6c819b"

class Studio:
    def __init__(self, root):
        self.root = root
        root.title("ESP32 Ladder Studio • v0.3")
        width = min(1180, max(760, root.winfo_screenwidth() - 80))
        height = min(760, max(480, root.winfo_screenheight() - 120))
        root.geometry(f"{width}x{height}")
        root.minsize(min(760, width), min(480, height))
        root.configure(bg=BG)
        self.project = example()
        self.bits = dict.fromkeys(TAGS, False)
        self.timers = {}
        self.sim_running = False
        self.port = None
        self.synced = None
        self.rx = b""
        self.last_poll = 0
        self.last_state = 0
        self.last_draw = 0
        self.selected = (0, 0)
        self.selected_contact = None
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=INK, font=("Segoe UI", 10))
        style.configure("TButton", padding=7, font=("Segoe UI", 10))
        style.configure("TCheckbutton", background=BG, foreground=INK)
        style.configure("Title.TLabel", font=("Segoe UI", 21, "bold"))
        style.configure("Run.TButton", background=GREEN, foreground=BG,
                        font=("Segoe UI", 11, "bold"), padding=(18, 9))
        style.configure("Stop.TButton", background="#f7a59a", foreground=BG,
                        font=("Segoe UI", 11, "bold"), padding=(18, 9))
        top = ttk.Frame(root, padding=16); top.pack(fill="x")
        ttk.Label(top, text="ESP32 Ladder Studio", style="Title.TLabel").pack(side="left")
        ttk.Label(top, text="Contacts → logic → real GPIO").pack(side="right")
        # Execution controls are packed before the expanding ladder area.
        # Keep them at the left so small windows cannot hide them horizontally.
        execution = ttk.Frame(root, padding=(16, 0, 16, 12)); execution.pack(fill="x")
        ttk.Button(execution, text="▶ RUN (F5)", style="Run.TButton", command=self.run).pack(side="left", padx=(0, 8))
        ttk.Button(execution, text="■ STOP (Esc)", style="Stop.TButton", command=self.stop).pack(side="left", padx=(0, 16))
        self.mode = tk.StringVar(value="SIMULATION • No hardware needed")
        ttk.Label(execution, textvariable=self.mode).pack(side="left")
        def shortcut(callback):
            # Ignore shortcuts while a modal editing dialog owns the grab.
            if root.grab_current() is None:
                callback()
            return "break"
        root.bind("<F5>", lambda event: shortcut(self.run))
        root.bind("<Escape>", lambda event: shortcut(self.stop))
        filebar = ttk.Frame(root, padding=(16, 0)); filebar.pack(fill="x")
        for label, callback in (("New", self.new), ("Open", self.open), ("Save", self.save),
                                ("Start/Stop example", self.load_example), ("DOL example", self.load_dol),
                                ("Blink LED", self.load_blink)):
            ttk.Button(filebar, text=label, command=callback).pack(side="left", padx=(0, 5))
        toolbar = ttk.Frame(root, padding=16); toolbar.pack(fill="x")
        for label, callback in (("Add rung", self.add_rung), ("Add parallel branch", self.add_branch),
                                ("Edit contacts", self.edit_branch), ("Set output / timer", self.set_coil),
                                ("Delete branch/rung", self.delete)):
            ttk.Button(toolbar, text=label, command=callback).pack(side="left", padx=(0, 5))
        grouping = ttk.Frame(root, padding=(16, 0, 16, 10)); grouping.pack(fill="x")
        for label, callback in (("Branch around contact", self.branch_contact),
                                ("Common before", lambda: self.edit_branch("prefix")),
                                ("Common after", lambda: self.edit_branch("suffix")),
                                ("Add TON timer", self.add_timer)):
            ttk.Button(grouping, text=label, command=callback).pack(side="left", padx=(0, 5))
        content = ttk.Frame(root, padding=(16, 0)); content.pack(fill="both", expand=True)
        left = ttk.Frame(content, width=200); left.pack(side="left", fill="y", padx=(0, 12))
        ttk.Label(left, text="INPUTS", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(left, text="Click to simulate a button").pack(anchor="w", pady=(3, 8))
        self.input_vars = []
        for i, label in enumerate(("I0 • START / GPIO25", "I1 • STOP / GPIO26",
                                    "I2 • SENSOR / GPIO27", "I3 • INPUT / GPIO32")):
            var = tk.BooleanVar()
            self.input_vars.append(var)
            ttk.Checkbutton(left, text=label, variable=var, command=self.input_changed).pack(anchor="w", pady=7)
        ttk.Label(left, text="OUTPUTS / MEMORY", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(20, 8))
        self.watch = tk.Text(left, width=25, height=16, bg=PANEL, fg=INK, font=("Consolas", 11),
                             relief="flat", state="disabled", padx=10, pady=10)
        self.watch.pack(fill="both", expand=True)
        pane = ttk.Frame(content); pane.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(pane, bg=PANEL, highlightthickness=0)
        scroll_y = ttk.Scrollbar(pane, orient="vertical", command=self.canvas.yview)
        scroll_y.pack(side="right", fill="y")
        scroll_x = ttk.Scrollbar(pane, orient="horizontal", command=self.canvas.xview)
        scroll_x.pack(side="bottom", fill="x")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.canvas.bind("<Configure>", lambda e: self.draw())
        self.canvas.bind("<Button-1>", self.select)
        self.canvas.bind("<Double-Button-1>", lambda e: self.edit_branch())
        connection = ttk.Frame(root, padding=(16, 0, 16, 10)); connection.pack(fill="x", before=content)
        self.port_name = tk.StringVar()
        self.ports = ttk.Combobox(connection, textvariable=self.port_name, width=15)
        self.ports.pack(side="left", padx=(0, 5))
        for label, callback in (("Refresh ports", self.refresh), ("Connect", self.connect),
                                ("Disconnect", self.disconnect), ("Upload ladder", self.upload)):
            ttk.Button(connection, text=label, command=callback).pack(side="left", padx=(0, 5))
        self.status = tk.StringVar(value="Select a branch, then Edit contacts. Green means logic is true.")
        ttk.Label(root, textvariable=self.status, wraplength=width-40).pack(anchor="w", padx=16, pady=(0, 12), before=content)
        self.refresh(); self.draw(); self.update_watch()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(10, self.tick)

    def fingerprint(self):
        return json.dumps(self.project, sort_keys=True)

    def change(self):
        self.sim_running = False
        self.selected_contact = None
        stopped(self.bits, self.timers)
        if self.port:
            self.status.set("Project edited. Upload before RUN; displayed ladder is not the board's active program.")
        else:
            self.status.set("Project edited. Press RUN to simulate.")
        self.draw(); self.update_watch()

    def editable(self):
        # Online changes are a stopped-state operation in this first version.
        if self.port:
            try: self.exchange("STOP", "OK STOP")
            except Exception as exc: self.failure(exc); return False
        return True

    def new(self):
        if not self.editable(): return
        self.project = {"version": 1, "name": "Untitled", "rungs": [
            {"coil": "Q0", "branches": [parse_branch("I0")]}]}
        self.selected = (0, 0); self.change()

    def load_example(self):
        if not self.editable(): return
        self.project = example(); self.selected = (0, 0); self.change()

    def load_dol(self):
        if not self.editable(): return
        self.project = dol_example(); self.selected = (0, 0); self.change()

    def load_blink(self):
        if not self.editable(): return
        self.project = blink_example(); self.selected = (0, 0); self.change()

    def add_timer(self):
        if not self.editable(): return
        used = {r["coil"] for r in self.project["rungs"]}
        timer = next((t for t in TIMERS if t not in used), None)
        if timer is None or len(self.project["rungs"]) >= 16:
            messagebox.showinfo("Timer limit", "Use at most four timers and sixteen total rungs."); return
        self.project["version"] = 3
        self.project["rungs"].append({"kind": "TON", "coil": timer, "preset_ms": 1000,
                                      "branches": [parse_branch("I0")]})
        self.selected = (len(self.project["rungs"])-1, 0); self.change()

    def branch_contact(self):
        selected = self.selected_contact
        if selected is None or selected[1] != "branch":
            messagebox.showinfo("Select a contact", "Click a contact symbol in the main branch first."); return
        if not self.editable(): return
        r, _, _, ci = selected
        text = simpledialog.askstring("Parallel contact", "New parallel contact: Q0 for NO, !I0 for NC", initialvalue="Q0")
        if text is None: return
        try:
            contacts = parse_branch(text.strip().upper())
            if len(contacts) != 1: raise ValueError("Choose one contact.")
            self.project = branch_around(self.project, r, ci, contacts[0])
            self.selected = (r, 1); self.change()
        except ValueError as exc: messagebox.showerror("Cannot add branch", str(exc))

    def open(self):
        path = filedialog.askopenfilename(filetypes=[("Ladder project", "*.json")])
        if not path: return
        try:
            with open(path, encoding="utf-8") as f: project = validate(json.load(f))
            if not self.editable(): return
            self.project = project; self.selected = (0, 0); self.change()
        except Exception as exc: messagebox.showerror("Cannot open project", str(exc))

    def save(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("Ladder project", "*.json")])
        if not path: return
        try:
            validate(self.project)
            with open(path, "w", encoding="utf-8") as f: json.dump(self.project, f, indent=2)
            self.status.set("Project saved.")
        except Exception as exc: messagebox.showerror("Cannot save", str(exc))

    def add_rung(self):
        if not self.editable(): return
        used = {r["coil"] for r in self.project["rungs"]}
        coil = next((t for t in COILS if t not in used), None)
        if not coil:
            messagebox.showinfo("Limit", "All 12 writable tags already have a coil."); return
        if len(self.project["rungs"]) >= 16:
            messagebox.showinfo("Limit", "Maximum sixteen rungs."); return
        self.project["rungs"].append({"coil": coil, "branches": [parse_branch("I0")]})
        self.selected = (len(self.project["rungs"])-1, 0); self.change()

    def add_branch(self):
        if not self.editable(): return
        r, _ = self.selected
        branches = self.project["rungs"][r]["branches"]
        if len(branches) == 4:
            messagebox.showinfo("Limit", "Maximum four branches per rung."); return
        branches.append(parse_branch("I0")); self.selected = (r, len(branches)-1); self.change()

    def edit_branch(self, region="branch"):
        if not self.editable(): return
        r, b = self.selected
        current = (self.project["rungs"][r]["branches"][b] if region == "branch"
                   else self.project["rungs"][r].get(region, []))
        window = tk.Toplevel(self.root); window.title("Edit series contacts"); window.geometry("520x440")
        window.transient(self.root); window.grab_set()
        frame = ttk.Frame(window, padding=16); frame.pack(fill="both", expand=True)
        title = {"branch": "Contacts in this branch (AND)", "prefix": "Common contacts BEFORE the branches", "suffix": "Common contacts AFTER the branches"}[region]
        ttk.Label(frame, text=title, font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Parallel branches are OR. NC is true when its tag is false.", wraplength=480).pack(anchor="w", pady=8)
        contacts = copy.deepcopy(current)
        listing = tk.Listbox(frame, height=9, font=("Consolas", 12)); listing.pack(fill="both", expand=True)
        row = ttk.Frame(frame); row.pack(fill="x", pady=12)
        tag = tk.StringVar(value="I0"); nc = tk.BooleanVar()
        ttk.Combobox(row, textvariable=tag, values=TAGS, state="readonly", width=8).pack(side="left")
        ttk.Checkbutton(row, text="NC contact", variable=nc).pack(side="left", padx=8)
        def redraw():
            listing.delete(0, "end")
            for c in contacts: listing.insert("end", ("NC  |/|   " if c["nc"] else "NO  | |   ") + c["tag"])
        def add():
            if len(contacts) >= 8: return
            selection = listing.curselection()
            at = selection[0]+1 if selection else len(contacts)
            contacts.insert(at, {"tag": tag.get(), "nc": nc.get()}); redraw()
            listing.selection_set(at)
        def remove():
            selection = listing.curselection()
            if selection: contacts.pop(selection[0]); redraw()
        def accept():
            if not contacts and region == "branch":
                messagebox.showerror("Empty branch", "Add at least one contact.", parent=window); return
            candidate = copy.deepcopy(self.project)
            if region == "branch": candidate["rungs"][r]["branches"][b] = contacts
            else:
                candidate["rungs"][r][region] = contacts
                candidate["version"] = max(2, candidate["version"])
            if any(c["tag"].startswith("T") for c in contacts): candidate["version"] = 3
            try: validate(candidate)
            except ValueError as exc:
                messagebox.showerror("Invalid contacts", str(exc), parent=window); return
            self.project = candidate
            window.destroy(); self.change()
        ttk.Button(row, text="Insert after / add", command=add).pack(side="left", padx=4)
        ttk.Button(row, text="Remove selected", command=remove).pack(side="left")
        ttk.Button(frame, text="Apply contacts", command=accept).pack(anchor="e")
        redraw()

    def set_coil(self):
        if not self.editable(): return
        r, _ = self.selected
        timer = self.project["rungs"][r].get("kind") == "TON"
        coil = simpledialog.askstring("Timer / output", "Choose T0–T3:" if timer else "Choose Q0–Q3 or M0–M7:", initialvalue=self.project["rungs"][r]["coil"])
        if coil is None: return
        candidate = copy.deepcopy(self.project); candidate["rungs"][r]["coil"] = coil.strip().upper()
        if timer:
            preset = simpledialog.askinteger("TON preset", "Delay in milliseconds (1000 = 1 second):",
                                             initialvalue=candidate["rungs"][r]["preset_ms"], minvalue=1, maxvalue=3600000)
            if preset is None: return
            candidate["rungs"][r]["preset_ms"] = preset
        try: validate(candidate)
        except ValueError as exc: messagebox.showerror("Invalid coil", str(exc)); return
        self.project = candidate; self.change()

    def delete(self):
        if not self.editable(): return
        r, b = self.selected; branches = self.project["rungs"][r]["branches"]
        if len(branches) > 1: branches.pop(b)
        elif len(self.project["rungs"]) > 1: self.project["rungs"].pop(r)
        else:
            messagebox.showinfo("Keep one rung", "The project must have at least one rung."); return
        self.selected = (min(r, len(self.project["rungs"])-1), 0); self.change()

    def select(self, event):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        self.selected_contact = None
        for ri, region, bi, ci, cx, cy in self.contact_hits:
            if abs(x-cx) <= 22 and abs(y-cy) <= 29:
                self.selected = (ri, bi)
                self.selected_contact = (ri, region, bi, ci)
                self.status.set("Contact selected. Use Branch around contact, or Edit contacts to insert in series.")
                self.draw(); return
        for r, b, top, bottom in self.hitboxes:
            if top <= y < bottom:
                self.selected = (r, b); self.draw(); return

    def draw(self):
        c = self.canvas; c.delete("all"); self.hitboxes = []; self.contact_hits = []
        slots = max(len(r.get("prefix", [])) + max(len(b) for b in r["branches"]) + len(r.get("suffix", []))
                    for r in self.project["rungs"])
        width = max(c.winfo_width(), 760, 280 + slots*85)
        left, right = 44, width-40
        y = 60
        show = not self.port or self.synced == self.fingerprint()
        c.create_text(left, 22, text="LADDER  •  click a contact to select / double-click a branch to edit", fill=INK,
                      anchor="w", font=("Segoe UI", 10))
        def truth(contacts):
            return show and all(self.bits[ct["tag"]] != ct["nc"] for ct in contacts)
        def symbols(contacts, x0, by, ri, region, bi, background):
            for ci, ct in enumerate(contacts):
                x = x0 + 40 + ci*85
                key = (ri, region, bi, ci)
                if self.selected_contact == key:
                    c.create_rectangle(x-24, by-32, x+24, by+20, outline="#f6cc65", width=2)
                self.contact_hits.append((*key, x, by))
                contact_color = GREEN if show and self.bits[ct["tag"]] != ct["nc"] else INK
                c.create_rectangle(x-17, by-13, x+17, by+13, fill=background, outline="")
                c.create_line(x-9, by-11, x-9, by+11, fill=contact_color, width=3)
                c.create_line(x+9, by-11, x+9, by+11, fill=contact_color, width=3)
                if ct["nc"]:
                    c.create_line(x-14, by+12, x+14, by-12, fill=contact_color, width=2)
                c.create_text(x, by-23, text=ct["tag"], fill=INK, font=("Consolas", 11))
        for ri, rung in enumerate(self.project["rungs"]):
            prefix, suffix = rung.get("prefix", []), rung.get("suffix", [])
            top = y; bottom = y+(len(rung["branches"])-1)*65
            split = left + len(prefix)*85 + 20
            join = split + max(len(b) for b in rung["branches"])*85
            suffix_end = join + len(suffix)*85
            prefix_ok = truth(prefix)
            group_ok = any(truth(b) for b in rung["branches"])
            c.create_text(13, top, text=str(ri+1), fill=GRAY, font=("Consolas", 12))
            c.create_line(left, top, split, top, fill=GREEN if prefix_ok else GRAY, width=2)
            symbols(prefix, left, top, ri, "prefix", 0, PANEL)
            c.create_line(split, top, split, bottom, fill=GREEN if prefix_ok else GRAY, width=2)
            c.create_line(join, top, join, bottom, fill=GREEN if prefix_ok and group_ok else GRAY, width=2)
            for bi, branch in enumerate(rung["branches"]):
                by = top+bi*65
                self.hitboxes.append((ri, bi, by-32, by+30))
                background = "#253b57" if self.selected == (ri, bi) else PANEL
                if self.selected == (ri, bi):
                    c.create_rectangle(split+3, by-32, join-3, by+25, fill=background, outline="#4c7098")
                c.create_line(split, by, join, by, fill=GREEN if prefix_ok and truth(branch) else GRAY, width=2)
                symbols(branch, split, by, ri, "branch", bi, background)
            path_ok = prefix_ok and group_ok and truth(suffix)
            c.create_line(join, top, suffix_end, top, fill=GREEN if path_ok else GRAY, width=2)
            symbols(suffix, join, top, ri, "suffix", 0, PANEL)
            color = GREEN if show and self.bits[rung["coil"]] else GRAY
            cx = right-48
            c.create_line(suffix_end, top, cx-15, top, fill=GREEN if path_ok else GRAY, width=2)
            if rung.get("kind") == "TON":
                c.create_rectangle(cx-40, top-15, cx+40, top+15, fill=PANEL, outline=color, width=2)
                c.create_text(cx, top, text="TON " + rung["coil"], fill=INK, font=("Consolas", 11))
                c.create_text(cx, top-29, text=f"PT {rung['preset_ms']} ms", fill=INK, font=("Consolas", 10))
                elapsed = self.timers.get(rung["coil"], {}).get("elapsed", 0)
                c.create_text(cx, top+29, text=f"ET {elapsed} ms", fill=GRAY, font=("Consolas", 10))
                c.create_line(cx+40, top, right, top, fill=color, width=2)
            else:
                c.create_oval(cx-15, top-13, cx+15, top+13, outline=color, width=3)
                c.create_line(cx+15, top, right, top, fill=color, width=2)
                c.create_text(cx, top-24, text=rung["coil"], fill=INK, font=("Consolas", 11))
            y = bottom+90
        c.create_line(left, 42, left, y-25, fill=INK, width=3)
        c.create_line(right, 42, right, y-25, fill=INK, width=3)
        c.configure(scrollregion=(0, 0, width, y))

    def input_changed(self):
        if self.port:
            self.status.set("Online inputs come from real ESP32 pins. Simulation switches do not force hardware.")
            for i, v in enumerate(self.input_vars): v.set(self.bits[f"I{i}"])
        else:
            for i, v in enumerate(self.input_vars): self.bits[f"I{i}"] = v.get()
            self.draw(); self.update_watch()

    def update_watch(self):
        rows = []
        for t in COILS + TIMERS:
            if t.startswith("T"):
                elapsed = self.timers.get(t, {}).get("elapsed", 0)
                rows.append(f"{'●' if self.bits[t] else '○'}  {t}.DN = {int(self.bits[t])} {elapsed}ms")
                continue
            pin = f" GPIO{(18,19,21,22)[int(t[1])]}" if t.startswith("Q") else " internal"
            rows.append(f"{'●' if self.bits[t] else '○'}  {t} = {int(self.bits[t])}{pin}")
        self.watch.configure(state="normal"); self.watch.delete("1.0", "end")
        self.watch.insert("end", "\n".join(rows)); self.watch.configure(state="disabled")

    def refresh(self):
        available = [p.device for p in list_ports.comports()] if serial else []
        self.ports["values"] = available
        if available and not self.port_name.get(): self.port_name.set(available[0])

    def exchange(self, command, expected):
        if not self.port: raise RuntimeError("Connect an ESP32 first.")
        self.port.write((command+"\n").encode("ascii"))
        deadline = time.monotonic()+2
        while time.monotonic() < deadline:
            raw = self.port.readline().decode("ascii", errors="replace").strip()
            if raw.startswith("ERR"): raise RuntimeError(raw)
            if raw.startswith("PONG ") and raw != expected:
                raise RuntimeError("Firmware version mismatch. Upload the v0.3 Arduino sketch, then reconnect.")
            if raw == expected: return
        raise RuntimeError("No valid reply. Check board, port and firmware.")

    def connect(self):
        if self.port: return
        if not serial:
            messagebox.showinfo("USB support", "Install USB support with: py -m pip install -r requirements.txt"); return
        try:
            self.sim_running = False; stopped(self.bits, self.timers)
            self.port = serial.Serial(self.port_name.get(), 115200, timeout=0.1, write_timeout=1)
            # ESP32 development boards often reset when the port opens.
            time.sleep(1.2); self.port.reset_input_buffer(); self.rx = b""
            self.exchange("PING", "PONG ESP32_LADDER_V2")
            self.exchange("STOP", "OK STOP")
            self.synced = None
            self.last_state = time.monotonic(); self.last_poll = 0
            self.mode.set("ONLINE • ESP32 connected")
            self.status.set("Connected, board STOPPED. Upload ladder, then press RUN.")
        except Exception as exc: self.failure(exc)

    def disconnect(self):
        if self.port:
            try: self.exchange("STOP", "OK STOP")
            except Exception: pass
            self.port.close(); self.port = None
        self.synced = None; self.rx = b""; self.sim_running = False; stopped(self.bits, self.timers)
        self.mode.set("SIMULATION • No hardware needed")
        self.status.set("Disconnected. A lost cable cannot guarantee STOP reached the board.")
        self.draw(); self.update_watch()

    def failure(self, exc):
        if self.port:
            try: self.port.close()
            except Exception: pass
        self.port = None; self.synced = None; self.sim_running = False; self.rx = b""
        stopped(self.bits, self.timers)
        self.mode.set("SIMULATION • Connection unavailable")
        self.status.set("Connection failed. The ESP32 may continue running if communication was lost.")
        messagebox.showerror("Connection error", str(exc))

    def upload(self):
        if not self.port:
            messagebox.showinfo("Upload", "Flash the supplied Arduino firmware once, then Connect."); return
        try:
            commands = wire_rungs(self.project)
            self.exchange("BEGIN", "OK BEGIN")
            for command in commands: self.exchange(command, "OK T" if command.startswith("T ") else "OK R")
            self.exchange("COMMIT", "OK COMMIT")
            self.synced = self.fingerprint(); stopped(self.bits, self.timers)
            self.status.set("Ladder uploaded to RAM. Board STOPPED; press RUN. Power loss clears the program.")
        except Exception as exc: self.failure(exc)

    def run(self):
        try:
            validate(self.project)
            if self.port:
                if self.synced != self.fingerprint(): raise RuntimeError("Upload the current project before RUN.")
                self.exchange("RUN", "OK RUN"); self.status.set("ESP32 RUNNING • approximate 10 ms scan")
            else:
                self.sim_running = True; self.status.set("SIMULATION RUNNING • click I0 START, release it, then click I1 STOP")
        except Exception as exc: messagebox.showerror("Cannot run", str(exc))

    def stop(self):
        self.sim_running = False
        if self.port:
            try: self.exchange("STOP", "OK STOP")
            except Exception as exc: self.failure(exc); return
        stopped(self.bits, self.timers); self.draw(); self.update_watch(); self.status.set("STOPPED • outputs and memory cleared")

    def tick(self):
        if self.port:
            try:
                self.rx += self.port.read(self.port.in_waiting)
                while b"\n" in self.rx:
                    line, self.rx = self.rx.split(b"\n", 1)
                    parts = line.decode("ascii", errors="replace").strip().split()
                    if len(parts) == 11 and parts[0] == "STATE":
                        self.last_state = time.monotonic()
                        for a, value, n in (("I", int(parts[2]), 4), ("Q", int(parts[3]), 4), ("M", int(parts[4]), 8)):
                            for i in range(n): self.bits[f"{a}{i}"] = bool(value & (1 << i))
                        for i, var in enumerate(self.input_vars): var.set(self.bits[f"I{i}"])
                        for i in range(4):
                            self.bits[f"T{i}"] = bool(int(parts[6]) & (1 << i))
                            self.timers[f"T{i}"] = {"elapsed": int(parts[7+i])}
                        self.mode.set("ONLINE • " + ("RUNNING" if parts[1] == "1" else "STOPPED"))
                if time.monotonic()-self.last_poll > 0.2:
                    self.port.write(b"STATE\n"); self.last_poll = time.monotonic()
                if time.monotonic()-self.last_state > 3:
                    raise RuntimeError("Live monitoring timed out. Board state is unknown.")
            except Exception as exc: self.failure(exc)
        elif self.sim_running:
            scan(self.project, self.bits, timers=self.timers)
        if time.monotonic()-self.last_draw >= 0.1:
            self.draw(); self.update_watch(); self.last_draw = time.monotonic()
        self.root.after(10, self.tick)

    def close(self):
        if self.port: self.disconnect()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk(); Studio(root); root.mainloop()
