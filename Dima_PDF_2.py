import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QPen
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QScrollArea, QFileDialog, QMessageBox,
    QDialog, QRadioButton, QButtonGroup, QDialogButtonBox,
    QLineEdit, QFormLayout, QCheckBox, QFrame,
)

import fitz  # PyMuPDF
from reportlab.pdfgen import canvas
from reportlab.lib.colors import red, blue, green, black
from pypdf import PdfReader, PdfWriter

# ---------------------------------------------------------------------------
# Conversioni
# ---------------------------------------------------------------------------

def mm_to_pt(mm: float) -> float:
    return mm * 2.83464567

def pt_to_mm(pt: float) -> float:
    return pt / 2.83464567

COLOR_MAP = {"rosso": red, "blu": blue, "verde": green, "nero": black}
COLOR_HEX = {"rosso": "#e63946", "blu": "#457b9d", "verde": "#2a9d8f", "nero": "#222222"}

def index_to_label(index: int) -> str:
    label = ""
    index += 1
    while index > 0:
        index, rem = divmod(index - 1, 26)
        label = chr(65 + rem) + label
    return label


# ---------------------------------------------------------------------------
# Dialog: valore float con limite
# ---------------------------------------------------------------------------

class FloatDialog(QDialog):
    def __init__(self, title: str, prompt: str, max_value: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.value: Optional[float] = None

        form = QFormLayout(self)
        form.setContentsMargins(16, 16, 16, 8)

        self._lbl = QLabel(f"{prompt}\n(Max: {max_value:.1f} mm)")
        self._lbl.setWordWrap(True)
        form.addRow(self._lbl)

        self._entry = QLineEdit()
        self._entry.setPlaceholderText("0.0")
        form.addRow("Valore (mm):", self._entry)

        self._max = max_value
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self._entry.setFocus()

    def _on_ok(self):
        try:
            v = float(self._entry.text().replace(",", "."))
        except ValueError:
            QMessageBox.warning(self, "Errore", "Inserisci un numero valido.")
            return
        if v < 0:
            QMessageBox.warning(self, "Errore", "Il valore non può essere negativo.")
            return
        if v > self._max:
            QMessageBox.warning(self, "Errore", f"Massimo consentito: {self._max:.1f} mm")
            return
        self.value = v
        self.accept()


# ---------------------------------------------------------------------------
# Dialog: scelta radio generica
# ---------------------------------------------------------------------------

class RadioDialog(QDialog):
    def __init__(self, title: str, label: str, options: list[tuple[str, str]], parent=None):
        """options: [(label, value), ...]"""
        super().__init__(parent)
        self.setWindowTitle(title)
        self.result_value: str = options[0][1]

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 8)
        lay.addWidget(QLabel(label))

        self._group = QButtonGroup(self)
        for i, (lbl, val) in enumerate(options):
            rb = QRadioButton(lbl)
            rb.setProperty("val", val)
            if i == 0:
                rb.setChecked(True)
            self._group.addButton(rb)
            lay.addWidget(rb)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _on_ok(self):
        btn = self._group.checkedButton()
        if btn:
            self.result_value = btn.property("val")
        self.accept()


# ---------------------------------------------------------------------------
# Dialog: posizione (lato + distanza)
# ---------------------------------------------------------------------------

