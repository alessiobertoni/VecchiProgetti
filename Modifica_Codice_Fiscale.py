"""
text_record_editor — Demo standalone v2
────────────────────────────────────────
Operazioni su file di testo a tracciato fisso.

Dipendenze: PySide6
  pip install PySide6
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QFrame, QSplitter, QLineEdit,
    QSpinBox, QGroupBox, QFormLayout, QTextEdit, QStackedWidget,
    QSizePolicy, QScrollArea, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QTabWidget, QRadioButton,
    QButtonGroup, QMessageBox,
)

logging.basicConfig(level=logging.DEBUG,
                    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s")
log = logging.getLogger("demo.text_record_editor")


# ── AppContext minimale ───────────────────────────────────────────────────────

class _Settings:
    def __init__(self): self._d: dict = {}
    def get(self, k, default=None): return self._d.get(k, default)
    def set(self, k, v): self._d[k] = v

class _Popups:
    def confirm(self, parent, title_key, message,
                default_title="Conferma", default_message=None, **kw) -> bool:
        return QMessageBox.question(
            parent, default_title, default_message or message,
            QMessageBox.Yes | QMessageBox.No,
        ) == QMessageBox.Yes

    def info(self, parent, tk, message, default_title="Info", **kw):
        QMessageBox.information(parent, default_title, message)

    def warn(self, parent, tk, message, default_title="Attenzione", **kw):
        QMessageBox.warning(parent, default_title, message)

    def error(self, parent, tk, message, default_title="Errore", **kw):
        QMessageBox.critical(parent, default_title, message)

class _AppContext:
    def __init__(self):
        self.settings = _Settings()
        self.popups   = _Popups()
        self.theme    = None


# ── Risultati ─────────────────────────────────────────────────────────────────

@dataclass
class OverwriteResult:
    output_path: str
    rows_modified: int
    errors: list[str] = field(default_factory=list)

@dataclass
class InsertResult:
    output_path: str
    rows_modified: int
    rows_truncated: int = 0
    errors: list[str] = field(default_factory=list)

@dataclass
class AnalysisResult:
    total_rows: int
    row_lengths: dict[int, int]
    prefix_counts: dict[str, int]
    anomalies: list[tuple[int, int]]
    expected_length: Optional[int]

@dataclass
class FilterResult:
    output_path: str
    rows_extracted: int

@dataclass
class ExtractColumnResult:
    rows: list[tuple[int, str]]


# ── Handler ───────────────────────────────────────────────────────────────────

class Handler:
    def __init__(self, ctx):
        self.ctx = ctx

    def overwrite_from_column(self, input_path, output_path, prefix,
                               src_start, length, dst_start,
                               encoding="utf-8") -> OverwriteResult:
        src0    = src_start - 1
        dst0    = dst_start - 1
        min_len = max(src0 + length, dst0 + length)
        lines   = Path(input_path).read_text(encoding=encoding).splitlines(keepends=True)
        new_lines, modified, errors = [], 0, []
        for i, line in enumerate(lines, start=1):
            raw = line.rstrip("\n")
            if prefix and not raw.startswith(prefix):
                new_lines.append(line); continue
            if len(raw) < min_len:
                errors.append(f"Riga {i}: troppo corta ({len(raw)} car., necessari {min_len})")
                new_lines.append(line); continue
            segment = raw[src0:src0 + length]
            new_raw = raw[:dst0] + segment + raw[dst0 + length:]
            new_lines.append(new_raw + line[len(raw):])
            modified += 1
        Path(output_path).write_text("".join(new_lines), encoding=encoding)
        return OverwriteResult(output_path, modified, errors)

    def overwrite_fixed(self, input_path, output_path, prefix,
                        dst_start, length, value,
                        encoding="utf-8") -> OverwriteResult:
        dst0   = dst_start - 1
        padded = value[:length].ljust(length)
        lines  = Path(input_path).read_text(encoding=encoding).splitlines(keepends=True)
        new_lines, modified, errors = [], 0, []
        for i, line in enumerate(lines, start=1):
            raw = line.rstrip("\n")
            if prefix and not raw.startswith(prefix):
                new_lines.append(line); continue
            if len(raw) < dst0 + length:
                errors.append(f"Riga {i}: troppo corta ({len(raw)} car., necessari {dst0 + length})")
                new_lines.append(line); continue
            new_raw = raw[:dst0] + padded + raw[dst0 + length:]
            new_lines.append(new_raw + line[len(raw):])
            modified += 1
        Path(output_path).write_text("".join(new_lines), encoding=encoding)
        return OverwriteResult(output_path, modified, errors)

    def insert_text(self, input_path, output_path, prefix,
                    position, value, truncate,
                    encoding="utf-8") -> InsertResult:
        pos0  = position - 1
        lines = Path(input_path).read_text(encoding=encoding).splitlines(keepends=True)
        new_lines, modified, truncated, errors = [], 0, 0, []
        for i, line in enumerate(lines, start=1):
            raw = line.rstrip("\n")
            eol = line[len(raw):]
            if prefix and not raw.startswith(prefix):
                new_lines.append(line); continue
            if pos0 > len(raw):
                errors.append(f"Riga {i}: posizione {position} oltre la fine ({len(raw)} car.)")
                new_lines.append(line); continue
            orig_len = len(raw)
            new_raw  = raw[:pos0] + value + raw[pos0:]
            if truncate and len(new_raw) > orig_len:
                new_raw = new_raw[:orig_len]
                truncated += 1
            new_lines.append(new_raw + eol)
            modified += 1
        Path(output_path).write_text("".join(new_lines), encoding=encoding)
        return InsertResult(output_path, modified, truncated, errors)

    def analyze(self, input_path, prefix_length=3,
                encoding="utf-8") -> AnalysisResult:
        from collections import Counter
        lines    = Path(input_path).read_text(encoding=encoding).splitlines()
        lengths  = [len(l) for l in lines]
        prefixes = [l[:prefix_length] for l in lines if len(l) >= prefix_length]
        lc       = Counter(lengths)
        pc       = Counter(prefixes)
        expected = lc.most_common(1)[0][0] if lc else None
        anomalies = [(i + 1, lengths[i]) for i in range(len(lengths))
                     if expected is not None and lengths[i] != expected]
        return AnalysisResult(
            total_rows=len(lines),
            row_lengths=dict(sorted(lc.items())),
            prefix_counts=dict(sorted(pc.items(), key=lambda x: -x[1])),
            anomalies=anomalies,
            expected_length=expected,
        )

    def filter_rows(self, input_path, output_path, prefix,
                    encoding="utf-8") -> FilterResult:
        lines    = Path(input_path).read_text(encoding=encoding).splitlines(keepends=True)
        filtered = [l for l in lines if l.startswith(prefix)]
        Path(output_path).write_text("".join(filtered), encoding=encoding)
        return FilterResult(output_path, len(filtered))

    def extract_column(self, input_path, prefix, col_start, length,
                       encoding="utf-8") -> ExtractColumnResult:
        col0  = col_start - 1
        lines = Path(input_path).read_text(encoding=encoding).splitlines()
        rows  = []
        for i, line in enumerate(lines, start=1):
            if prefix and not line.startswith(prefix):
                continue
            rows.append((i, line[col0:col0 + length]
                         if len(line) >= col0 + length else ""))
        return ExtractColumnResult(rows)


# ── UI helpers ────────────────────────────────────────────────────────────────

def _open_folder(path: Path):
    try:
        folder = path if path.is_dir() else path.parent
        if os.name == "nt":
            os.startfile(str(folder))          # type: ignore
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])
    except Exception as e:
        log.warning(f"Impossibile aprire cartella: {e}")

def _spinbox(min_v=1, max_v=9999, val=1) -> QSpinBox:
    s = QSpinBox()
    s.setRange(min_v, max_v); s.setValue(val); s.setMinimumWidth(90)
    return s

def _section(title: str) -> QGroupBox:
    g = QGroupBox(title)
    g.setLayout(QFormLayout())
    g.layout().setContentsMargins(10, 10, 10, 10)
    g.layout().setSpacing(8)
    return g

class _FileOutRow(QWidget):
    def __init__(self, placeholder: str, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(6)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        btn = QPushButton("Sfoglia…"); btn.setFixedWidth(80)
        btn.clicked.connect(self._browse)
        lay.addWidget(self.edit, 1); lay.addWidget(btn)

    def _browse(self):
        p, _ = QFileDialog.getSaveFileName(
            self, "File output", "", "File di testo (*.txt);;Tutti i file (*.*)")
        if p: self.edit.setText(p)

    def path(self) -> str: return self.edit.text().strip()


# ── Pannello: Sovrascrivi (due tab) ───────────────────────────────────────────

class _PanelOverwrite(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(10)

        self._tabs = QTabWidget()
        lay.addWidget(self._tabs)

        # Tab 1: Da colonna
        tab_col = QWidget()
        tc = QVBoxLayout(tab_col)
        tc.setContentsMargins(8, 8, 8, 8); tc.setSpacing(10)
        grp1 = _section("Copia da colonna origine")
        f1: QFormLayout = grp1.layout()
        self.col_prefix    = QLineEdit()
        self.col_prefix.setPlaceholderText("es. E23  (vuoto = tutte le righe)")
        self.col_src_start = _spinbox()
        self.col_length    = _spinbox()
        self.col_dst_start = _spinbox()
        f1.addRow("Righe che iniziano per:", self.col_prefix)
        f1.addRow("Da colonna origine (1-based):", self.col_src_start)
        f1.addRow("Numero caratteri:", self.col_length)
        f1.addRow("A colonna destinazione (1-based):", self.col_dst_start)
        tc.addWidget(grp1)
        out1 = _section("Output")
        self.col_out = _FileOutRow("Lascia vuoto = suffisso _mod automatico")
        out1.layout().addRow("File output:", self.col_out)
        tc.addWidget(out1); tc.addStretch()
        self._tabs.addTab(tab_col, "Da colonna")

        # Tab 2: Valore fisso
        tab_fix = QWidget()
        tf = QVBoxLayout(tab_fix)
        tf.setContentsMargins(8, 8, 8, 8); tf.setSpacing(10)
        grp2 = _section("Scrivi valore fisso")
        f2: QFormLayout = grp2.layout()
        self.fix_prefix    = QLineEdit()
        self.fix_prefix.setPlaceholderText("es. E23  (vuoto = tutte le righe)")
        self.fix_dst_start = _spinbox()
        self.fix_length    = _spinbox()
        self.fix_value     = QLineEdit()
        self.fix_value.setPlaceholderText("Valore (troncato/paddato a spazi alla lunghezza)")
        f2.addRow("Righe che iniziano per:", self.fix_prefix)
        f2.addRow("Da colonna (1-based):", self.fix_dst_start)
        f2.addRow("Numero caratteri:", self.fix_length)
        f2.addRow("Valore fisso:", self.fix_value)
        tf.addWidget(grp2)
        out2 = _section("Output")
        self.fix_out = _FileOutRow("Lascia vuoto = suffisso _mod automatico")
        out2.layout().addRow("File output:", self.fix_out)
        tf.addWidget(out2); tf.addStretch()
        self._tabs.addTab(tab_fix, "Valore fisso")

    def current_tab(self) -> int: return self._tabs.currentIndex()

    def params_col(self) -> dict:
        return dict(prefix=self.col_prefix.text().strip(),
                    src_start=self.col_src_start.value(),
                    length=self.col_length.value(),
                    dst_start=self.col_dst_start.value(),
                    output=self.col_out.path())

    def params_fix(self) -> dict:
        return dict(prefix=self.fix_prefix.text().strip(),
                    dst_start=self.fix_dst_start.value(),
                    length=self.fix_length.value(),
                    value=self.fix_value.text(),
                    output=self.fix_out.path())


# ── Pannello: Inserisci ───────────────────────────────────────────────────────

class _PanelInsert(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(10)

        grp = _section("Parametri inserimento")
        f: QFormLayout = grp.layout()
        self.prefix   = QLineEdit()
        self.prefix.setPlaceholderText("es. E23  (vuoto = tutte le righe)")
        self.position = _spinbox()
        self.value    = QLineEdit()
        self.value.setPlaceholderText("Testo da inserire")
        f.addRow("Righe che iniziano per:", self.prefix)
        f.addRow("Inserisci PRIMA della colonna (1-based):", self.position)
        f.addRow("Testo da inserire:", self.value)
        lay.addWidget(grp)

        trunc_grp = _section("Se la riga supera la lunghezza originale")
        tl = QVBoxLayout()
        tl.setSpacing(6)
        self._rb_ask      = QRadioButton("Chiedi caso per caso")
        self._rb_truncate = QRadioButton("Tronca sempre alla lunghezza originale")
        self._rb_keep     = QRadioButton("Lascia sempre la riga più lunga")
        self._rb_ask.setChecked(True)
        bg = QButtonGroup(self)
        for rb in (self._rb_ask, self._rb_truncate, self._rb_keep):
            bg.addButton(rb); tl.addWidget(rb)
        trunc_grp.layout().addRow(tl)
        lay.addWidget(trunc_grp)

        out_grp = _section("Output")
        self.out_row = _FileOutRow("Lascia vuoto = suffisso _ins automatico")
        out_grp.layout().addRow("File output:", self.out_row)
        lay.addWidget(out_grp)
        lay.addStretch()

    def params(self) -> dict:
        if self._rb_truncate.isChecked(): mode = "truncate"
        elif self._rb_keep.isChecked():   mode = "keep"
        else:                             mode = "ask"
        return dict(prefix=self.prefix.text().strip(),
                    position=self.position.value(),
                    value=self.value.text(),
                    trunc_mode=mode,
                    output=self.out_row.path())


# ── Pannello: Analisi ─────────────────────────────────────────────────────────

class _PanelAnalyze(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(10)
        grp = _section("Parametri analisi")
        self.prefix_len = _spinbox(1, 20, 3)
        grp.layout().addRow("Lunghezza prefisso per raggruppamento:", self.prefix_len)
        lay.addWidget(grp); lay.addStretch()

    def params(self) -> dict:
        return dict(prefix_length=self.prefix_len.value())


# ── Pannello: Filtra righe ────────────────────────────────────────────────────

class _PanelFilter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(10)
        grp = _section("Parametri filtro")
        f: QFormLayout = grp.layout()
        self.prefix  = QLineEdit(); self.prefix.setPlaceholderText("es. E23")
        self.out_row = _FileOutRow("Percorso file output")
        f.addRow("Prefisso righe da estrarre:", self.prefix)
        f.addRow("File output:", self.out_row)
        lay.addWidget(grp); lay.addStretch()

    def params(self) -> dict:
        return dict(prefix=self.prefix.text().strip(),
                    output=self.out_row.path())


# ── Pannello: Estrai colonna ──────────────────────────────────────────────────

class _PanelExtract(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(10)
        grp = _section("Parametri estrazione colonna")
        f: QFormLayout = grp.layout()
        self.prefix    = QLineEdit()
        self.prefix.setPlaceholderText("es. E23  (vuoto = tutte le righe)")
        self.col_start = _spinbox()
        self.length    = _spinbox()
        f.addRow("Righe che iniziano per:", self.prefix)
        f.addRow("Da colonna (1-based):", self.col_start)
        f.addRow("Numero caratteri:", self.length)
        lay.addWidget(grp); lay.addStretch()

    def params(self) -> dict:
        return dict(prefix=self.prefix.text().strip(),
                    col_start=self.col_start.value(),
                    length=self.length.value())


# ── Finestra principale ───────────────────────────────────────────────────────

_OP_OVERWRITE = 0
_OP_INSERT    = 1
_OP_ANALYZE   = 2
_OP_FILTER    = 3
_OP_EXTRACT   = 4

_OP_LABELS = [
    ("Sovrascrivi",    "Sovrascrive un segmento copiando da altra colonna o con valore fisso"),
    ("Inserisci",      "Inserisce testo in una posizione spostando i caratteri successivi"),
    ("Analisi file",   "Statistiche: righe, lunghezze, prefissi, anomalie"),
    ("Filtra righe",   "Estrae in un nuovo file le righe con un dato prefisso"),
    ("Estrai colonna", "Visualizza il contenuto di un campo su tutte le righe filtrate"),
]


class MainWindow(QMainWindow):
    def __init__(self, ctx: _AppContext):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle("Editor Tracciato Fisso")
        self.resize(1100, 700)
        self._file_path: Optional[str] = None
        self._current_op = _OP_OVERWRITE
        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # Titolo
        title = QLabel("Editor Tracciato Fisso")
        f = title.font(); f.setPointSize(f.pointSize() + 5); f.setBold(True)
        title.setFont(f)
        root.addWidget(title)

        # File input
        file_grp = _section("File di input")
        fg: QFormLayout = file_grp.layout()
        file_row = QWidget()
        fr = QHBoxLayout(file_row)
        fr.setContentsMargins(0, 0, 0, 0); fr.setSpacing(6)
        self._file_edit = QLineEdit()
        self._file_edit.setPlaceholderText("Nessun file selezionato")
        self._file_edit.setReadOnly(True)
        self._btn_open = QPushButton("Apri file…")
        self._btn_open.setFixedWidth(100)
        fr.addWidget(self._file_edit, 1); fr.addWidget(self._btn_open)
        fg.addRow("File .txt:", file_row)
        self._lbl_info = QLabel("")
        self._lbl_info.setStyleSheet("color: gray; font-style: italic;")
        fg.addRow("", self._lbl_info)
        root.addWidget(file_grp)

        # Splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, 1)

        # Sidebar
        sidebar = QWidget(); sidebar.setFixedWidth(190)
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(0, 0, 0, 0); sb.setSpacing(4)
        lbl = QLabel("Operazioni")
        lbl.setStyleSheet("font-weight: bold; padding: 4px 0;")
        sb.addWidget(lbl)
        self._op_buttons: list[QPushButton] = []
        for i, (label, tooltip) in enumerate(_OP_LABELS):
            btn = QPushButton(label)
            btn.setCheckable(True); btn.setMinimumHeight(38)
            btn.setToolTip(tooltip)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.clicked.connect(lambda _, idx=i: self._select_op(idx))
            self._op_buttons.append(btn); sb.addWidget(btn)
        sb.addStretch()
        splitter.addWidget(sidebar)

        # Area destra
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(10, 0, 0, 0); rl.setSpacing(8)

        self._stack = QStackedWidget()
        self._panel_overwrite = _PanelOverwrite()
        self._panel_insert    = _PanelInsert()
        self._panel_analyze   = _PanelAnalyze()
        self._panel_filter    = _PanelFilter()
        self._panel_extract   = _PanelExtract()

        for panel in (self._panel_overwrite, self._panel_insert,
                      self._panel_analyze, self._panel_filter,
                      self._panel_extract):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setWidget(panel)
            self._stack.addWidget(scroll)
        rl.addWidget(self._stack, 1)

        # Pulsante esegui
        run_row = QHBoxLayout()
        self._btn_run = QPushButton("▶  Esegui")
        self._btn_run.setMinimumHeight(36)
        bf = self._btn_run.font(); bf.setBold(True)
        bf.setPointSize(bf.pointSize() + 1); self._btn_run.setFont(bf)
        run_row.addStretch(); run_row.addWidget(self._btn_run)
        rl.addLayout(run_row)

        # Log
        self._log = QTextEdit()
        self._log.setReadOnly(True); self._log.setFixedHeight(150)
        self._log.setPlaceholderText("I risultati appariranno qui…")
        rl.addWidget(self._log)

        # Tabella
        self._table = QTableWidget()
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setVisible(False); self._table.setMaximumHeight(200)
        rl.addWidget(self._table)

        splitter.addWidget(right)
        splitter.setSizes([190, 810])

        self._btn_open.clicked.connect(self._open_file)
        self._btn_run.clicked.connect(self._run)
        self._select_op(_OP_OVERWRITE)

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #1e1e2e; color: #cdd6f4; }
            QGroupBox {
                border: 1px solid #45475a; border-radius: 6px;
                margin-top: 8px; padding-top: 6px; font-weight: bold;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QTabWidget::pane { border: 1px solid #45475a; border-radius: 4px; }
            QTabBar::tab {
                background: #313244; color: #cdd6f4; padding: 6px 18px;
                border: 1px solid #45475a; border-bottom: none;
                border-top-left-radius: 4px; border-top-right-radius: 4px;
            }
            QTabBar::tab:selected { background: #45475a; }
            QTabBar::tab:hover    { background: #45475a; }
            QLineEdit, QSpinBox, QTextEdit {
                background: #181825; border: 1px solid #45475a;
                border-radius: 4px; padding: 4px; color: #cdd6f4;
            }
            QRadioButton { spacing: 6px; }
            QPushButton {
                background: #313244; color: #cdd6f4;
                border: 1px solid #45475a; border-radius: 6px;
                padding: 6px 14px; font-size: 13px;
            }
            QPushButton:hover   { background: #45475a; border-color: #89b4fa; }
            QPushButton:pressed { background: #89b4fa; color: #1e1e2e; }
            QPushButton:checked { background: #89b4fa; color: #1e1e2e; border-color: #89b4fa; }
            QTableWidget {
                background: #181825; border: 1px solid #313244;
                gridline-color: #313244; color: #cdd6f4;
            }
            QHeaderView::section {
                background: #313244; color: #cdd6f4;
                border: none; padding: 4px; font-weight: bold;
            }
            QScrollBar:vertical   { background: #181825; width: 8px; border-radius: 4px; }
            QScrollBar::handle:vertical { background: #45475a; border-radius: 4px; }
            QSplitter::handle { background: #313244; }
        """)
        self._btn_run.setStyleSheet(
            "QPushButton { background: #a6e3a1; color: #1e1e2e; border-color: #a6e3a1; }"
            "QPushButton:hover { background: #caf2c2; }"
        )

    def _select_op(self, idx: int):
        for i, btn in enumerate(self._op_buttons):
            btn.setChecked(i == idx)
        self._stack.setCurrentIndex(idx)
        self._current_op = idx
        self._table.setVisible(False)
        self._log.clear()

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Apri file di testo",
            self.ctx.settings.get("last_dir", ""),
            "File di testo (*.txt);;Tutti i file (*.*)",
        )
        if not path: return
        self._file_path = path
        self._file_edit.setText(path)
        self.ctx.settings.set("last_dir", str(Path(path).parent))
        try:
            lines = Path(path).read_text(encoding="utf-8").splitlines()
            size  = Path(path).stat().st_size
            self._lbl_info.setText(
                f"{len(lines)} righe  —  {size:,} byte  —  {Path(path).name}")
        except Exception:
            self._lbl_info.setText("")

    def _run(self):
        if not self._file_path or not Path(self._file_path).exists():
            self._log_line("⚠ Nessun file aperto."); return
        handler = Handler(self.ctx)
        try:
            op = self._current_op
            if   op == _OP_OVERWRITE: self._run_overwrite(handler)
            elif op == _OP_INSERT:    self._run_insert(handler)
            elif op == _OP_ANALYZE:   self._run_analyze(handler)
            elif op == _OP_FILTER:    self._run_filter(handler)
            elif op == _OP_EXTRACT:   self._run_extract(handler)
        except Exception as e:
            self._log_line(f"✖ Errore: {e}")
            log.exception("Operazione fallita")

    def _auto_output(self, suffix="_mod") -> str:
        p = Path(self._file_path)
        return str(p.with_stem(p.stem + suffix))

    def _run_overwrite(self, handler: Handler):
        tab = self._panel_overwrite.current_tab()
        if tab == 0:
            p   = self._panel_overwrite.params_col()
            out = p["output"] or self._auto_output("_mod")
            result = handler.overwrite_from_column(
                self._file_path, out, p["prefix"],
                p["src_start"], p["length"], p["dst_start"])
        else:
            p   = self._panel_overwrite.params_fix()
            out = p["output"] or self._auto_output("_mod")
            result = handler.overwrite_fixed(
                self._file_path, out, p["prefix"],
                p["dst_start"], p["length"], p["value"])
        self._log.clear()
        self._log_line(f"Righe modificate: {result.rows_modified}")
        if result.errors:
            self._log_line(f"\n⚠ {len(result.errors)} avvisi:")
            for e in result.errors[:20]: self._log_line(f"  {e}")
            if len(result.errors) > 20:
                self._log_line(f"  … e altri {len(result.errors) - 20}")
        self._log_line(f"\n✔ Salvato in: {out}")
        self._ask_open(Path(out))

    def _run_insert(self, handler: Handler):
        p    = self._panel_insert.params()
        out  = p["output"] or self._auto_output("_ins")
        mode = p["trunc_mode"]

        if mode == "ask":
            pos0  = p["position"] - 1
            lines = Path(self._file_path).read_text(encoding="utf-8").splitlines()
            would_grow = sum(
                1 for l in lines
                if (not p["prefix"] or l.startswith(p["prefix"])) and pos0 <= len(l)
            )
            truncate = False
            if would_grow > 0:
                truncate = self.ctx.popups.confirm(
                    self, "",
                    f"{would_grow} righe verranno allungate dopo l'inserimento.\n\n"
                    f"Vuoi troncarle alla lunghezza originale?",
                    default_title="Inserimento",
                    default_message="Troncare alla lunghezza originale?",
                )
        else:
            truncate = (mode == "truncate")

        result = handler.insert_text(
            self._file_path, out, p["prefix"],
            p["position"], p["value"], truncate)

        self._log.clear()
        self._log_line(f"Righe modificate:  {result.rows_modified}")
        if result.rows_truncated:
            self._log_line(f"Righe troncate:    {result.rows_truncated}")
        if result.errors:
            self._log_line(f"\n⚠ {len(result.errors)} avvisi:")
            for e in result.errors[:20]: self._log_line(f"  {e}")
        self._log_line(f"\n✔ Salvato in: {out}")
        self._ask_open(Path(out))

    def _run_analyze(self, handler: Handler):
        p      = self._panel_analyze.params()
        result = handler.analyze(self._file_path, p["prefix_length"])
        self._log.clear()
        self._log_line(f"Righe totali:         {result.total_rows}")
        self._log_line(f"Lunghezza prevalente: {result.expected_length} car.")
        self._log_line(f"Righe anomale:        {len(result.anomalies)}")
        rows_data = (
            [(str(l), str(c)) for l, c in result.row_lengths.items()]
            + [("── Prefissi ──", "")]
            + [(repr(pf), str(c)) for pf, c in result.prefix_counts.items()]
        )
        self._table.setVisible(True)
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels(["Lunghezza / Prefisso", "N° righe"])
        self._table.setRowCount(len(rows_data))
        for r, (a, b) in enumerate(rows_data):
            self._table.setItem(r, 0, QTableWidgetItem(a))
            self._table.setItem(r, 1, QTableWidgetItem(b))
        if result.anomalies:
            self._log_line(f"\nRighe anomale (prime 50):")
            for row_n, length in result.anomalies[:50]:
                self._log_line(f"  Riga {row_n}: {length} car.")

    def _run_filter(self, handler: Handler):
        p = self._panel_filter.params()
        if not p["prefix"]:
            self._log_line("⚠ Inserisci un prefisso."); return
        out    = p["output"] or self._auto_output(f"_{p['prefix']}")
        result = handler.filter_rows(self._file_path, out, p["prefix"])
        self._log.clear()
        self._log_line(f"Righe estratte: {result.rows_extracted}")
        self._log_line(f"✔ Salvato in: {out}")
        self._ask_open(Path(out))

    def _run_extract(self, handler: Handler):
        p      = self._panel_extract.params()
        result = handler.extract_column(
            self._file_path, p["prefix"], p["col_start"], p["length"])
        self._log.clear()
        self._log_line(f"Righe trovate: {len(result.rows)}")
        self._table.setVisible(True)
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels(["Riga", "Valore estratto"])
        self._table.setRowCount(len(result.rows))
        for r, (row_n, val) in enumerate(result.rows):
            self._table.setItem(r, 0, QTableWidgetItem(str(row_n)))
            self._table.setItem(r, 1, QTableWidgetItem(val))

    def _log_line(self, text: str):
        self._log.append(text)

    def _ask_open(self, path: Path):
        if self.ctx.popups.confirm(
            self, "", "Operazione completata.\n\nAprire la cartella?",
            default_title="Completato", default_message="Aprire la cartella?",
        ):
            _open_folder(path)


# ── Avvio ─────────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow(_AppContext())
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()