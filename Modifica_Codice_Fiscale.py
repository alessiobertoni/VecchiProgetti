import os
import tkinter as tk
from tkinter import filedialog

def sostituisci_segmento(riga: str) -> str:
    idx_src = 127        # colonna 128 (0-based)
    idx_dst = 111        # colonna 112 (0-based)
    length = 16

    if len(riga) < max(idx_src + length, idx_dst + length):
        return riga

    segment = riga[idx_src:idx_src + length]  # copia dei 16 caratteri da colonna 128
    riga_mod = riga[:idx_dst] + segment + riga[idx_dst + length:]
    return riga_mod

def main():
    # Crea finestra nascosta
    root = tk.Tk()
    root.withdraw()

    # Apri finestra di selezione file
    input_path = filedialog.askopenfilename(
        title="Seleziona il file da elaborare",
        filetypes=[("File di testo", "*.txt"), ("Tutti i file", "*.*")]
    )

    if not input_path:
        print("Nessun file selezionato.")
        return

    # Costruisci il nome del file di output
    base, ext = os.path.splitext(input_path)
    output_path = base + "_mod" + ext

    with open(input_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        if line.startswith("E23"):
            new_lines.append(sostituisci_segmento(line))
        else:
            new_lines.append(line)

    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    print(f"File elaborato salvato come: {output_path}")

if __name__ == "__main__":
    main()
