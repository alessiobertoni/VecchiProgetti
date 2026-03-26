import os
import tempfile
from tkinter import *
from tkinter import filedialog, simpledialog, messagebox
from PIL import Image, ImageTk
from pdf2image import convert_from_path
from reportlab.pdfgen import canvas
from reportlab.lib.colors import red, blue, green, black
from pypdf import PdfReader, PdfWriter

# ---------------------------------------------------------
# Conversioni mm <-> pt
# ---------------------------------------------------------
def mm_to_pt(mm):
    return mm * 2.83464567

def pt_to_mm(pt):
    return pt / 2.83464567

# ---------------------------------------------------------
# Mappa colori
# ---------------------------------------------------------
COLOR_MAP = {
    "rosso": red,
    "blu": blue,
    "verde": green,
    "nero": black
}

# ---------------------------------------------------------
# Generatore etichette A, B, C, ..., Z, AA, AB, ...
# ---------------------------------------------------------
def index_to_label(index):
    label = ""
    index += 1
    while index > 0:
        index, rem = divmod(index - 1, 26)
        label = chr(65 + rem) + label
    return label

# ---------------------------------------------------------
# CLASSE PRINCIPALE
# ---------------------------------------------------------
class DimaWizardApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Dima PDF Wizard")
        self.root.geometry("1200x700")

        # PDF caricato
        self.pdf_path = None

        # Lista rettangoli
        self.rectangles = []
        self.next_index = 0

        # Zoom e pan
        self.zoom = 1.0
        self.image_id = None
        self.pan_start = None
        self.current_image = None

        # Overlay debug ON/OFF
        self.debug_overlay = False
        self.debug_points = []   # punti del testo
        self.debug_rects = []    # rettangoli calcolati

        # ---------------------------------------------------------
        # AREA ANTEPRIMA
        # ---------------------------------------------------------
        self.preview_frame = Frame(root, bg="white")
        self.preview_frame.pack(side=LEFT, fill=BOTH, expand=True)

        self.canvas = Canvas(self.preview_frame, bg="white")
        self.canvas.pack(fill=BOTH, expand=True)

        # Zoom
        self.canvas.bind("<MouseWheel>", self.on_zoom)
        self.canvas.bind("<Button-4>", self.on_zoom)
        self.canvas.bind("<Button-5>", self.on_zoom)

        # Pan
        self.canvas.bind("<ButtonPress-1>", self.start_pan)
        self.canvas.bind("<B1-Motion>", self.do_pan)

        # ---------------------------------------------------------
        # AREA CONTROLLI
        # ---------------------------------------------------------
        self.controls = Frame(root, width=300, padx=10, pady=10)
        self.controls.pack(side=RIGHT, fill=Y)

        Button(self.controls, text="Carica PDF", width=20, command=self.load_pdf).pack(pady=10)
        Button(self.controls, text="Aggiungi rettangolo", width=20, command=self.ask_add_rectangle).pack(pady=10)
        Button(self.controls, text="Elimina rettangolo", width=20, command=self.delete_rectangle).pack(pady=10)
        Button(self.controls, text="Esporta PDF finale", width=20, command=self.export_pdf).pack(pady=20)

        # 🔥 Pulsante overlay debug
        Button(self.controls, text="Toggle Debug Overlay", width=20, command=self.toggle_debug).pack(pady=20)
            # ---------------------------------------------------------
    # ESTRAZIONE POSIZIONI TESTO (pypdf)
    # ---------------------------------------------------------
    def extract_text_positions(self, page):
        items = []

        def visitor(text, cm, tm, font_dict, font_size):
            # Matrice completa: posizione reale del testo
            real_x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            real_y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]

            # Larghezza approssimata del testo (funziona molto bene)
            # 0.5 * font_size ≈ larghezza media di un carattere
            text_width = len(text) * font_size * 0.5

            # Altezza del testo
            text_height = font_size

            items.append({
                "text": text,
                "x": real_x,
                "y": real_y,
                "w": text_width,
                "h": text_height
            })

        page.extract_text(visitor_text=visitor)
        return items
    # ---------------------------------------------------------
    # COORDINATE UNIFICATE (disegno + detection)
    # ---------------------------------------------------------
    def get_rect_pdf_coords(self, rect, page_width, page_height):
        # Y
        if rect["vert_side"] == "top":
            y = page_height - rect["vert_value"] - rect["height"]
        else:
            y = rect["vert_value"]

        # X
        if rect["horiz_side"] == "left":
            x = rect["horiz_value"]
        else:
            x = page_width - rect["horiz_value"] - rect["width"]

        return x, y

    # ---------------------------------------------------------
    # DETECTION TESTO (con tolleranza migliorata)
    # ---------------------------------------------------------
    def rectangle_contains_text(self, rect, text_items, page_height, page_width):
        x, y = self.get_rect_pdf_coords(rect, page_width, page_height)

        rect_left = x
        rect_right = x + rect["width"]
        rect_bottom = y
        rect_top = y + rect["height"]

        tol = 2.0  # tolleranza

        found = False
        self.debug_points = []

        for t in text_items:
            tx = t["x"]
            ty = t["y"]
            tw = t["w"]
            th = t["h"]

            # Bounding box del testo
            text_left = tx
            text_right = tx + tw
            text_bottom = ty
            text_top = ty + th

            # Salva punto debug
            self.debug_points.append((tx, ty))

            # Controllo sovrapposizione rettangolo <-> testo
            overlap = not (
                text_right < rect_left - tol or
                text_left > rect_right + tol or
                text_top < rect_bottom - tol or
                text_bottom > rect_top + tol
            )

            if overlap:
                found = True

        return found

    # ---------------------------------------------------------
    # PATTERN PUNTINATO (compatibile con tutte le versioni)
    # ---------------------------------------------------------
    def draw_dotted_pattern(self, c, x, y, w, h, color):
        c.saveState()
        c.setFillColor(color)

        step = 6       # distanza tra puntini
        dot_size = 1 # raggio puntino

        xx = x
        while xx < x + w:
            yy = y
            while yy < y + h:
                c.circle(xx, yy, dot_size, fill=1, stroke=0)
                yy += step
            xx += step

        c.restoreState()
            # ---------------------------------------------------------
    # OVERLAY DEBUG: disegna punti del testo e rettangoli calcolati
    # ---------------------------------------------------------
    def draw_debug_overlay(self):
        if not self.debug_overlay:
            return

        # Cancella overlay precedente
        self.canvas.delete("debug")

        # Disegna punti del testo
        for (tx, ty) in self.debug_points:
            # Applica zoom
            zx = tx * self.zoom
            zy = ty * self.zoom
            r = 3
            self.canvas.create_oval(
                zx - r, zy - r, zx + r, zy + r,
                fill="red", outline="", tags="debug"
            )

        # Disegna rettangoli calcolati
        for rect in self.debug_rects:
            x, y, w, h = rect
            zx = x * self.zoom
            zy = y * self.zoom
            zw = w * self.zoom
            zh = h * self.zoom

            self.canvas.create_rectangle(
                zx, zy, zx + zw, zy + zh,
                outline="blue", width=2, tags="debug"
            )

    # ---------------------------------------------------------
    # TOGGLE OVERLAY DEBUG
    # ---------------------------------------------------------
    def toggle_debug(self):
        self.debug_overlay = not self.debug_overlay
        self.update_preview()
            # ---------------------------------------------------------
    # CARICA PDF
    # ---------------------------------------------------------
    def load_pdf(self):
        self.pdf_path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if not self.pdf_path:
            return

        # Reset stato
        self.rectangles = []
        self.next_index = 0
        self.zoom = 1.0
        self.debug_points = []
        self.debug_rects = []

        reader = PdfReader(self.pdf_path)
        page = reader.pages[0]

        page_width_pt = float(page.mediabox.width)
        page_height_pt = float(page.mediabox.height)

        page_width_mm = pt_to_mm(page_width_pt)
        page_height_mm = pt_to_mm(page_height_pt)

        # Rettangolo base (pagina intera)
        label = index_to_label(self.next_index)

        self.rectangles.append({
            "label": label,
            "width": page_width_pt,
            "height": page_height_pt,
            "width_mm": page_width_mm,
            "height_mm": page_height_mm,
            "vert_side": "top",
            "vert_value": 0,
            "vert_value_mm": 0,
            "horiz_side": "left",
            "horiz_value": 0,
            "horiz_value_mm": 0,
            "color": "nero",
            "text_position": "left",
            "fill_soft": False
        })

        self.next_index += 1

        # Estrai punti testo per overlay debug
        self.debug_points = self.extract_text_positions(page)

        self.update_preview()
        self.ask_add_rectangle()

    # ---------------------------------------------------------
    # WIZARD AGGIUNTA RETTANGOLO
    # ---------------------------------------------------------
    def ask_add_rectangle(self):
        if not self.pdf_path:
            messagebox.showwarning("Attenzione", "Carica prima un PDF.")
            return

        risposta = messagebox.askyesno("Aggiungi rettangolo", "Vuoi aggiungere un rettangolo?")
        if not risposta:
            return

        reader = PdfReader(self.pdf_path)
        page = reader.pages[0]

        page_width_mm = pt_to_mm(float(page.mediabox.width))
        page_height_mm = pt_to_mm(float(page.mediabox.height))

        # --- Dimensioni ---
        larghezza_mm = self.ask_limited_float(
            "Dimensioni",
            "Larghezza del rettangolo (mm):",
            page_width_mm
        )
        if larghezza_mm is None:
            return

        altezza_mm = self.ask_limited_float(
            "Dimensioni",
            "Altezza del rettangolo (mm):",
            page_height_mm
        )
        if altezza_mm is None:
            return

        # --- Posizione ---
        pos = self.ask_position(page_width_mm, page_height_mm)
        if pos is None:
            return

        # --- Colore ---
        colore = self.ask_color()

        # --- Posizione testo ---
        text_pos = self.ask_text_position()

        label = index_to_label(self.next_index)

        new_rect = {
            "label": label,
            "width": mm_to_pt(larghezza_mm),
            "height": mm_to_pt(altezza_mm),
            "width_mm": larghezza_mm,
            "height_mm": altezza_mm,
            "vert_side": pos["vert_side"],
            "vert_value": mm_to_pt(pos["vert_value"]),
            "vert_value_mm": pos["vert_value"],
            "horiz_side": pos["horiz_side"],
            "horiz_value": mm_to_pt(pos["horiz_value"]),
            "horiz_value_mm": pos["horiz_value"],
            "color": colore,
            "text_position": text_pos,
            "fill_soft": False
        }

        self.rectangles.append(new_rect)
        self.next_index += 1

        # --- Rilevamento testo ---
        text_items = self.extract_text_positions(page)

        contains_text = self.rectangle_contains_text(
            new_rect,
            text_items,
            float(page.mediabox.height),
            float(page.mediabox.width)
        )

        if contains_text:
            risposta = messagebox.askyesno(
                "Testo rilevato",
                "In quest'area è presente del testo.\nVuoi evidenziarlo?"
            )
            if risposta:
                new_rect["fill_soft"] = True

        # Salva rettangolo per overlay debug
        x, y = self.get_rect_pdf_coords(
            new_rect,
            float(page.mediabox.width),
            float(page.mediabox.height)
        )
        self.debug_rects.append((x, y, new_rect["width"], new_rect["height"]))

        self.update_preview()
        self.ask_add_rectangle()
            # ---------------------------------------------------------
    # FINESTRA POSIZIONE (corretta per Windows 11)
    # ---------------------------------------------------------
    def ask_position(self, page_width_mm, page_height_mm):
        win = Toplevel(self.root)
        win.title("Posizione del rettangolo")
        win.geometry("300x250")

        # --- Fix definitivo per finestre dietro ---
        win.transient(self.root)
        win.grab_set()
        win.after(10, win.lift)
        win.after(10, lambda: win.attributes("-topmost", True))
        win.after(200, lambda: win.attributes("-topmost", False))

        vert_choice = StringVar(value="top")
        horiz_choice = StringVar(value="left")

        Label(win, text="Posizione verticale").pack(pady=5)
        Radiobutton(win, text="Distanza dall'alto", variable=vert_choice, value="top").pack()
        Radiobutton(win, text="Distanza dal basso", variable=vert_choice, value="bottom").pack()

        Label(win, text="Posizione orizzontale").pack(pady=10)
        Radiobutton(win, text="Distanza da sinistra", variable=horiz_choice, value="left").pack()
        Radiobutton(win, text="Distanza da destra", variable=horiz_choice, value="right").pack()

        result = {}

        def confirm():
            result["vert_side"] = vert_choice.get()
            result["horiz_side"] = horiz_choice.get()
            win.destroy()

        Button(win, text="Conferma", command=confirm).pack(pady=15)
        win.wait_window()

        if not result:
            return None

        # --- Valore verticale ---
        if result["vert_side"] == "top":
            vert_prompt = "Distanza dall'alto (mm):"
            vert_max = page_height_mm
        else:
            vert_prompt = "Distanza dal basso (mm):"
            vert_max = page_height_mm

        vert_value_mm = self.ask_limited_float(
            "Posizione verticale",
            vert_prompt,
            vert_max
        )
        if vert_value_mm is None:
            return None

        # --- Valore orizzontale ---
        if result["horiz_side"] == "left":
            horiz_prompt = "Distanza da sinistra (mm):"
            horiz_max = page_width_mm
        else:
            horiz_prompt = "Distanza da destra (mm):"
            horiz_max = page_width_mm

        horiz_value_mm = self.ask_limited_float(
            "Posizione orizzontale",
            horiz_prompt,
            horiz_max
        )
        if horiz_value_mm is None:
            return None

        result["vert_value"] = vert_value_mm
        result["horiz_value"] = horiz_value_mm
        return result
    # ---------------------------------------------------------
    # INPUT CON LIMITE (mm)
    # ---------------------------------------------------------
    def ask_limited_float(self, title, prompt_base, max_value_mm):
        win = Toplevel(self.root)
        win.title(title)
        win.geometry("300x150")

        # Fix finestre dietro
        win.transient(self.root)
        win.grab_set()
        win.after(10, win.lift)
        win.after(10, lambda: win.attributes("-topmost", True))
        win.after(200, lambda: win.attributes("-topmost", False))

        Label(win, text=f"{prompt_base}\n(Max: {max_value_mm:.1f} mm)").pack(pady=10)

        value_var = StringVar()
        entry = Entry(win, textvariable=value_var)
        entry.pack(pady=5)
        entry.focus()

        result = {"value": None}

        def confirm():
            try:
                v = float(value_var.get())
                if v < 0:
                    messagebox.showerror("Valore non valido", "Il valore non può essere negativo.")
                    return
                if v > max_value_mm:
                    messagebox.showerror("Valore troppo grande", f"Massimo: {max_value_mm:.1f} mm")
                    return
                result["value"] = v
                win.destroy()
            except:
                messagebox.showerror("Errore", "Inserisci un numero valido.")

        Button(win, text="OK", command=confirm).pack(pady=10)
        win.wait_window()

        return result["value"]
    # ---------------------------------------------------------
    # FINESTRA COLORE (corretta per Windows 11)
    # ---------------------------------------------------------
    def ask_color(self):
        win = Toplevel(self.root)
        win.title("Colore del rettangolo")
        win.geometry("250x150")

        # --- Fix definitivo ---
        win.transient(self.root)
        win.grab_set()
        win.after(10, win.lift)
        win.after(10, lambda: win.attributes("-topmost", True))
        win.after(200, lambda: win.attributes("-topmost", False))

        color_choice = StringVar(value="rosso")

        Label(win, text="Scegli il colore").pack(pady=5)
        Radiobutton(win, text="Rosso", variable=color_choice, value="rosso").pack()
        Radiobutton(win, text="Blu", variable=color_choice, value="blu").pack()
        Radiobutton(win, text="Verde", variable=color_choice, value="verde").pack()

        def confirm():
            win.destroy()

        Button(win, text="Conferma", command=confirm).pack(pady=10)
        win.wait_window()
        return color_choice.get()

    # ---------------------------------------------------------
    # FINESTRA POSIZIONE TESTO (corretta per Windows 11)
    # ---------------------------------------------------------
    def ask_text_position(self):
        win = Toplevel(self.root)
        win.title("Posizione del testo")
        win.geometry("250x150")

        # --- Fix definitivo ---
        win.transient(self.root)
        win.grab_set()
        win.after(10, win.lift)
        win.after(10, lambda: win.attributes("-topmost", True))
        win.after(200, lambda: win.attributes("-topmost", False))

        choice = StringVar(value="left")

        Label(win, text="Dove vuoi posizionare la scritta?").pack(pady=5)
        Radiobutton(win, text="A sinistra", variable=choice, value="left").pack()
        Radiobutton(win, text="A destra", variable=choice, value="right").pack()

        def confirm():
            win.destroy()

        Button(win, text="Conferma", command=confirm).pack(pady=10)
        win.wait_window()
        return choice.get()
            # ---------------------------------------------------------
    # ELIMINA RETTANGOLO
    # ---------------------------------------------------------
    def delete_rectangle(self):
        if not self.rectangles:
            messagebox.showinfo("Nessun rettangolo", "Non ci sono rettangoli da eliminare.")
            return

        id_to_delete = simpledialog.askstring(
            "Elimina rettangolo",
            "Inserisci la lettera del rettangolo da eliminare (es. A, B, AA):"
        )
        if id_to_delete is None:
            return

        id_to_delete = id_to_delete.strip().upper()
        if not id_to_delete:
            return

        original_len = len(self.rectangles)
        self.rectangles = [r for r in self.rectangles if r["label"] != id_to_delete]

        if len(self.rectangles) < original_len:
            messagebox.showinfo("Eliminato", f"Rettangolo {id_to_delete} eliminato.")
        else:
            messagebox.showwarning("Non trovato", f"Nessun rettangolo con lettera {id_to_delete}.")

        # Aggiorna overlay debug
        self.debug_rects = []
        reader = PdfReader(self.pdf_path)
        page = reader.pages[0]
        pw = float(page.mediabox.width)
        ph = float(page.mediabox.height)

        for r in self.rectangles:
            x, y = self.get_rect_pdf_coords(r, pw, ph)
            self.debug_rects.append((x, y, r["width"], r["height"]))

        self.update_preview()

    # ---------------------------------------------------------
    # GENERA DIMA (PDF con rettangoli e pattern)
    # ---------------------------------------------------------
    def genera_dima(self, width, height):
        temp_dima = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        c = canvas.Canvas(temp_dima.name, pagesize=(width, height))

        self.debug_rects = []  # reset overlay rettangoli

        for r in self.rectangles:
            color = COLOR_MAP.get(r["color"], red)
            c.setStrokeColor(color)
            c.setLineWidth(1)

            # Coordinate PDF
            x, y = self.get_rect_pdf_coords(r, width, height)

            # Salva per overlay debug
            self.debug_rects.append((x, y, r["width"], r["height"]))

            # Riempimento puntinato
            if r.get("fill_soft", False):
                self.draw_dotted_pattern(c, x, y, r["width"], r["height"], color)

            # Bordo
            c.setStrokeColor(color)
            c.rect(x, y, r["width"], r["height"], fill=0, stroke=1)

            # Testo descrittivo
            c.setFillColor(color)
            c.setFont("Helvetica", 10)

            main_text = f"{r['label']} - {r['width_mm']:.0f} mm x {r['height_mm']:.0f} mm"

            vert_label = "dall'alto" if r["vert_side"] == "top" else "dal basso"
            horiz_label = "da sinistra" if r["horiz_side"] == "left" else "da destra"

            pos_text_1 = f"{r['vert_value_mm']:.0f} mm {vert_label}"
            pos_text_2 = f"{r['horiz_value_mm']:.0f} mm {horiz_label}"

            # Posizione testo
            if r["text_position"] == "left":
                text_x = x + 2
            else:
                max_len = max(len(main_text), len(pos_text_1), len(pos_text_2))
                approx_width = max_len * 4
                text_x = x + r["width"] - approx_width - 2

            # Disegna testo
            c.drawString(text_x, y + 4, pos_text_2)
            c.drawString(text_x, y + 16, pos_text_1)
            c.drawString(text_x, y + 28, main_text)

            c.setFillColorRGB(0, 0, 0)

        c.save()
        return temp_dima.name
            # ---------------------------------------------------------
    # AGGIORNA ANTEPRIMA PDF
    # ---------------------------------------------------------
    def update_preview(self):
        if not self.pdf_path:
            return

        reader = PdfReader(self.pdf_path)
        page = reader.pages[0]
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)

        # Se non ci sono rettangoli → mostra solo il PDF originale
        if not self.rectangles:
            temp_output = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            writer = PdfWriter()
            writer.add_page(page)

            with open(temp_output.name, "wb") as f:
                writer.write(f)

            img = convert_from_path(temp_output.name, dpi=120)[0]

        else:
            # Genera dima con rettangoli
            dima_pdf = self.genera_dima(width, height)

            temp_output = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            writer = PdfWriter()
            page_copy = reader.pages[0]
            dima_page = PdfReader(dima_pdf).pages[0]
            page_copy.merge_page(dima_page)
            writer.add_page(page_copy)

            with open(temp_output.name, "wb") as f:
                writer.write(f)

            img = convert_from_path(temp_output.name, dpi=120)[0]

        self.current_image = img
        self.redraw_image()

    # ---------------------------------------------------------
    # REDISEGNA IMMAGINE (applica zoom + overlay)
    # ---------------------------------------------------------
    def redraw_image(self):
        if self.current_image is None:
            return

        w, h = self.current_image.size
        new_size = (int(w * self.zoom), int(h * self.zoom))
        resized = self.current_image.resize(new_size, Image.LANCZOS)

        self.tk_image = ImageTk.PhotoImage(resized)

        self.canvas.delete("all")
        self.image_id = self.canvas.create_image(0, 0, anchor="nw", image=self.tk_image)
        self.canvas.config(scrollregion=self.canvas.bbox(ALL))

        # 🔥 Disegna overlay debug
        self.draw_debug_overlay()

    # ---------------------------------------------------------
    # ZOOM
    # ---------------------------------------------------------
    def on_zoom(self, event):
        if event.delta > 0 or getattr(event, "num", None) == 4:
            self.zoom *= 1.1
        else:
            self.zoom /= 1.1

        self.zoom = max(0.2, min(self.zoom, 5.0))
        self.redraw_image()

    # ---------------------------------------------------------
    # PAN
    # ---------------------------------------------------------
    def start_pan(self, event):
        self.pan_start = (event.x, event.y)

    def do_pan(self, event):
        if self.pan_start and self.image_id is not None:
            dx = event.x - self.pan_start[0]
            dy = event.y - self.pan_start[1]
            self.canvas.move(self.image_id, dx, dy)

            # Muove anche l’overlay
            for item in self.canvas.find_withtag("debug"):
                self.canvas.move(item, dx, dy)

            self.pan_start = (event.x, event.y)
                # ---------------------------------------------------------
    # ESPORTA PDF FINALE
    # ---------------------------------------------------------
    def export_pdf(self):
        if not self.pdf_path:
            return

        save_path = filedialog.asksaveasfilename(defaultextension=".pdf")
        if not save_path:
            return

        reader = PdfReader(self.pdf_path)
        writer = PdfWriter()

        for page in reader.pages:
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)

            # Genera la dima per questa pagina
            dima_pdf = self.genera_dima(width, height)
            dima_page = PdfReader(dima_pdf).pages[0]

            # Unisci dima + pagina originale
            page.merge_page(dima_page)
            writer.add_page(page)

        with open(save_path, "wb") as f:
            writer.write(f)

        messagebox.showinfo("Esportazione completata", "PDF esportato con successo!")
            # ---------------------------------------------------------
    # TOGGLE DEBUG OVERLAY (attiva/disattiva)
    # ---------------------------------------------------------
    def toggle_debug(self):
        self.debug_overlay = not self.debug_overlay

        if not self.debug_overlay:
            # Cancella overlay quando disattivato
            self.canvas.delete("debug")

        # Aggiorna anteprima
        self.update_preview()
        # ---------------------------------------------------------
# AVVIO APP
# ---------------------------------------------------------
if __name__ == "__main__":
    root = Tk()
    app = DimaWizardApp(root)
    root.mainloop()
        
        