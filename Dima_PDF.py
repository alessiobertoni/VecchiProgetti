import os
import tempfile
from tkinter import *
from tkinter import filedialog, simpledialog, messagebox
from PIL import Image, ImageTk
from pdf2image import convert_from_path
from reportlab.pdfgen import canvas
from reportlab.lib.colors import red, blue, green, black
from pypdf import PdfReader, PdfWriter


def mm_to_pt(mm):
    return mm * 2.83464567


def pt_to_mm(pt):
    return pt / 2.83464567


COLOR_MAP = {
    "rosso": red,
    "blu": blue,
    "verde": green,
    "nero": black
}


def index_to_label(index):
    """0 -> A, 1 -> B, ..., 25 -> Z, 26 -> AA, 27 -> AB, ..."""
    label = ""
    index += 1  # passiamo a 1-based
    while index > 0:
        index, rem = divmod(index - 1, 26)
        label = chr(65 + rem) + label
    return label


class DimaWizardApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Dima PDF Wizard")
        self.root.geometry("1200x700")

        self.pdf_path = None
        self.rectangles = []
        self.next_index = 0  # usato per generare la lettera (A, B, ...)

        # Zoom & Pan
        self.zoom = 1.0
        self.image_id = None
        self.pan_start = None
        self.current_image = None

        # Frame anteprima
        self.preview_frame = Frame(root, bg="white")
        self.preview_frame.pack(side=LEFT, fill=BOTH, expand=True)

        # Canvas per zoom e pan
        self.canvas = Canvas(self.preview_frame, bg="white")
        self.canvas.pack(fill=BOTH, expand=True)

        # Bind zoom
        self.canvas.bind("<MouseWheel>", self.on_zoom)  # Windows
        self.canvas.bind("<Button-4>", self.on_zoom)    # Linux
        self.canvas.bind("<Button-5>", self.on_zoom)    # Linux

        # Bind pan
        self.canvas.bind("<ButtonPress-1>", self.start_pan)
        self.canvas.bind("<B1-Motion>", self.do_pan)

        # Frame controlli
        self.controls = Frame(root, width=300, padx=10, pady=10)
        self.controls.pack(side=RIGHT, fill=Y)

        Button(self.controls, text="Carica PDF", command=self.load_pdf).pack(pady=10)
        Button(self.controls, text="Aggiungi rettangolo", command=self.ask_add_rectangle).pack(pady=10)
        Button(self.controls, text="Elimina rettangolo", command=self.delete_rectangle).pack(pady=10)
        Button(self.controls, text="Esporta PDF finale", command=self.export_pdf).pack(pady=20)

    # ---------------------------------------------------------
    # UTILITY: CHIEDI FLOAT CON LIMITE
    # ---------------------------------------------------------
    def ask_limited_float(self, title, prompt_base, max_value_mm):
        """
        Chiede un valore float in mm, mostra il limite e blocca valori oltre il massimo.
        Ritorna None se l'utente annulla.
        """
        while True:
            value = simpledialog.askfloat(
                title,
                f"{prompt_base}\n(Massimo consentito: {max_value_mm:.1f} mm)"
            )
            if value is None:
                return None
            if value < 0:
                messagebox.showerror("Valore non valido", "Il valore non può essere negativo.")
                continue
            if value > max_value_mm:
                messagebox.showerror(
                    "Valore troppo grande",
                    f"Valore troppo grande. Il massimo consentito è {max_value_mm:.1f} mm."
                )
                continue
            return value

    # ---------------------------------------------------------
    # CARICAMENTO PDF
    # ---------------------------------------------------------
    def load_pdf(self):
        self.pdf_path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if not self.pdf_path:
            return
     
        self.rectangles = []
        self.next_index = 0
        self.zoom = 1.0

        # Leggi dimensioni del foglio
        reader = PdfReader(self.pdf_path)
        page = reader.pages[0]
        page_width_pt = float(page.mediabox.width)
        page_height_pt = float(page.mediabox.height)

        page_width_mm = pt_to_mm(page_width_pt)
        page_height_mm = pt_to_mm(page_height_pt)

        # Crea rettangolo nero che evidenzia i limiti del foglio
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
            "text_position": "left" 
        })

        self.next_index += 1

        # Aggiorna anteprima
        self.update_preview()

        # Avvia wizard per aggiungere altri rettangoli
        self.ask_add_rectangle()

    # ---------------------------------------------------------
    # WIZARD: AGGIUNTA RETTANGOLO
    # ---------------------------------------------------------
    def ask_add_rectangle(self):
        if not self.pdf_path:
            messagebox.showwarning("Attenzione", "Carica prima un PDF.")
            return

        risposta = messagebox.askyesno("Aggiungi rettangolo", "Vuoi aggiungere un rettangolo?")
        if not risposta:
            return

        # Leggiamo dimensioni del foglio per mostrare i limiti
        reader = PdfReader(self.pdf_path)
        page = reader.pages[0]
        page_width_mm = pt_to_mm(float(page.mediabox.width))
        page_height_mm = pt_to_mm(float(page.mediabox.height))

        # Chiedi larghezza rettangolo (mm) con limite
        larghezza_mm = self.ask_limited_float(
            "Dimensioni",
            "Larghezza del rettangolo (mm):",
            page_width_mm
        )
        if larghezza_mm is None:
            return

        # Chiedi altezza rettangolo (mm) con limite
        altezza_mm = self.ask_limited_float(
            "Dimensioni",
            "Altezza del rettangolo (mm):",
            page_height_mm
        )
        if altezza_mm is None:
            return

        # Posizione (solo scelta lato nella finestra, poi valori con limiti in mm)
        pos = self.ask_position(page_width_mm, page_height_mm)
        if pos is None:
            return

        colore = self.ask_color()
        if colore not in COLOR_MAP:
            messagebox.showerror("Errore", "Colore non valido.")
            return
        
        text_pos = self.ask_text_position()

        label = index_to_label(self.next_index)

        self.rectangles.append({
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
            "text_position": text_pos
        })

        self.next_index += 1
        self.update_preview()
        self.ask_add_rectangle()

    # ---------------------------------------------------------
    # FINESTRA POSIZIONE (SCELTA LATO + RICHIESTA VALORI CON LIMITE)
    # ---------------------------------------------------------
    def ask_position(self, page_width_mm, page_height_mm):
        pos_window = Toplevel(self.root)
        pos_window.title("Posizione del rettangolo")
        pos_window.geometry("300x250")
        pos_window.grab_set()

        vert_choice = StringVar(value="top")
        horiz_choice = StringVar(value="left")

        Label(pos_window, text="Posizione verticale").pack(pady=5)
        Radiobutton(pos_window, text="Distanza dall'alto", variable=vert_choice, value="top").pack()
        Radiobutton(pos_window, text="Distanza dal basso", variable=vert_choice, value="bottom").pack()

        Label(pos_window, text="Posizione orizzontale").pack(pady=10)
        Radiobutton(pos_window, text="Distanza da sinistra", variable=horiz_choice, value="left").pack()
        Radiobutton(pos_window, text="Distanza da destra", variable=horiz_choice, value="right").pack()

        result = {}

        def confirm():
            result["vert_side"] = vert_choice.get()
            result["horiz_side"] = horiz_choice.get()
            pos_window.destroy()

        Button(pos_window, text="Conferma", command=confirm).pack(pady=15)
        pos_window.wait_window()

        if not result:
            return None

        # Dopo aver scelto i lati, chiediamo le distanze con limiti
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
    # FINESTRA COLORE
    # ---------------------------------------------------------
    def ask_color(self):
        color_window = Toplevel(self.root)
        color_window.title("Colore del rettangolo")
        color_window.geometry("250x150")
        color_window.grab_set()

        color_choice = StringVar(value="rosso")

        Label(color_window, text="Scegli il colore").pack(pady=5)
        Radiobutton(color_window, text="Rosso", variable=color_choice, value="rosso").pack()
        Radiobutton(color_window, text="Blu", variable=color_choice, value="blu").pack()
        Radiobutton(color_window, text="Verde", variable=color_choice, value="verde").pack()

        def confirm():
            color_window.destroy()

        Button(color_window, text="Conferma", command=confirm).pack(pady=10)
        color_window.wait_window()
        return color_choice.get()
    # ---------------------------------------------------------
    # POSIZIONE SCRITTA
    # ---------------------------------------------------------        
    def ask_text_position(self):
        win = Toplevel(self.root)
        win.title("Posizione del testo")
        win.geometry("250x150")
        win.grab_set()

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
    # ELIMINA RETTANGOLO (PER LETTERA)
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

        self.update_preview()

    # ---------------------------------------------------------
    # GENERA DIMA
    # ---------------------------------------------------------
    def genera_dima(self, width, height):
        temp_dima = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        c = canvas.Canvas(temp_dima.name, pagesize=(width, height))

        for r in self.rectangles:
            color = COLOR_MAP.get(r["color"], red)
            c.setStrokeColor(color)
            c.setLineWidth(1)

            # Calcolo posizione rettangolo
            if r["vert_side"] == "top":
                y = height - r["vert_value"] - r["height"]
            else:
                y = r["vert_value"]

            if r["horiz_side"] == "left":
                x = r["horiz_value"]
            else:
                x = width - r["horiz_value"] - r["width"]

            # Disegno rettangolo
            c.rect(x, y, r["width"], r["height"])

            # Testo: stesso colore del rettangolo
            c.setFillColor(color)

            # Font più grande (10 pt)
            c.setFont("Helvetica", 10)

            # Testo principale: lettera + dimensioni
            main_text = f"{r['label']} - {r['width_mm']:.0f} mm x {r['height_mm']:.0f} mm"

            # Testo posizione (in mm)
            vert_label = "dall'alto" if r["vert_side"] == "top" else "dal basso"
            horiz_label = "da sinistra" if r["horiz_side"] == "left" else "da destra"

            pos_text_1 = f"{r['vert_value_mm']:.0f} mm {vert_label}"
            pos_text_2 = f"{r['horiz_value_mm']:.0f} mm {horiz_label}"

            # Posizione testo (sinistra o destra)
            if r["text_position"] == "left":
                text_x = x + 2
            else:
                # stima larghezza massima tra le tre righe
                max_len = max(len(main_text), len(pos_text_1), len(pos_text_2))
                approx_width = max_len * 4
                text_x = x + r["width"] - approx_width - 2

            # Testo in basso nel rettangolo
            c.drawString(text_x, y + 4, pos_text_2)          # riga più bassa
            c.drawString(text_x, y + 16, pos_text_1)         # riga sopra
            c.drawString(text_x, y + 28, main_text)          # riga più alta

            # Ripristino colore di default (nero)
            c.setFillColorRGB(0, 0, 0)

        c.save()
        return temp_dima.name

    # ---------------------------------------------------------
    # ANTEPRIMA CON ZOOM + PAN
    # ---------------------------------------------------------
    def update_preview(self):
        if not self.pdf_path:
            return

        reader = PdfReader(self.pdf_path)
        page = reader.pages[0]
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)

        # Se non ci sono rettangoli → mostra solo la pagina originale
        if not self.rectangles:
            temp_output = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            writer = PdfWriter()
            writer.add_page(page)

            with open(temp_output.name, "wb") as f:
                writer.write(f)

            img = convert_from_path(temp_output.name, dpi=120)[0]

        else:
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
    # REDISEGNA IMMAGINE (APPLICA ZOOM)
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

    # ---------------------------------------------------------
    # ZOOM HANDLER
    # ---------------------------------------------------------
    def on_zoom(self, event):
        if event.delta > 0 or getattr(event, "num", None) == 4:
            self.zoom *= 1.1
        else:
            self.zoom /= 1.1

        self.zoom = max(0.2, min(self.zoom, 5.0))
        self.redraw_image()

    # ---------------------------------------------------------
    # PAN HANDLER
    # ---------------------------------------------------------
    def start_pan(self, event):
        self.pan_start = (event.x, event.y)

    def do_pan(self, event):
        if self.pan_start and self.image_id is not None:
            dx = event.x - self.pan_start[0]
            dy = event.y - self.pan_start[1]
            self.canvas.move(self.image_id, dx, dy)
            self.pan_start = (event.x, event.y)

    # ---------------------------------------------------------
    # ESPORTA PDF
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
            dima_pdf = self.genera_dima(width, height)
            page.merge_page(PdfReader(dima_pdf).pages[0])
            writer.add_page(page)

        with open(save_path, "wb") as f:
            writer.write(f)

        messagebox.showinfo("Esportazione completata", "PDF esportato con successo!")


# ---------------------------------------------------------
# AVVIO APP
# ---------------------------------------------------------
root = Tk()
app = DimaWizardApp(root)
root.mainloop()