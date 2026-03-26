import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from reportlab.pdfgen import canvas
from PyPDF2 import PdfReader, PdfWriter


# ============================================================
#  UTILITÀ PDF
# ============================================================

def mm_to_points(mm: float) -> float:
    return mm * 2.83465


def annotate_pdf(input_path: str, output_path: str, text: str, x_mm: float, y_mm: float, color_name: str):
    reader = PdfReader(input_path)
    writer = PdfWriter()

    first_page = reader.pages[0]
    media_box = first_page.mediabox
    width = float(media_box.width)
    height = float(media_box.height)

    # overlay nella stessa cartella del PDF
    temp_overlay = os.path.join(os.path.dirname(input_path), "_overlay_tmp.pdf")

    # crea overlay con stessa dimensione della pagina
    c = canvas.Canvas(temp_overlay, pagesize=(width, height))

    colors = {
        "Nero": (0, 0, 0),
        "Blu": (0, 0, 1),
        "Rosso": (1, 0, 0),
        "Verde": (0, 1, 0),
    }
    r, g, b = colors.get(color_name, (0, 0, 0))
    c.setFillColorRGB(r, g, b)
    c.setFont("Helvetica", 12)

    x_pt = mm_to_points(x_mm)
    y_pt = height - mm_to_points(y_mm)

    c.drawString(x_pt, y_pt, text)
    c.save()

    overlay_reader = PdfReader(temp_overlay)
    overlay_page = overlay_reader.pages[0]

    base_page = reader.pages[0]
    base_page.merge_page(overlay_page)
    writer.add_page(base_page)

    # eventuali altre pagine copiate senza modifiche
    for i in range(1, len(reader.pages)):
        writer.add_page(reader.pages[i])

    with open(output_path, "wb") as f:
        writer.write(f)

    if os.path.exists(temp_overlay):
        os.remove(temp_overlay)


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
#  APP PRINCIPALE
# ============================================================

class PDFAnnotationApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PDF Annotation Studio - Dark Elegant")
        self.geometry("1100x700")
        self.minsize(900, 600)

        setup_dark_theme(self)
        self._build_layout()
        self.show_annotate_view()

    # ---------------- Layout base ----------------

    def _build_layout(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Header
        header = ttk.Frame(self, style="Header.TFrame")
        header.grid(row=0, column=0, columnspan=2, sticky="nsew")
        ttk.Label(header, text="PDF Annotation Studio", style="Title.TLabel").grid(row=0, column=0, padx=16, pady=10, sticky="w")

        # Sidebar
        sidebar = ttk.Frame(self, style="Sidebar.TFrame")
        sidebar.grid(row=1, column=0, sticky="nsew")
        sidebar.grid_rowconfigure(10, weight=1)

        ttk.Button(sidebar, text="Annota PDF", style="Sidebar.TButton",
                   command=self.show_annotate_view).grid(row=0, column=0, sticky="ew")
        ttk.Button(sidebar, text="Impostazioni", style="Sidebar.TButton",
                   command=self.show_settings_view).grid(row=1, column=0, sticky="ew")

        # Area principale
        self.main_area = ttk.Frame(self, style="TFrame")
        self.main_area.grid(row=1, column=1, sticky="nsew")

        # Footer
        footer = ttk.Frame(self, style="Footer.TFrame")
        footer.grid(row=2, column=0, columnspan=2, sticky="nsew")
        footer.grid_columnconfigure(0, weight=1)
        self.status_label = ttk.Label(footer, text="Pronto.", style="Secondary.TLabel")
        self.status_label.grid(row=0, column=0, padx=16, pady=6, sticky="w")

    def _clear_main(self):
        for w in self.main_area.winfo_children():
            w.destroy()

    # ---------------- Vista: Annotazione ----------------

    def show_annotate_view(self):
        self._clear_main()
        self.status_label.config(text="Modalità annotazione PDF.")

        panel = ttk.Frame(self.main_area, style="Panel.TFrame")
        panel.pack(fill="both", expand=True, padx=16, pady=16)

        ttk.Label(panel, text="Annota PDF", style="SectionTitle.TLabel").pack(anchor="w", padx=16, pady=(16, 8))

        # Percorso PDF
        path_frame = ttk.Frame(panel, style="Panel.TFrame")
        path_frame.pack(fill="x", padx=16, pady=8)

        self.pdf_entry = PlaceholderEntry(path_frame, placeholder="Percorso del file PDF")
        self.pdf_entry.pack(side="left", fill="x", expand=True, padx=8, pady=8)

        ttk.Button(path_frame, text="Sfoglia...", command=self._browse_pdf).pack(side="right", padx=8, pady=8)

        # Testo annotazione
        self.text_entry = PlaceholderEntry(panel, placeholder="Testo dell'annotazione")
        self.text_entry.pack(fill="x", padx=16, pady=8)

        # Posizione
        pos_frame = ttk.Frame(panel, style="Panel.TFrame")
        pos_frame.pack(fill="x", padx=16, pady=8)

        ttk.Label(pos_frame, text="X (mm):", style="Secondary.TLabel").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self.x_entry = PlaceholderEntry(pos_frame, placeholder="es. 10")
        self.x_entry.grid(row=0, column=1, padx=8, pady=8, sticky="ew")

        ttk.Label(pos_frame, text="Y (mm):", style="Secondary.TLabel").grid(row=1, column=0, padx=8, pady=8, sticky="w")
        self.y_entry = PlaceholderEntry(pos_frame, placeholder="es. 20")
        self.y_entry.grid(row=1, column=1, padx=8, pady=8, sticky="ew")

        pos_frame.grid_columnconfigure(1, weight=1)

        # Colore
        ttk.Label(panel, text="Colore:", style="TLabel").pack(anchor="w", padx=16, pady=(8, 2))
        self.color_combo = ttk.Combobox(panel, values=["Nero", "Blu", "Rosso", "Verde"], state="readonly")
        self.color_combo.set("Blu")
        self.color_combo.pack(fill="x", padx=16, pady=(0, 8))

        # Pulsante applica
        ttk.Button(panel, text="Applica annotazione", style="Primary.TButton",
                   command=self._apply_annotation).pack(anchor="w", padx=16, pady=16)

        # Log
        self.log = tk.Text(panel, height=10, bg="#1E1E1E", fg="#C8C8C8",
                           insertbackground="#FFFFFF", relief="flat", wrap="word")
        self.log.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.log.insert("end", "Log operazioni:\n")

    # ---------------- Vista: Impostazioni ----------------

    def show_settings_view(self):
        self._clear_main()
        self.status_label.config(text="Impostazioni aperte.")

        panel = ttk.Frame(self.main_area, style="Panel.TFrame")
        panel.pack(fill="both", expand=True, padx=16, pady=16)

        ttk.Label(panel, text="Impostazioni", style="SectionTitle.TLabel").pack(anchor="w", padx=16, pady=(16, 8))
        ttk.Label(panel, text="Tema attuale: Scuro elegante", style="Secondary.TLabel").pack(anchor="w", padx=16, pady=4)
        ttk.Label(panel, text="Unità di misura: mm", style="Secondary.TLabel").pack(anchor="w", padx=16, pady=4)

    # ---------------- Azioni ----------------

    def _browse_pdf(self):
        path = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if path:
            self.pdf_entry._clear()
            self.pdf_entry.delete(0, tk.END)
            self.pdf_entry.insert(0, path)

    def _apply_annotation(self):
        try:
            pdf_path = self.pdf_entry.get_value().strip()
            text = self.text_entry.get_value().strip()
            x_str = self.x_entry.get_value().strip()
            y_str = self.y_entry.get_value().strip()
            color = self.color_combo.get()

            if not pdf_path:
                raise ValueError("Seleziona un file PDF.")
            if not os.path.exists(pdf_path):
                raise FileNotFoundError("Il file PDF selezionato non esiste.")
            if not text:
                raise ValueError("Inserisci il testo dell'annotazione.")
            if not x_str or not y_str:
                raise ValueError("Inserisci le coordinate X e Y in mm.")

            try:
                x_mm = float(x_str.replace(",", "."))
                y_mm = float(y_str.replace(",", "."))
            except ValueError:
                raise ValueError("Le coordinate X e Y devono essere numeriche.")

            output_path = pdf_path[:-4] + "_annotato.pdf"

            annotate_pdf(pdf_path, output_path, text, x_mm, y_mm, color)

            msg = f"Annotazione applicata.\nFile salvato come:\n{output_path}\n\n"
            self.log.insert("end", msg)
            self.log.see("end")
            self.status_label.config(text="Annotazione completata.")

        except Exception as e:
            messagebox.showerror("Errore", str(e))
            self.log.insert("end", f"ERRORE: {e}\n")
            self.log.see("end")
            self.status_label.config(text="Errore durante l'annotazione.")


# ============================================================
#  AVVIO
# ============================================================

if __name__ == "__main__":
    app = PDFAnnotationApp()
    app.mainloop()