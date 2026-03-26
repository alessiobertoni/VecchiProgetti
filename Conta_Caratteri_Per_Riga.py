import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class AnalizzatoreFile(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Analizzatore di file di testo")
        self.resize(520, 460)

        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.btn = QPushButton("Seleziona file")
        self.btn.clicked.connect(self.analizza_file)
        layout.addWidget(self.btn)

        self.text_output = QTextEdit()
        self.text_output.setReadOnly(True)
        layout.addWidget(self.text_output)

    def analizza_file(self):
        percorso, _ = QFileDialog.getOpenFileName(
            self,
            "Seleziona un file di testo",
            "",
            "File di testo (*.txt);;Tutti i file (*.*)",
        )

        if not percorso:
            return

        try:
            righe = Path(percorso).read_text(encoding="utf-8").splitlines(keepends=True)
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Impossibile leggere il file:\n{e}")
            return

        report = [
            f"Riga {i}: {len(riga.rstrip(chr(10)))} caratteri"
            for i, riga in enumerate(righe, start=1)
        ]

        self.text_output.setPlainText("\n".join(report))


def main():
    app = QApplication(sys.argv)
    window = AnalizzatoreFile()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()