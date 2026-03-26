import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
from pdf2image import convert_from_path
from pypdf import PdfReader, PdfWriter
import json
import os

CONFIG_FILE = "config.json"

# ------------------ CONFIGURAZIONE POPPLER ------------------

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=4)

def ask_poppler_path():
    messagebox.showinfo(
        "Percorso Poppler",
        "Seleziona la CARTELLA 'bin' di Poppler.\n\n"
        "Esempio: C:/poppler/Library/bin"
    )

    path = filedialog.askdirectory()

    if path and os.path.exists(path):
        # Verifica che contenga pdftoppm.exe
        if not os.path.exists(os.path.join(path, "pdftoppm.exe")):
            messagebox.showerror("Errore", "La cartella selezionata NON contiene pdftoppm.exe")
            return None
        return path

    messagebox.showerror("Errore", "Percorso Poppler non valido.")
    return None


# ------------------ GUI PRINCIPALE ------------------

class PdfSplitterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF Splitter con Anteprima")

        self.config = load_config()
        self.poppler_path = self.config.get("poppler_path")

        # Se Poppler non è configurato, chiedilo all'utente
        if not self.poppler_path or not os.path.exists(self.poppler_path):
            self.poppler_path = ask_poppler_path()
            if self.poppler_path:
                self.config["poppler_path"] = self.poppler_path
                save_config(self.config)
            else:
                raise Exception("Percorso Poppler non configurato!")

        self.pdf_path = None

        # Pulsante carica PDF
        tk.Button(root, text="Carica PDF", command=self.load_pdf).pack(pady=5)

        # Area anteprima
        self.preview_label = tk.Label(root, width=400, height=400, bg="lightgray")
        self.preview_label.pack(pady=10)

        # Campi input
        tk.Label(root, text="Campo 1:").pack()
        self.field1 = tk.Entry(root)
        self.field1.pack()

        tk.Label(root, text="Campo 2:").pack()
        self.field2 = tk.Entry(root)
        self.field2.pack()

        # Pulsante split
        tk.Button(root, text="Esegui Split", command=self.split_pdf).pack(pady=10)

    # ------------------ CARICAMENTO PDF ------------------

    def load_pdf(self):
        self.pdf_path = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf")])
        if not self.pdf_path:
            print("Nessun file selezionato.")
            return

        try:
            pages = convert_from_path(
                self.pdf_path,
                first_page=1,
                last_page=1,
                poppler_path=self.poppler_path
            )

            img = pages[0].convert("RGB")
            print("Dimensione immagine:", img.size)

            img.thumbnail((400, 400))

            if img.width < 50 or img.height < 50:
                img = img.resize((300, 300))

            self.img_tk = ImageTk.PhotoImage(img)

            self.preview_label.config(image=self.img_tk)
            self.preview_label.image = self.img_tk

            self.preview_label.update_idletasks()
            print("Anteprima aggiornata.")

        except Exception as e:
            print("ERRORE nel caricamento anteprima:", e)

    # ------------------ SPLIT PDF ------------------

    def split_pdf(self):
        if not self.pdf_path:
            print("Carica prima un PDF.")
            return

        f1 = self.field1.get().strip()
        f2 = self.field2.get().strip()

        if not f1 or not f2:
            print("Compila entrambi i campi!")
            return

        reader = PdfReader(self.pdf_path)

        for i, page in enumerate(reader.pages):
            writer = PdfWriter()
            writer.add_page(page)

            output_filename = f"{f1}_{f2}_pagina_{i+1}.pdf"

            with open(output_filename, "wb") as out_file:
                writer.write(out_file)

        print("Split completato!")

# ------------------ AVVIO PROGRAMMA ------------------

root = tk.Tk()
gui = PdfSplitterGUI(root)
root.mainloop()