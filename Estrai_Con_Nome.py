import json
import os
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog, QMessageBox,
    QFormLayout, QFrame,
)

CONFIG_FILE = Path(__file__).parent / "config.json"


# ---------------------------------------------------------------------------
# Config Poppler
# ---------------------------------------------------------------------------

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_config(data: dict):
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


def ask_poppler_path(parent) -> Optional[str]:
    QMessageBox.information(
        parent,
        "Percorso Poppler",
        "Seleziona la cartella 'bin' di Poppler.\n\nEsempio: C:/poppler/Library/bin",
    )
    path = QFileDialog.getExistingDirectory(parent, "Seleziona cartella bin di Poppler")
    if not path:
        QMessageBox.warning(parent, "Annullato", "Percorso Poppler non configurato.")
        return None
    if not os.path.exists(os.path.join(path, "pdftoppm.exe")):
        QMessageBox.critical(parent, "Errore", "La cartella selezionata NON contiene pdftoppm.exe")
        return None
    return path


# ---------------------------------------------------------------------------
# Finestra principale
# ---------------------------------------------------------------------------

class PdfSplitterWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Splitter con Anteprima")
        self.setMinimumWidth(500)

        self.pdf_path: Optional[str] = None
        self.poppler_path: Optional[str] = None

        self._setup_poppler()
        self._build_ui()

    # ── Configurazione Poppler ───────────────────────────────────────────────

    def _setup_poppler(self):
        config = load_config()
        path   = config.get("poppler_path")

        if path and os.path.exists(path):
            self.poppler_path = path
            return

        path = ask_poppler_path(self)
        if not path:
            QMessageBox.critical(self, "Errore", "Impossibile avviare senza Poppler.")
            sys.exit(1)

        self.poppler_path = path
        config["poppler_path"] = path
        save_config(config)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)

        # Pulsante carica
        self.btn_load = QPushButton("Carica PDF")
        self.btn_load.setMinimumHeight(34)
        self.btn_load.clicked.connect(self.load_pdf)
        lay.addWidget(self.btn_load)

        # Anteprima
        self.preview = QLabel("Nessun PDF caricato")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(400, 400)
        self.preview.setFrameShape(QFrame.StyledPanel)
        self.preview.setStyleSheet("background:#e0e0e0; color:#555;")
        lay.addWidget(self.preview)

        # Campi input
        form = QFormLayout()
        self.field1 = QLineEdit()
        self.field2 = QLineEdit()
        self.field1.setPlaceholderText("es. Cliente")
        self.field2.setPlaceholderText("es. 2024")
        form.addRow("Campo 1:", self.field1)
        form.addRow("Campo 2:", self.field2)
        lay.addLayout(form)

        # Pulsante split
        self.btn_split = QPushButton("Esegui Split")
        self.btn_split.setMinimumHeight(34)
        self.btn_split.clicked.connect(self.split_pdf)
        lay.addWidget(self.btn_split)

    # ── Caricamento PDF ───────────────────────────────────────────────────────

    def load_pdf(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleziona PDF", "", "PDF files (*.pdf)"
        )
        if not path:
            return

        self.pdf_path = path

        try:
            from pdf2image import convert_from_path
            pages = convert_from_path(
                path, first_page=1, last_page=1,
                poppler_path=self.poppler_path,
            )
            img = pages[0].convert("RGB")
            img.thumbnail((400, 400))
            if img.width < 50 or img.height < 50:
                img = img.resize((300, 300))

            data = img.tobytes("raw", "RGB")
            qi   = QImage(data, img.width, img.height, img.width * 3, QImage.Format_RGB888)
            pm   = QPixmap.fromImage(qi)
            self.preview.setPixmap(pm)
            self.preview.setText("")

        except Exception as e:
            QMessageBox.critical(self, "Errore anteprima", f"Impossibile caricare l'anteprima:\n{e}")

    # ── Split PDF ──────────────────────────────────────────────────────────────

    def split_pdf(self):
        if not self.pdf_path:
            QMessageBox.warning(self, "Attenzione", "Carica prima un PDF.")
            return

        f1 = self.field1.text().strip()
        f2 = self.field2.text().strip()

        if not f1 or not f2:
            QMessageBox.warning(self, "Attenzione", "Compila entrambi i campi.")
            return

        try:
            from pypdf import PdfReader, PdfWriter
            reader  = PdfReader(self.pdf_path)
            out_dir = Path(self.pdf_path).parent

            for i, page in enumerate(reader.pages):
                writer = PdfWriter()
                writer.add_page(page)
                out_name = out_dir / f"{f1}_{f2}_pagina_{i + 1}.pdf"
                with open(out_name, "wb") as fout:
                    writer.write(fout)

            QMessageBox.information(
                self, "Completato",
                f"Split completato!\n{len(reader.pages)} file salvati in:\n{out_dir}",
            )

        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Errore durante lo split:\n{e}")


# ---------------------------------------------------------------------------
# Avvio
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    window = PdfSplitterWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()