class PositionDialog(QDialog):
    def __init__(self, page_w_mm: float, page_h_mm: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Posizione del rettangolo")
        self.result: Optional[dict] = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 8)

        lay.addWidget(QLabel("Posizione verticale"))
        self._rb_top    = QRadioButton("Distanza dall'alto");  self._rb_top.setChecked(True)
        self._rb_bottom = QRadioButton("Distanza dal basso")
        vg = QButtonGroup(self)
        for rb in (self._rb_top, self._rb_bottom):
            vg.addButton(rb); lay.addWidget(rb)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine); lay.addWidget(sep)

        lay.addWidget(QLabel("Posizione orizzontale"))
        self._rb_left  = QRadioButton("Distanza da sinistra"); self._rb_left.setChecked(True)
        self._rb_right = QRadioButton("Distanza da destra")
        hg = QButtonGroup(self)
        for rb in (self._rb_left, self._rb_right):
            hg.addButton(rb); lay.addWidget(rb)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        self._pw = page_w_mm
        self._ph = page_h_mm
        self._parent = parent

    def _on_ok(self):
        vert_side  = "top"  if self._rb_top.isChecked()  else "bottom"
        horiz_side = "left" if self._rb_left.isChecked() else "right"

        dlg_v = FloatDialog(
            "Posizione verticale",
            f"Distanza dall'{'alto' if vert_side == 'top' else 'basso'} (mm):",
            self._ph, self._parent
        )
        if not dlg_v.exec() or dlg_v.value is None:
            return

        dlg_h = FloatDialog(
            "Posizione orizzontale",
            f"Distanza da{'sinistra' if horiz_side == 'left' else ' destra'} (mm):",
            self._pw, self._parent
        )
        if not dlg_h.exec() or dlg_h.value is None:
            return

        self.result = {
            "vert_side": vert_side, "vert_value": dlg_v.value,
            "horiz_side": horiz_side, "horiz_value": dlg_h.value,
        }
        self.accept()


# ---------------------------------------------------------------------------
# Widget anteprima con zoom + pan
# ---------------------------------------------------------------------------

