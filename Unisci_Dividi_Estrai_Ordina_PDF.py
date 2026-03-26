import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
from PyPDF2 import PdfReader, PdfWriter


# ============================================================
#  TEMA SCURO ELEGANTE
# ============================================================

def setup_dark_theme(root: tk.Tk):
    style = ttk.Style(root)
    style.theme_use("clam")

    bg_main = "#1E1E1E"
    bg_panel = "#252526"
    bg_sidebar = "#1E1E1E"
    bg_header = "#252526"
    bg_footer = "#252526"
    border_color = "#3C3C3C"
    fg_primary = "#FFFFFF"
    fg_secondary = "#C8C8C8"
    accent = "#569CD6"
    accent_hover = "#6CB8FF"
    danger = "#D16969"

    root.configure(bg=bg_main)

    style.configure(".", background=bg_main, foreground=fg_primary, font=("Segoe UI", 10))

    style.configure("TFrame", background=bg_main)
    style.configure("Panel.TFrame", background=bg_panel, borderwidth=1, relief="solid")
    style.configure("Sidebar.TFrame", background=bg_sidebar)
    style.configure("Header.TFrame", background=bg_header)
    style.configure("Footer.TFrame", background=bg_footer)

    style.configure("TLabel", background=bg_main, foreground=fg_primary)
    style.configure("Secondary.TLabel", background=bg_main, foreground=fg_secondary)
    style.configure("Title.TLabel", font=("Segoe UI Semibold", 12), foreground=fg_primary, background=bg_header)
    style.configure("SectionTitle.TLabel", font=("Segoe UI Semibold", 11), foreground=accent, background=bg_panel)

    style.configure("TButton",
                    background=bg_panel,
                    foreground=fg_primary,
                    borderwidth=1,
                    padding=(10, 5))
    style.map("TButton", background=[("active", accent_hover)])

    style.configure("Primary.TButton",
                    background=accent,
                    foreground="#FFFFFF",
                    borderwidth=0,
                    padding=(12, 6))
    style.map("Primary.TButton", background=[("active", accent_hover)])

    style.configure("Danger.TButton",
                    background=danger,
                    foreground="#FFFFFF",
                    borderwidth=0,
                    padding=(12, 6))

    style.configure("Sidebar.TButton",
                    background=bg_sidebar,
                    foreground=fg_secondary,
                    anchor="w",
                    padding=(14, 8),
                    borderwidth=0)
    style.map("Sidebar.TButton",
              background=[("active", "#333333")],
              foreground=[("active", fg_primary)])

    style.configure("Treeview",
                    background=bg_panel,
                    foreground=fg_primary,
                    fieldbackground=bg_panel,
                    bordercolor=border_color)
    style.map("Treeview",
              background=[("selected", accent)],
              foreground=[("selected", "#FFFFFF")])

    style.configure("TEntry",
                    fieldbackground=bg_panel,
                    foreground=fg_primary,
                    bordercolor=border_color,
                    padding=5)

    style.configure("TCombobox",
                    fieldbackground=bg_panel,
                    background=bg_panel,
                    foreground=fg_primary,
                    arrowcolor=fg_primary)


# ============================================================
#  ENTRY CON PLACEHOLDER
# ============================================================

class PlaceholderEntry(ttk.Entry):
    def __init__(self, master=None, placeholder="", color="#6A6A6A", **kwargs):
        super().__init__(master, **kwargs)
        self.placeholder = placeholder
        self.placeholder_color = color
        self.default_fg_color = self.cget("foreground")
        self._has_placeholder = False
        self.bind("<FocusIn>", self._clear)
        self.bind("<FocusOut>", self._add)
        self._add()

    def _clear(self, event=None):
        if self._has_placeholder:
            self.delete(0, tk.END)
            self.config(foreground=self.default_fg_color)
            self._has_placeholder = False

    def _add(self, event=None):
        if not self.get():
            self.config(foreground=self.placeholder_color)
            self.delete(0, tk.END)
            self.insert(0, self.placeholder)
            self._has_placeholder = True

    def get_value(self):
        if self._has_placeholder:
            return ""
        return super().get()


