import sys
from collections import Counter
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QFileDialog, QMessageBox, QFrame, QLabel
)
from PySide6.QtGui import QFont, QColor, QTextCharFormat, QTextCursor
from PySide6.QtCore import Qt

ultimo_report = ""


class AnalizzatoreWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Analizzatore di file di testo")
        self.setMinimumSize(750, 600)
        self.ultimo_report = ""
        self._setup_ui()
        self._apply_style()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Pulsanti
        btn_frame = QHBoxLayout()
        btn_frame.setSpacing(10)

        self.btn_apri = QPushButton("Seleziona file")
        self.btn_apri.setFixedHeight(36)
        self.btn_apri.clicked.connect(self.analizza_file)

        self.btn_salva = QPushButton("Salva report")
        self.btn_salva.setFixedHeight(36)
        self.btn_salva.clicked.connect(self.salva_report)

        btn_frame.addWidget(self.btn_apri)
        btn_frame.addWidget(self.btn_salva)
        btn_frame.addStretch()
        layout.addLayout(btn_frame)

        # Separatore
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep)

        # Area testo output
        self.text_output = QTextEdit()
        self.text_output.setReadOnly(True)
        self.text_output.setFont(QFont("Consolas", 10))
        self.text_output.setLineWrapMode(QTextEdit.NoWrap)
        layout.addWidget(self.text_output)

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #1e1e2e;
                color: #cdd6f4;
            }
            QPushButton {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 6px 20px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45475a;
                border-color: #89b4fa;
            }
            QPushButton:pressed {
                background-color: #89b4fa;
                color: #1e1e2e;
            }
            QTextEdit {
                background-color: #181825;
                color: #cdd6f4;
                border: 1px solid #313244;
                border-radius: 6px;
                padding: 8px;
                font-family: Consolas;
                font-size: 10pt;
            }
            QFrame[frameShape="4"] {
                color: #313244;
            }
            QScrollBar:vertical {
                background: #181825;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #45475a;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: #89b4fa;
            }
            QScrollBar:horizontal {
                background: #181825;
                height: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:horizontal {
                background: #45475a;
                border-radius: 5px;
            }
        """)
        # Colore pulsante Seleziona file (blu accent)
        self.btn_apri.setStyleSheet(
            self.btn_apri.styleSheet() +
            "QPushButton { background-color: #89b4fa; color: #1e1e2e; border-color: #89b4fa; }"
            "QPushButton:hover { background-color: #b4befe; }"
            "QPushButton:pressed { background-color: #cba6f7; }"
        )
        # Colore pulsante Salva report (verde accent)
        self.btn_salva.setStyleSheet(
            self.btn_salva.styleSheet() +
            "QPushButton { background-color: #a6e3a1; color: #1e1e2e; border-color: #a6e3a1; }"
            "QPushButton:hover { background-color: #caf2c2; }"
            "QPushButton:pressed { background-color: #94e2d5; }"
        )

    def analizza_file(self):
        percorso, _ = QFileDialog.getOpenFileName(
            self, "Seleziona un file", "", "Tutti i file (*.*)"
        )
        if not percorso:
            return

        try:
            with open(percorso, "r", encoding="utf-8") as f:
                righe = f.readlines()
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Impossibile leggere il file:\n{e}")
            return

        # Chiedi tipo di statistica
        risp = QMessageBox.question(
            self, "Tipo di statistica",
            "Vuoi la statistica ESTESA?\n\nSì = tutte le righe\nNo = statistiche raggruppate",
            QMessageBox.Yes | QMessageBox.No
        )
        scelta = (risp == QMessageBox.Yes)

        report = []
        lunghezze = []
        righe_anomale = set()  # numeri di riga (1-based) anomale

        for i, riga in enumerate(righe, start=1):
            num_caratteri = len(riga.rstrip("\n"))
            lunghezze.append(num_caratteri)
            if scelta:
                report.append(f"Riga {i}: {num_caratteri} caratteri")

        counter = Counter(lunghezze)
        lunghezza_prevalente = counter.most_common(1)[0][0]
        righe_prevalenti = counter[lunghezza_prevalente]
        righe_diverse = len(lunghezze) - righe_prevalenti
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
                report.append(f"Riga {num_riga}: con {lung} caratteri")
                righe_anomale.add(f"Riga {num_riga}: con {lung} caratteri")

        # Scrittura nel text edit con evidenziazione righe anomale
        self.text_output.clear()
        cursor = self.text_output.textCursor()

        fmt_normale = QTextCharFormat()
        fmt_normale.setForeground(QColor("#cdd6f4"))
        fmt_normale.setFontWeight(QFont.Normal)

        fmt_anomala = QTextCharFormat()
        fmt_anomala.setForeground(QColor("#f38ba8"))
        fmt_anomala.setFontWeight(QFont.Bold)

        for line in report:
            fmt = fmt_anomala if line.strip() in righe_anomale else fmt_normale
            cursor.insertText(line + "\n", fmt)

        self.text_output.setTextCursor(cursor)
        self.text_output.moveCursor(QTextCursor.Start)
        self.ultimo_report = "\n".join(report)

    def salva_report(self):
        if not self.ultimo_report:
            QMessageBox.warning(self, "Attenzione", "Non hai ancora generato un report.")
            return

        percorso, _ = QFileDialog.getSaveFileName(
            self, "Salva report", "", "File di testo (*.txt)"
        )
        if not percorso:
            return
        if not percorso.endswith(".txt"):
            percorso += ".txt"

        try:
            with open(percorso, "w", encoding="utf-8") as f:
                f.write(self.ultimo_report)
            QMessageBox.information(self, "Successo", "Report salvato correttamente.")
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Impossibile salvare il file:\n{e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = AnalizzatoreWindow()
    window.show()
    sys.exit(app.exec())