class PreviewCanvas(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.setMinimumSize(400, 400)
        self._pixmap_orig: Optional[QPixmap] = None
        self._zoom = 1.0
        self._pan_start = None
        self._offset_x = 0
        self._offset_y = 0
        self.setMouseTracking(True)

    def set_pixmap(self, pm: QPixmap):
        self._pixmap_orig = pm
        self._offset_x = 0
        self._offset_y = 0
        self._redraw()

    def _redraw(self):
        if self._pixmap_orig is None:
            return
        w = int(self._pixmap_orig.width()  * self._zoom)
        h = int(self._pixmap_orig.height() * self._zoom)
        scaled = self._pixmap_orig.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        canvas = QPixmap(self.size())
        canvas.fill(QColor("#e0e0e0"))
        painter = QPainter(canvas)
        painter.drawPixmap(self._offset_x, self._offset_y, scaled)
        painter.end()
        self.setPixmap(canvas)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        factor = 1.1 if delta > 0 else 1 / 1.1
        self._zoom = max(0.2, min(5.0, self._zoom * factor))
        self._redraw()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pan_start = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self._pan_start is not None:
            delta = event.position().toPoint() - self._pan_start
            self._offset_x += delta.x()
            self._offset_y += delta.y()
            self._pan_start = event.position().toPoint()
            self._redraw()

    def mouseReleaseEvent(self, event):
        self._pan_start = None

    def resizeEvent(self, event):
        self._redraw()


# ---------------------------------------------------------------------------
# App principale
# ---------------------------------------------------------------------------

class DimaWizardApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dima PDF Wizard")
        self.resize(1200, 700)

        self.pdf_path: Optional[str] = None
        self.rectangles: list[dict]  = []
        self.next_index: int         = 0
        self.debug_overlay: bool     = False
        self.debug_points: list      = []
        self.debug_rects: list       = []
        self.current_image: Optional[QImage] = None

        self._build_ui()

    # ── Layout ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)

        # Anteprima
        self._canvas = PreviewCanvas()
        scroll = QScrollArea()
        scroll.setWidget(self._canvas)
        scroll.setWidgetResizable(True)
        root.addWidget(scroll, 1)

        # Controlli
        ctrl = QWidget()
        ctrl.setFixedWidth(260)
        ctrl_lay = QVBoxLayout(ctrl)
        ctrl_lay.setContentsMargins(10, 10, 10, 10)
        ctrl_lay.setSpacing(10)

        for text, slot in [
            ("Carica PDF",           self.load_pdf),
            ("Aggiungi rettangolo",  self.ask_add_rectangle),
            ("Elimina rettangolo",   self.delete_rectangle),
            ("Toggle Debug Overlay", self.toggle_debug),
            ("Esporta PDF finale",   self.export_pdf),
        ]:
            btn = QPushButton(text)
            btn.setMinimumHeight(34)
            btn.clicked.connect(slot)
            ctrl_lay.addWidget(btn)

        ctrl_lay.addStretch()
        root.addWidget(ctrl)

    # ── Caricamento PDF ──────────────────────────────────────────────────────

    def load_pdf(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleziona PDF", "", "PDF files (*.pdf)"
        )
        if not path:
            return

        self.pdf_path   = path
        self.rectangles = []
        self.next_index = 0
        self.debug_points = []
        self.debug_rects  = []

        reader = PdfReader(path)
        page   = reader.pages[0]
        pw_pt  = float(page.mediabox.width)
        ph_pt  = float(page.mediabox.height)

        # Rettangolo base = intera pagina
        self.rectangles.append({
            "label": index_to_label(0),
            "width": pw_pt,  "height": ph_pt,
            "width_mm": pt_to_mm(pw_pt), "height_mm": pt_to_mm(ph_pt),
            "vert_side": "top",  "vert_value": 0, "vert_value_mm": 0,
            "horiz_side": "left", "horiz_value": 0, "horiz_value_mm": 0,
            "color": "nero", "text_position": "left", "fill_soft": False,
        })
        self.next_index = 1

        self.debug_points = self._extract_text_positions(page)
        self._update_preview()
        self.ask_add_rectangle()

    # ── Estrazione posizioni testo ────────────────────────────────────────────

    def _extract_text_positions(self, page) -> list:
        items = []

        def visitor(text, cm, tm, font_dict, font_size):
            real_x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            real_y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            items.append({
                "text": text, "x": real_x, "y": real_y,
                "w": len(text) * font_size * 0.5, "h": font_size,
            })

        page.extract_text(visitor_text=visitor)
        return items

    # ── Coordinate rettangolo in PDF ──────────────────────────────────────────

    def _get_rect_pdf_coords(self, rect: dict, page_w: float, page_h: float):
        y = (page_h - rect["vert_value"]  - rect["height"]) if rect["vert_side"]  == "top"  else rect["vert_value"]
        x = rect["horiz_value"] if rect["horiz_side"] == "left" else (page_w - rect["horiz_value"] - rect["width"])
        return x, y

    # ── Detection testo ───────────────────────────────────────────────────────

    def _rectangle_contains_text(self, rect: dict, text_items: list, pw: float, ph: float) -> bool:
        x, y = self._get_rect_pdf_coords(rect, pw, ph)
        tol  = 2.0
        for t in text_items:
            overlap = not (
                t["x"] + t["w"] < x - tol or t["x"] > x + rect["width"]  + tol or
                t["y"] + t["h"] < y - tol or t["y"] > y + rect["height"] + tol
            )
            if overlap:
                return True
        return False

    # ── Wizard: aggiungi rettangolo ───────────────────────────────────────────

    def ask_add_rectangle(self):
        if not self.pdf_path:
            QMessageBox.warning(self, "Attenzione", "Carica prima un PDF.")
            return
        if QMessageBox.question(
            self, "Aggiungi rettangolo", "Vuoi aggiungere un rettangolo?",
            QMessageBox.Yes | QMessageBox.No
        ) != QMessageBox.Yes:
            return

        reader  = PdfReader(self.pdf_path)
        page    = reader.pages[0]
        pw_mm   = pt_to_mm(float(page.mediabox.width))
        ph_mm   = pt_to_mm(float(page.mediabox.height))

        # Larghezza
        dlg = FloatDialog("Dimensioni", "Larghezza del rettangolo (mm):", pw_mm, self)
        if not dlg.exec() or dlg.value is None:
            return
        w_mm = dlg.value

        # Altezza
        dlg = FloatDialog("Dimensioni", "Altezza del rettangolo (mm):", ph_mm, self)
        if not dlg.exec() or dlg.value is None:
            return
        h_mm = dlg.value

        # Posizione
        pos_dlg = PositionDialog(pw_mm, ph_mm, self)
        if not pos_dlg.exec() or pos_dlg.result is None:
            return
        pos = pos_dlg.result

        # Colore
        col_dlg = RadioDialog(
            "Colore del rettangolo", "Scegli il colore:",
            [("Rosso", "rosso"), ("Blu", "blu"), ("Verde", "verde")], self
        )
        if not col_dlg.exec():
            return
        colore = col_dlg.result_value

        # Posizione testo
        tp_dlg = RadioDialog(
            "Posizione del testo", "Dove vuoi posizionare la scritta?",
            [("A sinistra", "left"), ("A destra", "right")], self
        )
        if not tp_dlg.exec():
            return
        text_pos = tp_dlg.result_value

        label = index_to_label(self.next_index)
        new_rect = {
            "label": label,
            "width": mm_to_pt(w_mm),  "height": mm_to_pt(h_mm),
            "width_mm": w_mm,          "height_mm": h_mm,
            "vert_side":  pos["vert_side"],  "vert_value":  mm_to_pt(pos["vert_value"]),
            "vert_value_mm": pos["vert_value"],
            "horiz_side": pos["horiz_side"], "horiz_value": mm_to_pt(pos["horiz_value"]),
            "horiz_value_mm": pos["horiz_value"],
            "color": colore, "text_position": text_pos, "fill_soft": False,
        }

        # Rilevamento testo
        text_items = self._extract_text_positions(page)
        contains = self._rectangle_contains_text(
            new_rect, text_items,
            float(page.mediabox.width), float(page.mediabox.height)
        )
        if contains and QMessageBox.question(
            self, "Testo rilevato",
            "In quest'area è presente del testo.\nVuoi evidenziarlo?",
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            new_rect["fill_soft"] = True

        self.rectangles.append(new_rect)
        self.next_index += 1

        # Aggiorna debug_rects
        x, y = self._get_rect_pdf_coords(
            new_rect, float(page.mediabox.width), float(page.mediabox.height)
        )
        self.debug_rects.append((x, y, new_rect["width"], new_rect["height"]))

        self._update_preview()
        self.ask_add_rectangle()

    # ── Elimina rettangolo ───────────────────────────────────────────────────

    def delete_rectangle(self):
        if not self.rectangles:
            QMessageBox.information(self, "Info", "Non ci sono rettangoli da eliminare.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Elimina rettangolo")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("Inserisci la lettera del rettangolo (es. A, B, AA):"))
        entry = QLineEdit()
        lay.addWidget(entry)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)

        if not dlg.exec():
            return

        target = entry.text().strip().upper()
        if not target:
            return

        before = len(self.rectangles)
        self.rectangles = [r for r in self.rectangles if r["label"] != target]

        if len(self.rectangles) < before:
            QMessageBox.information(self, "Eliminato", f"Rettangolo {target} eliminato.")
        else:
            QMessageBox.warning(self, "Non trovato", f"Nessun rettangolo con lettera {target}.")

        # Ricalcola debug_rects
        if self.pdf_path:
            reader = PdfReader(self.pdf_path)
            page   = reader.pages[0]
            pw, ph = float(page.mediabox.width), float(page.mediabox.height)
            self.debug_rects = [
                (*self._get_rect_pdf_coords(r, pw, ph), r["width"], r["height"])
                for r in self.rectangles
            ]

        self._update_preview()

    # ── Genera dima (PDF overlay) ─────────────────────────────────────────────

    def _genera_dima(self, width: float, height: float) -> str:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        c   = canvas.Canvas(tmp.name, pagesize=(width, height))
        self.debug_rects = []

        for r in self.rectangles:
            color = COLOR_MAP.get(r["color"], red)
            c.setStrokeColor(color)
            c.setLineWidth(1)

            x, y = self._get_rect_pdf_coords(r, width, height)
            self.debug_rects.append((x, y, r["width"], r["height"]))

            # Fill puntinato se richiesto
            if r.get("fill_soft"):
                self._draw_dotted(c, x, y, r["width"], r["height"], color)

            c.rect(x, y, r["width"], r["height"], fill=0, stroke=1)

            # Testo descrittivo
            c.setFillColor(color)
            c.setFont("Helvetica", 10)
            main_text = f"{r['label']} - {r['width_mm']:.0f} mm x {r['height_mm']:.0f} mm"
            pos1 = f"{r['vert_value_mm']:.0f} mm {'dall\'alto' if r['vert_side']=='top' else 'dal basso'}"
            pos2 = f"{r['horiz_value_mm']:.0f} mm {'da sinistra' if r['horiz_side']=='left' else 'da destra'}"

            if r["text_position"] == "left":
                tx = x + 2
            else:
                tx = x + r["width"] - max(len(main_text), len(pos1), len(pos2)) * 4 - 2

            c.drawString(tx, y + 4,  pos2)
            c.drawString(tx, y + 16, pos1)
            c.drawString(tx, y + 28, main_text)
            c.setFillColorRGB(0, 0, 0)

        c.save()
        return tmp.name

    def _draw_dotted(self, c, x, y, w, h, color):
        c.saveState()
        c.setFillColor(color)
        step, dot = 6, 1
        xx = x
        while xx < x + w:
            yy = y
            while yy < y + h:
                c.circle(xx, yy, dot, fill=1, stroke=0)
                yy += step
            xx += step
        c.restoreState()

    # ── Anteprima ────────────────────────────────────────────────────────────

    def _update_preview(self):
        if not self.pdf_path:
            return

        # Leggi dimensioni pagina con fitz
        doc_src = fitz.open(self.pdf_path)
        page0   = doc_src[0]
        w       = page0.rect.width
        h       = page0.rect.height
        doc_src.close()

        reader = PdfReader(self.pdf_path)

        if self.rectangles:
            dima_path = self._genera_dima(w, h)
            writer    = PdfWriter()
            page_copy = reader.pages[0]
            page_copy.merge_page(PdfReader(dima_path).pages[0])
            writer.add_page(page_copy)
        else:
            writer = PdfWriter()
            writer.add_page(reader.pages[0])

        tmp_out = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        with open(tmp_out.name, "wb") as f:
            writer.write(f)

        # Rendering con fitz (nessun Poppler necessario)
        doc  = fitz.open(tmp_out.name)
        mat  = fitz.Matrix(120 / 72, 120 / 72)   # ~120 DPI
        pix  = doc[0].get_pixmap(matrix=mat, alpha=False)
        doc.close()

        qi = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
        pm = QPixmap.fromImage(qi)

        if self.debug_overlay:
            pm = self._draw_debug_overlay(pm, w, h, pix.width, pix.height)

        self._canvas.set_pixmap(pm)

    def _draw_debug_overlay(self, pm: QPixmap, pdf_w: float, pdf_h: float,
                             img_w: int, img_h: int) -> QPixmap:
        sx = img_w / pdf_w
        sy = img_h / pdf_h
        painter = QPainter(pm)
        painter.setPen(QPen(QColor("red"), 4))
        for pt in self.debug_points:
            painter.drawEllipse(int(pt["x"] * sx) - 3, int((pdf_h - pt["y"]) * sy) - 3, 6, 6)
        painter.setPen(QPen(QColor("blue"), 2))
        for rx, ry, rw, rh in self.debug_rects:
            painter.drawRect(int(rx * sx), int((pdf_h - ry - rh) * sy),
                             int(rw * sx), int(rh * sy))
        painter.end()
        return pm

    def toggle_debug(self):
        self.debug_overlay = not self.debug_overlay
        self._update_preview()

    # ── Esporta PDF ───────────────────────────────────────────────────────────

    def export_pdf(self):
        if not self.pdf_path:
            QMessageBox.warning(self, "Attenzione", "Carica prima un PDF.")
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self, "Salva PDF", "", "PDF files (*.pdf)"
        )
        if not save_path:
            return

        reader = PdfReader(self.pdf_path)
        writer = PdfWriter()

        for page in reader.pages:
            w = float(page.mediabox.width)
            h = float(page.mediabox.height)
            dima_pdf  = self._genera_dima(w, h)
            dima_page = PdfReader(dima_pdf).pages[0]
            page.merge_page(dima_page)
            writer.add_page(page)

        with open(save_path, "wb") as f:
            writer.write(f)

        QMessageBox.information(self, "Completato", "PDF esportato con successo!")


# ---------------------------------------------------------------------------
# Avvio
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    window = DimaWizardApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()