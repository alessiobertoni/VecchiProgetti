import tkinter as tk
from tkinter import filedialog, messagebox

def analizza_file():
    percorso = filedialog.askopenfilename(
        title="Seleziona un file di testo",
        filetypes=[("File di testo", "*.txt"), ("Tutti i file", "*.*")]
    )

    if not percorso:
        return

    try:
        with open(percorso, "r", encoding="utf-8") as f:
            righe = f.readlines()
    except Exception as e:
        messagebox.showerror("Errore", f"Impossibile leggere il file:\n{e}")
        return

    report = []
    for i, riga in enumerate(righe, start=1):
        num_caratteri = len(riga.rstrip("\n"))
        report.append(f"Riga {i}: {num_caratteri} caratteri")

    text_output.delete("1.0", tk.END)
    text_output.insert(tk.END, "\n".join(report))


# GUI
root = tk.Tk()
root.title("Analizzatore di file di testo")

btn = tk.Button(root, text="Seleziona file", command=analizza_file)
btn.pack(pady=10)

text_output = tk.Text(root, width=60, height=20)
text_output.pack(padx=10, pady=10)

root.mainloop()