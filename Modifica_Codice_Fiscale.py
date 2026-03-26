import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox


def sostituisci_segmento(riga: str) -> str:
    idx_src = 127   # colonna 128 (0-based)
    idx_dst = 111   # colonna 112 (0-based)
    length = 16

    if len(riga) < max(idx_src + length, idx_dst + length):
        return riga

    segment = riga[idx_src:idx_src + length]
    return riga[:idx_dst] + segment + riga[idx_dst + length:]


def main():
    app = QApplication(sys.argv)

    input_path, _ = QFileDialog.getOpenFileName(
        None,
        "Seleziona il file da elaborare",
        "",
        "File di testo (*.txt);;Tutti i file (*.*)",
    )

    if not input_path:
        QMessageBox.information(None, "Annullato", "Nessun file selezionato.")
        return

    p = Path(input_path)
    output_path = p.with_stem(p.stem + "_mod")

    try:
        lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    except Exception as e:
        QMessageBox.critical(None, "Errore", f"Impossibile leggere il file:\n{e}")
        return

    new_lines = [
        sostituisci_segmento(line) if line.startswith("E23") else line
        for line in lines
    ]

    try:
        output_path.write_text("".join(new_lines), encoding="utf-8")
    except Exception as e:
        QMessageBox.critical(None, "Errore", f"Impossibile scrivere il file:\n{e}")
        return

    QMessageBox.information(
        None,
        "Completato",
        f"File elaborato salvato come:\n{output_path}",
    )


if __name__ == "__main__":
    main()