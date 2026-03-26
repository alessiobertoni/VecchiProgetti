import tkinter as tk
from tkinter import filedialog, messagebox
from collections import Counter
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

ultimo_report = ""


def analizza_file():
    percorso = filedialog.askopenfilename(
        title="Seleziona un file",
        filetypes=[("Tutti i file", "*.*")]
    )

    if not percorso:
        return

    try:
        with open(percorso, "r", encoding="utf-8") as f:
            righe = f.readlines()
    except Exception as e:
        messagebox.showerror("Errore", f"Impossibile leggere il file:\n{e}")
        return

    # Chiedi il tipo di statistica
    scelta = messagebox.askyesno(
        "Tipo di statistica",
        "Vuoi la statistica ESTESA?\n\n"
        "Sì = tutte le righe\n"
        "No = statistiche raggruppate"
    )

    report = []
    lunghezze = []

    # Calcolo lunghezze
    for i, riga in enumerate(righe, start=1):
        num_caratteri = len(riga.rstrip("\n"))
        lunghezze.append(num_caratteri)

        if scelta:  # Statistica estesa
            report.append(f"Riga {i}: {num_caratteri} caratteri")

    # Statistiche raggruppate
    counter = Counter(lunghezze)

    # Lunghezza prevalente
    lunghezza_prevalente = counter.most_common(1)[0][0]
    righe_prevalenti = counter[lunghezza_prevalente]

    # Righe diverse
    righe_diverse = len(lunghezze) - righe_prevalenti

    # Numeri delle righe diverse
    righe_diverse_lista = [
        i + 1 for i, lung in enumerate(lunghezze)
        if lung != lunghezza_prevalente
    ]

    report.append("\n--- Statistiche ---")
    for lung, count in sorted(counter.items()):
        report.append(f"{count} righe con {lung} caratteri")

    report.append(
        f"\nRighe diverse dal valore prevalente ({lunghezza_prevalente} caratteri): {righe_diverse}"
    )

    if righe_diverse_lista:
        report.append("\nDettaglio righe diverse:")
        for num_riga in righe_diverse_lista:
            lung = lunghezze[num_riga - 1]
            report.append(
                f"Riga {num_riga}: con {lung} caratteri"
            )

    # Mostra il report con evidenziazione
    text_output.config(state="normal")
    text_output.delete("1.0", tk.END)

    for line in report:
        if "Riga" in line and "diversi" in line:
            text_output.insert(tk.END, line + "\n", "anomala")
        else:
            text_output.insert(tk.END, line + "\n")

    text_output.config(state="disabled")

    global ultimo_report
    ultimo_report = "\n".join(report)


def salva_report():
    if not ultimo_report:
        messagebox.showwarning("Attenzione", "Non hai ancora generato un report.")
        return

    percorso = filedialog.asksaveasfilename(
        title="Salva report",
        defaultextension=".txt",
        filetypes=[("File di testo", "*.txt")]
    )

    if not percorso:
        return

    try:
        with open(percorso, "w", encoding="utf-8") as f:
            f.write(ultimo_report)
        messagebox.showinfo("Successo", "Report salvato correttamente.")
    except Exception as e:
        messagebox.showerror("Errore", f"Impossibile salvare il file:\n{e}")


# GUI stile Windows 11
root = ttk.Window(themename="cosmo")  # Tema moderno stile Win11
root.title("Analizzatore di file di testo")
root.geometry("750x600")

frame = ttk.Frame(root, padding=10)
frame.pack(fill="both", expand=True)

# Pulsanti
btn_frame = ttk.Frame(frame)
btn_frame.pack(pady=10)

btn_apri = ttk.Button(btn_frame, text="Seleziona file", bootstyle=PRIMARY, command=analizza_file)
btn_apri.grid(row=0, column=0, padx=5)

btn_salva = ttk.Button(btn_frame, text="Salva report", bootstyle=SUCCESS, command=salva_report)
btn_salva.grid(row=0, column=1, padx=5)

# Box testo + scrollbar
text_frame = ttk.Frame(frame)
text_frame.pack(fill="both", expand=True, pady=10)

scrollbar = ttk.Scrollbar(text_frame, orient="vertical")
scrollbar.pack(side="right", fill="y")

text_output = tk.Text(
    text_frame,
    width=90,
    height=30,
    wrap="none",
    yscrollcommand=scrollbar.set,
    font=("Segoe UI", 10)
)
text_output.pack(side="left", fill="both", expand=True)

scrollbar.config(command=text_output.yview)

# Stile evidenziazione righe anomale
text_output.tag_config("anomala", foreground="red", font=("Segoe UI", 10, "bold"))

root.mainloop()