# ============================================================
#  UTILITY PDF
# ============================================================

def get_pdf_page_count(path: str) -> int:
    reader = PdfReader(path)
    return len(reader.pages)


def parse_page_spec(spec: str, max_pages: int):
    pages = set()
    spec = spec.replace(" ", "")
    if not spec:
        return []
    parts = spec.split(",")
    for part in parts:
        if "-" in part:
            start, end = part.split("-")
            if not start.isdigit() or not end.isdigit():
                raise ValueError(f"Intervallo non valido: {part}")
            s = int(start)
            e = int(end)
            if s < 1 or e < 1 or s > max_pages or e > max_pages or s > e:
                raise ValueError(f"Intervallo fuori range: {part}")
            for p in range(s, e + 1):
                pages.add(p - 1)
        else:
            if not part.isdigit():
                raise ValueError(f"Pagina non valida: {part}")
            p = int(part)
            if p < 1 or p > max_pages:
                raise ValueError(f"Pagina fuori range: {p}")
            pages.add(p - 1)
    return sorted(pages)


# ============================================================
#  APP PRINCIPALE
# ============================================================

class PDFManagerApp(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("PDF Manager - Unisci / Dividi / Estrai / Riordina")
        self.geometry("1200x750")
        self.minsize(1000, 650)

        self.pdf_items = []  # lista dei file PDF
        self._reorder_reader = None
        self._reorder_path = None

        setup_dark_theme(self)
        self._build_layout()

    # ---------------- Layout base ----------------

    def _build_layout(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Header
        header = ttk.Frame(self, style="Header.TFrame")
        header.grid(row=0, column=0, columnspan=2, sticky="nsew")
        ttk.Label(header, text="PDF Manager", style="Title.TLabel").grid(row=0, column=0, padx=16, pady=10, sticky="w")

        # Sidebar
        sidebar = ttk.Frame(self, style="Sidebar.TFrame")
        sidebar.grid(row=1, column=0, sticky="nsew")
        sidebar.grid_rowconfigure(10, weight=1)

        ttk.Button(sidebar, text="Unisci PDF", style="Sidebar.TButton",
                   command=self.show_file_view).grid(row=1, column=0, sticky="ew")
        ttk.Button(sidebar, text="Dividi PDF", style="Sidebar.TButton",
                   command=self.show_pages_view).grid(row=2, column=0, sticky="ew")

        # Area principale
        self.main_area = ttk.Frame(self, style="TFrame")
        self.main_area.grid(row=1, column=1, sticky="nsew")

        # Footer
        footer = ttk.Frame(self, style="Footer.TFrame")
        footer.grid(row=2, column=0, columnspan=2, sticky="nsew")
        footer.grid_columnconfigure(0, weight=1)
        self.status_label = ttk.Label(footer, text="Pronto.", style="Secondary.TLabel")
        self.status_label.grid(row=0, column=0, padx=16, pady=6, sticky="w")

        self.show_file_view()

    def _clear_main(self):
        for w in self.main_area.winfo_children():
            w.destroy()

    # ========================================================
    #  VISTA: GESTIONE FILE (UNIONE)
    # ========================================================

    def show_file_view(self):
        self._clear_main()
        self.status_label.config(text="Gestione file PDF.")

        container = ttk.Frame(self.main_area, style="Panel.TFrame")
        container.pack(fill="both", expand=True, padx=16, pady=16)

        ttk.Label(container, text="Lista PDF", style="SectionTitle.TLabel").pack(anchor="w", padx=16, pady=(16, 8))

        # Treeview
        columns = ("idx", "name", "pages", "path")
        self.tree = ttk.Treeview(container, columns=columns, show="headings", selectmode="extended")
        self.tree.heading("idx", text="#")
        self.tree.heading("name", text="Nome file")
        self.tree.heading("pages", text="Pagine")
        self.tree.heading("path", text="Percorso")

        self.tree.column("idx", width=40, anchor="center")
        self.tree.column("name", width=250, anchor="w")
        self.tree.column("pages", width=70, anchor="center")
        self.tree.column("path", width=500, anchor="w")

        self.tree.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        # Drag & Drop
        self.tree.drop_target_register(DND_FILES)
        self.tree.dnd_bind('<<Drop>>', self.on_drop_files)

        # Pulsanti gestione lista
        btn_frame = ttk.Frame(container, style="Panel.TFrame")
        btn_frame.pack(fill="x", padx=16, pady=(0, 16))

        ttk.Button(btn_frame, text="Aggiungi PDF", command=self.add_pdfs).grid(row=0, column=0, padx=4, pady=8, sticky="w")
        ttk.Button(btn_frame, text="Rimuovi selezionati", command=self.remove_selected).grid(row=0, column=1, padx=4, pady=8, sticky="w")
        ttk.Button(btn_frame, text="Svuota lista", command=self.clear_list).grid(row=0, column=2, padx=4, pady=8, sticky="w")

        ttk.Button(btn_frame, text="Sposta su", command=self.move_up).grid(row=0, column=3, padx=20, pady=8, sticky="w")
        ttk.Button(btn_frame, text="Sposta giù", command=self.move_down).grid(row=0, column=4, padx=4, pady=8, sticky="w")

        # Unione
        merge_frame = ttk.Frame(container, style="Panel.TFrame")
        merge_frame.pack(fill="x", padx=16, pady=(0, 16))

        ttk.Label(merge_frame, text="Unisci tutti i PDF in lista", style="Secondary.TLabel").grid(row=0, column=0, padx=8, pady=(8, 2), sticky="w")
        ttk.Button(merge_frame, text="Unisci PDF", style="Primary.TButton",
                   command=self.merge_pdfs).grid(row=1, column=0, padx=8, pady=(0, 8), sticky="w")

        # Log
        ttk.Label(container, text="Log operazioni", style="Secondary.TLabel").pack(anchor="w", padx=16, pady=(0, 4))
        self.log = tk.Text(container, height=8, bg="#1E1E1E", fg="#C8C8C8",
                           insertbackground="#FFFFFF", relief="flat", wrap="word")
        self.log.pack(fill="both", expand=False, padx=16, pady=(0, 16))
        self.log.insert("end", "Log:\n")

        self.refresh_tree()

    # ========================================================
    #  GESTIONE LISTA PDF
    # ========================================================

    def add_pdfs(self):
        paths = filedialog.askopenfilenames(filetypes=[("PDF", "*.pdf")])
        if not paths:
            return
        for path in paths:
            if not os.path.exists(path):
                continue
            try:
                pages = get_pdf_page_count(path)
                self.pdf_items.append({"path": path, "pages": pages})
            except Exception as e:
                self.log.insert("end", f"Errore con {path}: {e}\n")
        self.refresh_tree()

    def remove_selected(self):
        selected = self.tree.selection()
        if not selected:
            return
        indices = sorted([int(self.tree.item(i, "values")[0]) - 1 for i in selected], reverse=True)
        for idx in indices:
            if 0 <= idx < len(self.pdf_items):
                self.pdf_items.pop(idx)
        self.refresh_tree()

    def clear_list(self):
        self.pdf_items.clear()
        self.refresh_tree()

    def move_up(self):
        selected = self.tree.selection()
        if len(selected) != 1:
            return
        idx = int(self.tree.item(selected[0], "values")[0]) - 1
        if idx <= 0:
            return
        self.pdf_items[idx - 1], self.pdf_items[idx] = self.pdf_items[idx], self.pdf_items[idx - 1]
        self.refresh_tree()
        self.tree.selection_set(self.tree.get_children()[idx - 1])

    def move_down(self):
        selected = self.tree.selection()
        if len(selected) != 1:
            return
        idx = int(self.tree.item(selected[0], "values")[0]) - 1
        if idx >= len(self.pdf_items) - 1:
            return
        self.pdf_items[idx + 1], self.pdf_items[idx] = self.pdf_items[idx], self.pdf_items[idx + 1]
        self.refresh_tree()
        self.tree.selection_set(self.tree.get_children()[idx + 1])

    def refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for i, item in enumerate(self.pdf_items, start=1):
            path = item["path"]
            name = os.path.basename(path)
            pages = item["pages"]
            self.tree.insert("", "end", values=(i, name, pages, path))

    # ========================================================
    #  DRAG & DROP
    # ========================================================

    def on_drop_files(self, event):
        raw = event.data
        paths = self._parse_dropped_files(raw)

        added = 0
        for path in paths:
            if path.lower().endswith(".pdf") and os.path.exists(path):
                try:
                    pages = get_pdf_page_count(path)
                    self.pdf_items.append({"path": path, "pages": pages})
                    added += 1
                except Exception as e:
                    self.log.insert("end", f"Errore con {path}: {e}\n")

        if added:
            self.refresh_tree()
            self.log.insert("end", f"Aggiunti {added} PDF tramite drag & drop.\n")
            self.log.see("end")

    def _parse_dropped_files(self, raw):
        files = []
        current = ""
        inside = False

        for c in raw:
            if c == "{":
                inside = True
                current = ""
            elif c == "}":
                inside = False
                files.append(current)
                current = ""
            elif c == " " and not inside:
                if current:
                    files.append(current)
                    current = ""
            else:
                current += c

        if current:
            files.append(current)

        return files

    # ========================================================
    #  UNIONE PDF
    # ========================================================

    def merge_pdfs(self):
        if not self.pdf_items:
            messagebox.showwarning("Attenzione", "La lista PDF è vuota.")
            return
        paths = [item["path"] for item in self.pdf_items]
        out_path = filedialog.asksaveasfilename(defaultextension=".pdf",
                                                filetypes=[("PDF", "*.pdf")],
                                                title="Salva PDF unito")
        if not out_path:
            return
        try:
            writer = PdfWriter()
            for p in paths:
                reader = PdfReader(p)
                for page in reader.pages:
                    writer.add_page(page)
            with open(out_path, "wb") as f:
                writer.write(f)
            self.log.insert("end", f"PDF uniti in: {out_path}\n")
            self.log.see("end")
            self.status_label.config(text="Unione completata.")
        except Exception as e:
            messagebox.showerror("Errore", str(e))
            self.log.insert("end", f"ERRORE unione: {e}\n")
            self.log.see("end")
            self.status_label.config(text="Errore durante l'unione.")

    # ========================================================
    #  VISTA: OPERAZIONI SULLE PAGINE
    # ========================================================

    def show_pages_view(self):
        self._clear_main()
        self.status_label.config(text="Operazioni sulle pagine PDF.")

        container = ttk.Frame(self.main_area, style="Panel.TFrame")
        container.pack(fill="both", expand=True, padx=16, pady=16)

        # Selezione file
        file_frame = ttk.Frame(container, style="Panel.TFrame")
        file_frame.pack(fill="x", padx=16, pady=(8, 16))

        ttk.Label(file_frame, text="Percorso PDF:", style="TLabel").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self.single_pdf_entry = PlaceholderEntry(file_frame, placeholder="Seleziona un PDF o incolla il percorso")
        self.single_pdf_entry.grid(row=0, column=1, padx=8, pady=8, sticky="ew")
        file_frame.grid_columnconfigure(1, weight=1)
        ttk.Button(file_frame, text="Sfoglia...", command=self.browse_single_pdf).grid(row=0, column=2, padx=8, pady=8)

        # Notebook
        notebook = ttk.Notebook(container)
        notebook.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        # --- Tab: Dividi ---
        split_tab = ttk.Frame(notebook, style="Panel.TFrame")
        notebook.add(split_tab, text="Dividi")

        ttk.Label(split_tab, text="Intervalli di pagine (es: 1-3,4-6):", style="TLabel").grid(row=0, column=0, padx=16, pady=(16, 4), sticky="w")
        self.split_entry = PlaceholderEntry(split_tab, placeholder="es. 1-3,4-6")
        self.split_entry.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="ew")
        split_tab.grid_columnconfigure(0, weight=1)

        ttk.Button(split_tab, text="Dividi PDF", style="Primary.TButton",
                   command=self.split_pdf).grid(row=2, column=0, padx=16, pady=(8, 4), sticky="w")

        ttk.Button(split_tab, text="Dividi in un PDF per ogni pagina",
                   style="Primary.TButton",
                   command=self.split_every_page).grid(row=3, column=0, padx=16, pady=(0, 16), sticky="w")

        # --- Tab: Estrai ---
        extract_tab = ttk.Frame(notebook, style="Panel.TFrame")
        notebook.add(extract_tab, text="Estrai")

        ttk.Label(extract_tab, text="Pagine da estrarre (es: 1,3,5-7):", style="TLabel").grid(row=0, column=0, padx=16, pady=(16, 4), sticky="w")
        self.extract_entry = PlaceholderEntry(extract_tab, placeholder="es. 1,3,5-7")
        self.extract_entry.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="ew")
        extract_tab.grid_columnconfigure(0, weight=1)

        ttk.Button(extract_tab, text="Estrai pagine", style="Primary.TButton",
                   command=self.extract_pages).grid(row=2, column=0, padx=16, pady=(8, 16), sticky="w")

        # --- Tab: Elimina ---
        delete_tab = ttk.Frame(notebook, style="Panel.TFrame")
        notebook.add(delete_tab, text="Elimina")

        ttk.Label(delete_tab, text="Pagine da eliminare (es: 2,4-6):", style="TLabel").grid(row=0, column=0, padx=16, pady=(16, 4), sticky="w")
        self.delete_entry = PlaceholderEntry(delete_tab, placeholder="es. 2,4-6")
        self.delete_entry.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="ew")
        delete_tab.grid_columnconfigure(0, weight=1)

        ttk.Button(delete_tab, text="Elimina pagine", style="Primary.TButton",
                   command=self.delete_pages).grid(row=2, column=0, padx=16, pady=(8, 16), sticky="w")

        # --- Tab: Riordina ---
        reorder_tab = ttk.Frame(notebook, style="Panel.TFrame")
        notebook.add(reorder_tab, text="Riordina")

        ttk.Button(reorder_tab, text="Carica pagine del PDF",
                   style="Primary.TButton",
                   command=self.load_pages_for_reorder).grid(row=0, column=0, padx=16, pady=(16, 8), sticky="w")

        self.page_tree = ttk.Treeview(reorder_tab, columns=("idx", "label"), show="headings", height=12)
        self.page_tree.heading("idx", text="#")
        self.page_tree.heading("label", text="Pagina")

        self.page_tree.column("idx", width=50, anchor="center")
        self.page_tree.column("label", width=200, anchor="w")

        self.page_tree.grid(row=1, column=0, padx=16, pady=8, sticky="nsew")
        reorder_tab.grid_rowconfigure(1, weight=1)
        reorder_tab.grid_columnconfigure(0, weight=1)

        btn_frame = ttk.Frame(reorder_tab, style="Panel.TFrame")
        btn_frame.grid(row=2, column=0, padx=16, pady=8, sticky="w")

        ttk.Button(btn_frame, text="Sposta su", command=self.move_page_up).grid(row=0, column=0, padx=4, pady=4)
        ttk.Button(btn_frame, text="Sposta giù", command=self.move_page_down).grid(row=0, column=1, padx=4, pady=4)

        ttk.Button(reorder_tab, text="Applica nuovo ordine",
                   style="Primary.TButton",
                   command=self.apply_reordered_pages).grid(row=3, column=0, padx=16, pady=(8, 16), sticky="w")

        # Log
        ttk.Label(container, text="Log operazioni", style="Secondary.TLabel").pack(anchor="w", padx=16, pady=(0, 4))
        self.log = tk.Text(container, height=8, bg="#1E1E1E", fg="#C8C8C8",
                           insertbackground="#FFFFFF", relief="flat", wrap="word")
        self.log.pack(fill="both", expand=False, padx=16, pady=(0, 16))
        self.log.insert("end", "Log:\n")

    # ========================================================
    #  OPERAZIONI SULLE PAGINE
    # ========================================================

    def browse_single_pdf(self):
        path = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if path:
            self.single_pdf_entry._clear()
            self.single_pdf_entry.delete(0, tk.END)
            self.single_pdf_entry.insert(0, path)

    def _get_single_pdf_and_reader(self):
        path = self.single_pdf_entry.get_value().strip()
        if not path:
            raise ValueError("Seleziona un PDF.")
        if not os.path.exists(path):
            raise FileNotFoundError("Il file PDF selezionato non esiste.")
        reader = PdfReader(path)
        return path, reader

    def split_pdf(self):
        try:
            path, reader = self._get_single_pdf_and_reader()
            max_pages = len(reader.pages)
            spec = self.split_entry.get_value().strip()
            if not spec:
                raise ValueError("Inserisci gli intervalli di pagine.")
            intervals = spec.replace(" ", "").split(",")
            out_dir = filedialog.askdirectory(title="Seleziona cartella di destinazione")
            if not out_dir:
                return
            base_name = os.path.splitext(os.path.basename(path))[0]

            for idx, interval in enumerate(intervals, start=1):
                if not interval:
                    continue
                pages = parse_page_spec(interval, max_pages)
                if not pages:
                    continue
                writer = PdfWriter()
                for p in pages:
                    writer.add_page(reader.pages[p])
                out_path = os.path.join(out_dir, f"{base_name}_part_{idx}.pdf")
                with open(out_path, "wb") as f:
                    writer.write(f)
                self.log.insert("end", f"Creato: {out_path}\n")

            self.log.see("end")
            self.status_label.config(text="Divisione completata.")
        except Exception as e:
            messagebox.showerror("Errore", str(e))
            self.log.insert("end", f"ERRORE divisione: {e}\n")
            self.log.see("end")
            self.status_label.config(text="Errore durante la divisione.")

    def split_every_page(self):
        try:
            path, reader = self._get_single_pdf_and_reader()
            max_pages = len(reader.pages)

            out_dir = filedialog.askdirectory(title="Seleziona cartella di destinazione")
            if not out_dir:
                return

            base_name = os.path.splitext(os.path.basename(path))[0]

            for i in range(max_pages):
                writer = PdfWriter()
                writer.add_page(reader.pages[i])
                out_path = os.path.join(out_dir, f"{base_name}_page_{i+1}.pdf")
                with open(out_path, "wb") as f:
                    writer.write(f)
                self.log.insert("end", f"Creato: {out_path}\n")

            self.log.see("end")
            self.status_label.config(text="Divisione per pagina completata.")
        except Exception as e:
            messagebox.showerror("Errore", str(e))
            self.log.insert("end", f"ERRORE divisione per pagina: {e}\n")
            self.log.see("end")
            self.status_label.config(text="Errore durante la divisione per pagina.")

    def extract_pages(self):
        try:
            path, reader = self._get_single_pdf_and_reader()
            max_pages = len(reader.pages)
            spec = self.extract_entry.get_value().strip()
            if not spec:
                raise ValueError("Inserisci le pagine da estrarre.")
            pages = parse_page_spec(spec, max_pages)
            if not pages:
                raise ValueError("Nessuna pagina valida da estrarre.")
            out_path = filedialog.asksaveasfilename(defaultextension=".pdf",
                                                    filetypes=[("PDF", "*.pdf")],
                                                    title="Salva PDF estratto")
            if not out_path:
                return
            writer = PdfWriter()
            for p in pages:
                writer.add_page(reader.pages[p])
            with open(out_path, "wb") as f:
                writer.write(f)
            self.log.insert("end", f"Pagine estratte in: {out_path}\n")
            self.log.see("end")
            self.status_label.config(text="Estrazione completata.")
        except Exception as e:
            messagebox.showerror("Errore", str(e))
            self.log.insert("end", f"ERRORE estrazione: {e}\n")
            self.log.see("end")
            self.status_label.config(text="Errore durante l'estrazione.")

    def delete_pages(self):
        try:
            path, reader = self._get_single_pdf_and_reader()
            max_pages = len(reader.pages)
            spec = self.delete_entry.get_value().strip()
            if not spec:
                raise ValueError("Inserisci le pagine da eliminare.")
            to_delete = set(parse_page_spec(spec, max_pages))
            out_path = filedialog.asksaveasfilename(defaultextension=".pdf",
                                                    filetypes=[("PDF", "*.pdf")],
                                                    title="Salva PDF modificato")
            if not out_path:
                return
            writer = PdfWriter()
            for i in range(max_pages):
                if i not in to_delete:
                    writer.add_page(reader.pages[i])
            with open(out_path, "wb") as f:
                writer.write(f)
            self.log.insert("end", f"Pagine eliminate. Nuovo PDF: {out_path}\n")
            self.log.see("end")
            self.status_label.config(text="Eliminazione completata.")
        except Exception as e:
            messagebox.showerror("Errore", str(e))
            self.log.insert("end", f"ERRORE eliminazione: {e}\n")
            self.log.see("end")
            self.status_label.config(text="Errore durante l'eliminazione.")

    # ========================================================
    #  RIORDINO GRAFICO DELLE PAGINE
    # ========================================================

    def load_pages_for_reorder(self):
        try:
            path, reader = self._get_single_pdf_and_reader()
            max_pages = len(reader.pages)

            self._reorder_reader = reader
            self._reorder_path = path

            self.page_tree.delete(*self.page_tree.get_children())
            for i in range(max_pages):
                self.page_tree.insert("", "end", values=(i+1, f"Pagina {i+1}"))

            self.status_label.config(text="Pagine caricate per riordino.")
            self.log.insert("end", f"Caricate {max_pages} pagine da {path}\n")
            self.log.see("end")
        except Exception as e:
            messagebox.showerror("Errore", str(e))

    def move_page_up(self):
        selected = self.page_tree.selection()
        if not selected:
            return
        item = selected[0]
        index = self.page_tree.index(item)
        if index == 0:
            return
        self.page_tree.move(item, "", index - 1)

    def move_page_down(self):
        selected = self.page_tree.selection()
        if not selected:
            return
        item = selected[0]
        index = self.page_tree.index(item)
        if index == len(self.page_tree.get_children()) - 1:
            return
        self.page_tree.move(item, "", index + 1)

    def apply_reordered_pages(self):
        try:
            children = self.page_tree.get_children()
            if not children:
                raise ValueError("Nessuna pagina caricata.")
            if self._reorder_reader is None or self._reorder_path is None:
                raise ValueError("Nessun PDF caricato per il riordino.")

            reader = self._reorder_reader
            path = self._reorder_path

            new_order = []
            for item in children:
                page_num = int(self.page_tree.item(item, "values")[0]) - 1
                new_order.append(page_num)

            out_path = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                filetypes=[("PDF", "*.pdf")],
                title="Salva PDF riordinato"
            )
            if not out_path:
                return

            writer = PdfWriter()
            for p in new_order:
                writer.add_page(reader.pages[p])

            with open(out_path, "wb") as f:
                writer.write(f)

            self.log.insert("end", f"PDF riordinato salvato come: {out_path}\n")
            self.log.see("end")
            self.status_label.config(text="Riordino completato.")
        except Exception as e:
            messagebox.showerror("Errore", str(e))
            self.log.insert("end", f"ERRORE riordino: {e}\n")
            self.log.see("end")


# ============================================================
#  AVVIO
# ============================================================

if __name__ == "__main__":
    app = PDFManagerApp()
    app.mainloop()