import os
import cv2
import fitz  # PyMuPDF
import pandas as pd
import json
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import numpy as np

class PDFExtractorApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.cartella = ""
        self.zone = []
        self.dati_finali = []
        self.simboli_pulizia = ""

    def configura_simboli(self):
        simboli_default = "-/|;,"
        nuovi_simboli = simpledialog.askstring(
            "Configurazione Pulizia", 
            "Simboli da eliminare (verranno sostituiti con spazi):",
            initialvalue=simboli_default
        )
        self.simboli_pulizia = nuovi_simboli if nuovi_simboli is not None else simboli_default

    def salva_maschera(self):
        if not self.zone: return
        if messagebox.askyesno("Salva Maschera", "Vuoi salvare questa configurazione di rettangoli per usi futuri?"):
            path_maschera = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")], title="Salva Maschera")
            if path_maschera:
                with open(path_maschera, 'w') as f:
                    json.dump(self.zone, f)
                messagebox.showinfo("Salvataggio", "Maschera salvata correttamente!")

    def carica_maschera(self):
        if messagebox.askyesno("Carica Maschera", "Hai già una maschera salvata per questi documenti?"):
            path_maschera = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")], title="Seleziona Maschera")
            if path_maschera:
                with open(path_maschera, 'r') as f:
                    self.zone = json.load(f)
                return True
        return False

    def seleziona_cartella(self):
        self.cartella = filedialog.askdirectory(title="Seleziona la cartella contenente i PDF")
        return bool(self.cartella)

    def chiedi_nome_zona(self):
        return simpledialog.askstring("Nome Campo", "Come vuoi chiamare questa cella Excel?")

    def definisci_zone(self, primo_pdf):
        doc = fitz.open(primo_pdf)
        pagina = doc[0]
        pix = pagina.get_pixmap(matrix=fitz.Matrix(2, 2))
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, 3)
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        copia_img = img.copy()
        titolo = "Seleziona area -> INVIO per confermare -> ESC per finire"

        while True:
            roi = cv2.selectROI(titolo, copia_img, fromCenter=False, showCrosshair=True)
            if roi[2] > 0 and roi[3] > 0:
                nome_zona = self.chiedi_nome_zona()
                if nome_zona:
                    split_parole = messagebox.askyesno("Opzione", f"Dividere ogni parola di '{nome_zona}' in celle?")
                    coord_reali = (roi[0]/2, roi[1]/2, (roi[0]+roi[2])/2, (roi[1]+roi[3])/2)
                    self.zone.append((nome_zona, coord_reali, split_parole))
                    cv2.rectangle(copia_img, (int(roi[0]), int(roi[1])), (int(roi[0]+roi[2]), int(roi[1]+roi[3])), (0, 255, 0), 2)
                    cv2.putText(copia_img, nome_zona, (int(roi[0]), int(roi[1]-10)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            else: break
        cv2.destroyAllWindows()
        doc.close()
        self.salva_maschera()

    def elabora_tutti_pdf(self):
        file_pdf = [f for f in os.listdir(self.cartella) if f.lower().endswith('.pdf')]
        totale = len(file_pdf)
        
        progress_win = tk.Toplevel(self.root)
        progress_win.title("Elaborazione...")
        progress_win.geometry("400x120")
        progress_win.attributes("-topmost", True)
        
        tk.Label(progress_win, text="Estrazione in corso...", font=('Helvetica', 10, 'bold')).pack(pady=10)
        progresso_var = tk.DoubleVar()
        progress_bar = ttk.Progressbar(progress_win, variable=progresso_var, maximum=totale)
        progress_bar.pack(fill="x", padx=20, pady=5)
        label_stato = tk.Label(progress_win, text="")
        label_stato.pack()

        for i, file_nome in enumerate(file_pdf):
            label_stato.config(text=f"File {i+1} di {totale}: {file_nome}")
            progresso_var.set(i + 1)
            progress_win.update()
            
            doc = fitz.open(os.path.join(self.cartella, file_nome))
            pagina = doc[0]
            riga = {"NOME_FILE": file_nome}
            
            for nome_zona, coords, split_parole in self.zone:
                rect = fitz.Rect(coords)
                testo_grezzo = pagina.get_text("text", clip=rect)
                testo_pulito = " ".join(testo_grezzo.replace('\n', ' ').split())
                
                if split_parole and testo_pulito:
                    for char in self.simboli_pulizia:
                        testo_pulito = testo_pulito.replace(char, " ")
                    parole = testo_pulito.split()
                    for idx, parola in enumerate(parole, 1):
                        riga[f"{nome_zona}_{idx}"] = parola
                else:
                    riga[nome_zona] = testo_pulito if testo_pulito else ""
            
            self.dati_finali.append(riga)
            doc.close()
        progress_win.destroy()

    def salva_excel(self):
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", initialfile="estrazione_dati.xlsx")
        if path:
            pd.DataFrame(self.dati_finali).to_excel(path, index=False)
            if messagebox.askyesno("Fatto", "File salvato. Vuoi aprirlo?"):
                os.startfile(path)

    def esegui(self):
        if self.seleziona_cartella():
            self.configura_simboli()
            # Prova a caricare una maschera esistente
            if not self.carica_maschera():
                # Se non caricata, procedi con il disegno manuale
                file_pdf = [f for f in os.listdir(self.cartella) if f.lower().endswith('.pdf')]
                if file_pdf:
                    self.definisci_zone(os.path.join(self.cartella, file_pdf[0]))
            
            if self.zone:
                self.elabora_tutti_pdf()
                self.salva_excel()

if __name__ == "__main__":
    app = PDFExtractorApp()
    app.esegui()