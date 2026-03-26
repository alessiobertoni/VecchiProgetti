#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
JSON Suite GUI (v3) - Standalone
GUI (PySide6) per modificare JSON con:
- Editor testo + formattazione + validazione
- Vista ad albero (edit base: add/remove/rename/set)
- Regole ripetibili (JSON; YAML opzionale)
- Preview: diff + patch/ops
- Undo/Redo
- Batch: applica regole a cartella (output separato)

Dipendenze:
  pip install PySide6
Opzionale:
  pip install pyyaml
"""

from __future__ import annotations

import json
import os
import re
import sys
import copy
import difflib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QMessageBox,
    QWidget, QSplitter,
    QPlainTextEdit, QTreeWidget, QTreeWidgetItem,
    QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QLineEdit,
    QTabWidget, QCheckBox, QComboBox, QGroupBox, QFormLayout,
    QProgressDialog
)

# -------- Optional YAML support --------
try:
    import yaml  # type: ignore
    HAS_YAML = True
except Exception:
    HAS_YAML = False

# =========================
# JSON Pointer helpers
# =========================
def jp_escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")

def jp_unescape(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")

def split_pointer(ptr: str) -> List[str]:
    if ptr == "" or ptr == "/":
        return []
    if not ptr.startswith("/"):
        raise ValueError(f"Invalid JSON Pointer: {ptr}")
    parts = ptr.split("/")[1:]
    return [jp_unescape(p) for p in parts]

def get_at(doc: Any, ptr: str) -> Any:
    cur = doc
    for p in split_pointer(ptr):
        if isinstance(cur, list):
            cur = cur[int(p)]
        elif isinstance(cur, dict):
            cur = cur[p]
        else:
            raise KeyError(f"Cannot traverse pointer {ptr}")
    return cur

def exists_at(doc: Any, ptr: str) -> bool:
    try:
        get_at(doc, ptr)
        return True
    except Exception:
        return False

def set_at(doc: Any, ptr: str, value: Any) -> None:
    parts = split_pointer(ptr)
    if not parts:
        raise ValueError("Cannot set root via set_at in this prototype.")
    cur = doc
    for p in parts[:-1]:
        cur = cur[int(p)] if isinstance(cur, list) else cur[p]
    last = parts[-1]
    if isinstance(cur, list):
        cur[int(last)] = value
    else:
        cur[last] = value

def add_at(doc: Any, ptr: str, value: Any) -> None:
    parts = split_pointer(ptr)
    if not parts:
        raise ValueError("Cannot add at root in this prototype.")
    cur = doc
    for p in parts[:-1]:
        cur = cur[int(p)] if isinstance(cur, list) else cur[p]
    last = parts[-1]
    if isinstance(cur, list):
        if last == "-":
            cur.append(value)
        else:
            cur.insert(int(last), value)
    else:
        cur[last] = value

def remove_at(doc: Any, ptr: str) -> None:
    parts = split_pointer(ptr)
    if not parts:
        raise ValueError("Cannot remove root.")
    cur = doc
    for p in parts[:-1]:
        cur = cur[int(p)] if isinstance(cur, list) else cur[p]
    last = parts[-1]
    if isinstance(cur, list):
        del cur[int(last)]
    else:
        del cur[last]

# =========================
# Pretty + diff + atomic write
# =========================
def pretty_json(doc: Any, indent: int = 2) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=indent, sort_keys=True)

def unified_diff(a: str, b: str, fromfile: str = "before.json", tofile: str = "after.json") -> str:
    al = a.splitlines(keepends=True)
    bl = b.splitlines(keepends=True)
    return "".join(difflib.unified_diff(al, bl, fromfile=fromfile, tofile=tofile))

def atomic_write(path: str, data: str) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(data)
    os.replace(tmp, path)

def parse_value(s: str) -> Any:
    s = s.strip()
    if s == "":
        return ""
    try:
        return json.loads(s)
    except Exception:
        return s

# =========================
# Rules engine
# =========================
@dataclass
class RuleResult:
    new_doc: Any
    ops: List[Dict[str, Any]]
    warnings: List[str]
    errors: List[str]

def deep_merge(dst: Any, src: Any, overwrite: bool = True) -> Any:
    if isinstance(dst, dict) and isinstance(src, dict):
        out = dict(dst)
        for k, v in src.items():
            if k in out:
                out[k] = deep_merge(out[k], v, overwrite=overwrite)
            else:
                out[k] = copy.deepcopy(v)
        return out
    return copy.deepcopy(src) if overwrite else copy.deepcopy(dst)

def compile_rules(text: str, fmt: str) -> List[Dict[str, Any]]:
    text = text.strip()
    if not text:
        return []
    if fmt == "json":
        data = json.loads(text)
    elif fmt == "yaml":
        if not HAS_YAML:
            raise RuntimeError("PyYAML non installato. Esegui: pip install pyyaml")
        data = yaml.safe_load(text)
    else:
        raise ValueError("Formato regole non supportato")

    if isinstance(data, dict):
        if "ops" in data and isinstance(data["ops"], list):
            return data["ops"]
        if "op" in data:
            return [data]
        raise ValueError("Se usi un oggetto, deve contenere 'ops' oppure essere una singola operazione con 'op'.")
    if isinstance(data, list):
        return data
    raise ValueError("Le regole devono essere una lista o un oggetto.")

def apply_ops(doc: Any, ops: List[Dict[str, Any]]) -> RuleResult:
    new_doc = copy.deepcopy(doc)
    out_ops: List[Dict[str, Any]] = []
    warnings: List[str] = []
    errors: List[str] = []

    def _apply_one(op: Dict[str, Any]) -> None:
        nonlocal new_doc
        typ = op.get("op")
        try:
            if typ == "replace_root":
                new_doc = copy.deepcopy(op.get("value"))
                out_ops.append({"op": "replace", "path": "", "value": copy.deepcopy(new_doc)})
                return

            if typ == "set":
                path = op["path"]
                value = copy.deepcopy(op.get("value"))
                if exists_at(new_doc, path):
                    set_at(new_doc, path, value)
                    out_ops.append({"op": "replace", "path": path, "value": copy.deepcopy(value)})
                else:
                    add_at(new_doc, path, value)
                    out_ops.append({"op": "add", "path": path, "value": copy.deepcopy(value)})
                return

            if typ == "add":
                path = op["path"]
                value = copy.deepcopy(op.get("value"))
                add_at(new_doc, path, value)
                out_ops.append({"op": "add", "path": path, "value": copy.deepcopy(value)})
                return

            if typ == "remove":
                path = op["path"]
                remove_at(new_doc, path)
                out_ops.append({"op": "remove", "path": path})
                return

            if typ == "rename":
                path = op["path"]
                k_from = op["from"]
                k_to = op["to"]
                obj = get_at(new_doc, path)
                if not isinstance(obj, dict):
                    raise TypeError(f"rename richiede un oggetto a {path}")
                if k_from not in obj:
                    warnings.append(f"rename: '{k_from}' non trovato a {path}")
                    return
                if k_to in obj:
                    warnings.append(f"rename: '{k_to}' esiste già a {path}, sovrascrivo")
                obj[k_to] = obj.pop(k_from)
                out_ops.append({"op": "move", "from": f"{path}/{jp_escape(k_from)}", "path": f"{path}/{jp_escape(k_to)}"})
                return

            if typ == "merge":
                path = op["path"]
                value = op.get("value")
                overwrite = bool(op.get("overwrite", True))
                target = get_at(new_doc, path)
                merged = deep_merge(target, value, overwrite=overwrite)
                set_at(new_doc, path, merged)
                out_ops.append({"op": "replace", "path": path, "value": copy.deepcopy(merged)})
                return

            if typ == "when":
                cond = op.get("if", {})
                cpath = cond.get("path")
                equals = cond.get("equals", None)
                present = cond.get("present", None)

                if cpath is None:
                    raise ValueError("when.if.path obbligatorio")

                matched = False
                if present is not None:
                    matched = exists_at(new_doc, cpath) == bool(present)
                else:
                    matched = exists_at(new_doc, cpath) and (get_at(new_doc, cpath) == equals)

                branch = op.get("then", []) if matched else op.get("else", [])
                if not isinstance(branch, list):
                    raise ValueError("when.then/else devono essere liste")
                for sub in branch:
                    if isinstance(sub, dict):
                        _apply_one(sub)
                    else:
                        errors.append("when: operazione non valida (non è un oggetto)")
                return

            raise ValueError(f"Operazione sconosciuta: {typ}")

        except Exception as e:
            errors.append(f"{typ}: {e}")

    for op in ops:
        if not isinstance(op, dict):
            errors.append("Operazione non valida (non è un oggetto)")
            continue
        _apply_one(op)

    return RuleResult(new_doc=new_doc, ops=out_ops, warnings=warnings, errors=errors)

# =========================
# Tree view
# =========================
ROLE_PTR = Qt.UserRole + 1

def preview_value(v: Any) -> str:
    if isinstance(v, (dict, list)):
        return ""
    s = json.dumps(v, ensure_ascii=False)
    return s if len(s) <= 80 else s[:77] + "..."

def is_dummy(item: QTreeWidgetItem) -> bool:
    return item.childCount() == 1 and item.child(0).text(0) == ""

def build_tree(tree: QTreeWidget, doc: Any) -> None:
    tree.clear()
    root = QTreeWidgetItem(["<root>", type(doc).__name__, ""])
    root.setData(0, ROLE_PTR, "")
    tree.addTopLevelItem(root)
    fill_children(root, doc, "")
    root.setExpanded(True)

def fill_children(parent_item: QTreeWidgetItem, value: Any, ptr: str) -> None:
    parent_item.takeChildren()
    if isinstance(value, dict):
        for k in sorted(value.keys(), key=lambda x: str(x)):
            v = value[k]
            child_ptr = f"{ptr}/{jp_escape(str(k))}" if ptr else f"/{jp_escape(str(k))}"
            child = QTreeWidgetItem([str(k), type(v).__name__, preview_value(v)])
            child.setData(0, ROLE_PTR, child_ptr)
            parent_item.addChild(child)
            if isinstance(v, (dict, list)):
                child.addChild(QTreeWidgetItem(["", "", ""]))  # dummy
    elif isinstance(value, list):
        for i, v in enumerate(value):
            child_ptr = f"{ptr}/{i}" if ptr else f"/{i}"
            child = QTreeWidgetItem([f"[{i}]", type(v).__name__, preview_value(v)])
            child.setData(0, ROLE_PTR, child_ptr)
            parent_item.addChild(child)
            if isinstance(v, (dict, list)):
                child.addChild(QTreeWidgetItem(["", "", ""]))  # dummy

# =========================
# Undo manager
# =========================
@dataclass
class Snapshot:
    doc: Any
    note: str

class UndoManager:
    def __init__(self) -> None:
        self.stack: List[Snapshot] = []
        self.redo_stack: List[Snapshot] = []

    def push(self, doc: Any, note: str) -> None:
        self.stack.append(Snapshot(copy.deepcopy(doc), note))
        self.redo_stack.clear()

    def can_undo(self) -> bool:
        return len(self.stack) > 1

    def can_redo(self) -> bool:
        return len(self.redo_stack) > 0

    def undo(self) -> Optional[Snapshot]:
        if not self.can_undo():
            return None
        cur = self.stack.pop()
        self.redo_stack.append(cur)
        return self.stack[-1]

    def redo(self) -> Optional[Snapshot]:
        if not self.can_redo():
            return None
        snap = self.redo_stack.pop()
        self.stack.append(snap)
        return snap

# =========================
# Main window
# =========================
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("JSON Suite GUI (v3)")
        self.resize(1350, 820)

        self.current_path: Optional[str] = None
        self.doc: Any = {}
        self.undo = UndoManager()
        self.undo.push(self.doc, "initial")

        self._sync_guard = False

        self._build_ui()
        self._build_menu()
        self._refresh_all()

    # UI
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(6, 6, 6, 6)

        splitter = QSplitter(Qt.Horizontal)
        outer.addWidget(splitter)

        # LEFT panel: tree + buttons
        left = QWidget()
        left_v = QVBoxLayout(left)
        left_v.setContentsMargins(0, 0, 0, 0)
        left_v.setSpacing(6)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Key/Index", "Type", "Value"])
        self.tree.setUniformRowHeights(True)
        self.tree.itemExpanded.connect(self._on_tree_expand)
        left_v.addWidget(self.tree, 1)

        btns = QHBoxLayout()
        self.btn_add = QPushButton("Add")
        self.btn_remove = QPushButton("Remove")
        self.btn_rename = QPushButton("Rename")
        self.btn_set = QPushButton("Set Value")
        for b in [self.btn_add, self.btn_remove, self.btn_rename, self.btn_set]:
            b.setMinimumHeight(28)
        self.btn_add.clicked.connect(self._tree_add)
        self.btn_remove.clicked.connect(self._tree_remove)
        self.btn_rename.clicked.connect(self._tree_rename)
        self.btn_set.clicked.connect(self._tree_set_value)
        btns.addWidget(self.btn_add)
        btns.addWidget(self.btn_remove)
        btns.addWidget(self.btn_rename)
        btns.addWidget(self.btn_set)
        left_v.addLayout(btns)

        splitter.addWidget(left)

        # RIGHT panel: tabs
        right = QWidget()
        right_v = QVBoxLayout(right)
        right_v.setContentsMargins(0, 0, 0, 0)
        right_v.setSpacing(6)

        self.lbl_status = QLabel("Ready")
        right_v.addWidget(self.lbl_status)

        self.tabs = QTabWidget()
        right_v.addWidget(self.tabs, 1)

        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)

        # Text tab
        tab_text = QWidget()
        t_v = QVBoxLayout(tab_text)
        top = QHBoxLayout()
        self.btn_format = QPushButton("Format JSON")
        self.btn_apply_text = QPushButton("Apply Text -> Model")
        self.btn_format.clicked.connect(self._format_json)
        self.btn_apply_text.clicked.connect(self._apply_text_to_model)
        top.addWidget(self.btn_format)
        top.addWidget(self.btn_apply_text)
        top.addStretch(1)
        t_v.addLayout(top)

        self.text = QPlainTextEdit()
        self.text.setFont(mono)
        self.text.textChanged.connect(self._on_text_changed)
        t_v.addWidget(self.text, 1)
        self.tabs.addTab(tab_text, "Text")

        # Rules tab
        tab_rules = QWidget()
        r_v = QVBoxLayout(tab_rules)

        row = QHBoxLayout()
        row.addWidget(QLabel("Rules format:"))
        self.rules_fmt = QComboBox()
        self.rules_fmt.addItems(["json"] + (["yaml"] if HAS_YAML else []))
        row.addWidget(self.rules_fmt)
        row.addStretch(1)
        r_v.addLayout(row)

        self.chk_apply_to_text = QCheckBox("After applying rules, update Text editor")
        self.chk_apply_to_text.setChecked(True)
        r_v.addWidget(self.chk_apply_to_text)

        row2 = QHBoxLayout()
        self.btn_preview = QPushButton("Preview (diff + patch)")
        self.btn_apply_rules = QPushButton("Apply Rules (commit)")
        self.btn_preview.clicked.connect(self._preview_rules)
        self.btn_apply_rules.clicked.connect(self._apply_rules_commit)
        row2.addWidget(self.btn_preview)
        row2.addWidget(self.btn_apply_rules)
        row2.addStretch(1)
        r_v.addLayout(row2)

        self.rules = QPlainTextEdit()
        self.rules.setFont(mono)
        self.rules.setPlaceholderText(self._default_rules_example())
        r_v.addWidget(self.rules, 1)

        self.tabs.addTab(tab_rules, "Rules")

        # Preview tab
        tab_prev = QWidget()
        p_v = QVBoxLayout(tab_prev)

        self.prev_tabs = QTabWidget()
        self.diff_view = QPlainTextEdit(); self.diff_view.setFont(mono); self.diff_view.setReadOnly(True)
        self.patch_view = QPlainTextEdit(); self.patch_view.setFont(mono); self.patch_view.setReadOnly(True)
        self.report_view = QPlainTextEdit(); self.report_view.setFont(mono); self.report_view.setReadOnly(True)
        self.prev_tabs.addTab(self.diff_view, "Diff")
        self.prev_tabs.addTab(self.patch_view, "Patch/Ops")
        self.prev_tabs.addTab(self.report_view, "Report")
        p_v.addWidget(self.prev_tabs, 1)

        self.tabs.addTab(tab_prev, "Preview")

        # Batch tab
        tab_batch = QWidget()
        b_v = QVBoxLayout(tab_batch)

        box = QGroupBox("Batch apply rules to folder")
        form = QFormLayout(box)

        self.in_dir = QLineEdit()
        self.out_dir = QLineEdit()
        btn_in = QPushButton("Browse...")
        btn_out = QPushButton("Browse...")
        btn_in.clicked.connect(lambda: self._pick_dir(self.in_dir))
        btn_out.clicked.connect(lambda: self._pick_dir(self.out_dir))

        row_in = QWidget(); row_in_l = QHBoxLayout(row_in); row_in_l.setContentsMargins(0,0,0,0); row_in_l.addWidget(self.in_dir,1); row_in_l.addWidget(btn_in)
        row_out = QWidget(); row_out_l = QHBoxLayout(row_out); row_out_l.setContentsMargins(0,0,0,0); row_out_l.addWidget(self.out_dir,1); row_out_l.addWidget(btn_out)

        self.pattern = QLineEdit("*.json")
        self.max_files = QLineEdit("1000")

        self.btn_run_batch = QPushButton("Run Batch")
        self.btn_run_batch.clicked.connect(self._run_batch)

        form.addRow("Input folder:", row_in)
        form.addRow("Output folder:", row_out)
        form.addRow("File pattern:", self.pattern)
        form.addRow("Max files:", self.max_files)
        form.addRow(self.btn_run_batch)

        b_v.addWidget(box)

        self.batch_log = QPlainTextEdit()
        self.batch_log.setFont(mono)
        self.batch_log.setReadOnly(True)
        b_v.addWidget(self.batch_log, 1)

        self.tabs.addTab(tab_batch, "Batch")

        splitter.addWidget(right)
        splitter.setSizes([470, 880])

    def _build_menu(self) -> None:
        m_file = self.menuBar().addMenu("&File")
        act_new = QAction("New", self); act_new.setShortcut(QKeySequence.New); act_new.triggered.connect(self.new_doc)
        act_open = QAction("Open JSON...", self); act_open.setShortcut(QKeySequence.Open); act_open.triggered.connect(self.open_file)
        act_save = QAction("Save", self); act_save.setShortcut(QKeySequence.Save); act_save.triggered.connect(self.save_file)
        act_save_as = QAction("Save As...", self); act_save_as.setShortcut(QKeySequence.SaveAs); act_save_as.triggered.connect(self.save_file_as)
        act_exit = QAction("Exit", self); act_exit.triggered.connect(self.close)

        m_file.addAction(act_new)
        m_file.addAction(act_open)
        m_file.addSeparator()
        m_file.addAction(act_save)
        m_file.addAction(act_save_as)
        m_file.addSeparator()
        m_file.addAction(act_exit)

        m_edit = self.menuBar().addMenu("&Edit")
        self.act_undo = QAction("Undo", self); self.act_undo.setShortcut(QKeySequence.Undo); self.act_undo.triggered.connect(self._undo)
        self.act_redo = QAction("Redo", self); self.act_redo.setShortcut(QKeySequence.Redo); self.act_redo.triggered.connect(self._redo)
        m_edit.addAction(self.act_undo)
        m_edit.addAction(self.act_redo)

        m_help = self.menuBar().addMenu("&Help")
        act_sample = QAction("Insert sample rules", self); act_sample.triggered.connect(self._insert_sample_rules)
        act_about = QAction("About", self); act_about.triggered.connect(self._about)
        m_help.addAction(act_sample)
        m_help.addSeparator()
        m_help.addAction(act_about)

    # Refresh
    def _refresh_all(self) -> None:
        self._sync_guard = True
        try:
            build_tree(self.tree, self.doc)
            self.text.setPlainText(pretty_json(self.doc, indent=2))
            self._update_actions()
            self.lbl_status.setText(self._doc_label())
            self.diff_view.setPlainText("")
            self.patch_view.setPlainText("")
            self.report_view.setPlainText("")
        finally:
            self._sync_guard = False

    def _doc_label(self) -> str:
        name = os.path.basename(self.current_path) if self.current_path else "<unsaved>"
        return f"Loaded: {name}"

    def _update_actions(self) -> None:
        self.act_undo.setEnabled(self.undo.can_undo())
        self.act_redo.setEnabled(self.undo.can_redo())

    # File ops
    def new_doc(self) -> None:
        self.current_path = None
        self.doc = {}
        self.undo = UndoManager()
        self.undo.push(self.doc, "new")
        self._refresh_all()

    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open JSON", "", "JSON files (*.json);;All files (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.doc = json.load(f)
            self.current_path = path
            self.undo = UndoManager()
            self.undo.push(self.doc, f"open {os.path.basename(path)}")
            self._refresh_all()
        except Exception as e:
            QMessageBox.critical(self, "Open error", str(e))

    def save_file(self) -> None:
        if not self.current_path:
            self.save_file_as()
            return
        try:
            atomic_write(self.current_path, pretty_json(self.doc, indent=2))
            self.lbl_status.setText(f"Saved: {self.current_path}")
        except Exception as e:
            QMessageBox.critical(self, "Save error", str(e))

    def save_file_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save JSON As", "", "JSON files (*.json);;All files (*)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        self.current_path = path
        self.save_file()

    # Text tab
    def _on_text_changed(self) -> None:
        if self._sync_guard:
            return
        s = self.text.toPlainText()
        try:
            json.loads(s)
            self.lbl_status.setText("Text: valid JSON")
        except Exception as e:
            self.lbl_status.setText(f"Text: invalid JSON ({e})")

    def _format_json(self) -> None:
        try:
            data = json.loads(self.text.toPlainText())
            self._sync_guard = True
            self.text.setPlainText(pretty_json(data, indent=2))
            self.lbl_status.setText("Formatted")
        except Exception as e:
            QMessageBox.warning(self, "Format error", str(e))
        finally:
            self._sync_guard = False

    def _apply_text_to_model(self) -> None:
        try:
            data = json.loads(self.text.toPlainText())
            self._commit_doc(data, note="apply text")
        except Exception as e:
            QMessageBox.warning(self, "Apply error", f"Text is not valid JSON:\n{e}")

    # Tree
    def _selected_ptr(self) -> str:
        items = self.tree.selectedItems()
        if not items:
            return ""
        return items[0].data(0, ROLE_PTR) or ""

    def _on_tree_expand(self, item: QTreeWidgetItem) -> None:
        ptr = item.data(0, ROLE_PTR) or ""
        val = self.doc if ptr == "" else get_at(self.doc, ptr)
        if isinstance(val, (dict, list)) and is_dummy(item):
            fill_children(item, val, ptr)

    def _tree_set_value(self) -> None:
        items = self.tree.selectedItems()
        if not items:
            return
        ptr = items[0].data(0, ROLE_PTR) or ""
        if ptr == "":
            QMessageBox.information(self, "Set value", "Per cambiare il root usa il tab Text e 'Apply Text -> Model'.")
            return
        cur = get_at(self.doc, ptr)
        default = json.dumps(cur, ensure_ascii=False)
        val, ok = self._prompt("Set Value", f"JSON value for {ptr}:", default)
        if not ok:
            return
        try:
            newv = parse_value(val)
            new_doc = copy.deepcopy(self.doc)
            if exists_at(new_doc, ptr):
                set_at(new_doc, ptr, newv)
            else:
                add_at(new_doc, ptr, newv)
            self._commit_doc(new_doc, note=f"set {ptr}")
        except Exception as e:
            QMessageBox.warning(self, "Set error", str(e))

    def _tree_add(self) -> None:
        items = self.tree.selectedItems()
        if not items:
            return
        ptr = items[0].data(0, ROLE_PTR) or ""
        target = self.doc if ptr == "" else get_at(self.doc, ptr)

        if isinstance(target, dict):
            k, ok = self._prompt("Add key", f"New key under {ptr or '<root>'}:", "newKey")
            if not ok or not k:
                return
            v, ok2 = self._prompt("Add value", f"Value for '{k}':", "null")
            if not ok2:
                return
            newv = parse_value(v)
            new_doc = copy.deepcopy(self.doc)
            base = new_doc if ptr == "" else get_at(new_doc, ptr)
            base[k] = newv
            self._commit_doc(new_doc, note=f"add key {k}")
            return

        if isinstance(target, list):
            v, ok = self._prompt("Append", f"Value to append under {ptr or '<root>'}:", "null")
            if not ok:
                return
            newv = parse_value(v)
            new_doc = copy.deepcopy(self.doc)
            base = new_doc if ptr == "" else get_at(new_doc, ptr)
            base.append(newv)
            self._commit_doc(new_doc, note="append")
            return

        QMessageBox.information(self, "Add", "Seleziona un oggetto (dict) o un array (list) per aggiungere elementi.")

    def _tree_remove(self) -> None:
        items = self.tree.selectedItems()
        if not items:
            return
        ptr = items[0].data(0, ROLE_PTR) or ""
        if ptr == "":
            QMessageBox.information(self, "Remove", "Non puoi rimuovere il root.")
            return
        if QMessageBox.question(self, "Remove", f"Remove {ptr}?") != QMessageBox.Yes:
            return
        try:
            new_doc = copy.deepcopy(self.doc)
            remove_at(new_doc, ptr)
            self._commit_doc(new_doc, note=f"remove {ptr}")
        except Exception as e:
            QMessageBox.warning(self, "Remove error", str(e))

    def _tree_rename(self) -> None:
        items = self.tree.selectedItems()
        if not items:
            return
        ptr = items[0].data(0, ROLE_PTR) or ""
        if ptr == "":
            QMessageBox.information(self, "Rename", "Non puoi rinominare il root.")
            return

        parts = split_pointer(ptr)
        if not parts:
            return
        last = parts[-1]
        parent_ptr = "/" + "/".join(jp_escape(p) for p in parts[:-1]) if len(parts) > 1 else ""
        parent_val = self.doc if parent_ptr == "" else get_at(self.doc, parent_ptr)

        if not isinstance(parent_val, dict):
            QMessageBox.information(self, "Rename", "Puoi rinominare solo chiavi dentro oggetti (dict).")
            return

        new_key, ok = self._prompt("Rename key", f"Rename '{last}' to:", last)
        if not ok or not new_key:
            return

        new_doc = copy.deepcopy(self.doc)
        pobj = new_doc if parent_ptr == "" else get_at(new_doc, parent_ptr)
        if last not in pobj:
            QMessageBox.warning(self, "Rename", "Chiave non trovata (documento cambiato).")
            return
        pobj[new_key] = pobj.pop(last)
        self._commit_doc(new_doc, note=f"rename {last} -> {new_key}")

    # Rules tab
    def _default_rules_example(self) -> str:
        return (
            "[\n"
            "  {\"op\": \"set\", \"path\": \"/version\", \"value\": 2},\n"
            "  {\"op\": \"when\",\n"
            "   \"if\": {\"path\": \"/env\", \"equals\": \"prod\"},\n"
            "   \"then\": [\n"
            "     {\"op\": \"set\", \"path\": \"/logging/level\", \"value\": \"warn\"}\n"
            "   ],\n"
            "   \"else\": [\n"
            "     {\"op\": \"set\", \"path\": \"/logging/level\", \"value\": \"debug\"}\n"
            "   ]\n"
            "  },\n"
            "  {\"op\": \"rename\", \"path\": \"/user\", \"from\": \"name\", \"to\": \"fullName\"}\n"
            "]\n"
        )

    def _insert_sample_rules(self) -> None:
        self.rules.setPlainText(self._default_rules_example())
        self.tabs.setCurrentIndex(1)

    def _preview_rules(self) -> None:
        try:
            ops = compile_rules(self.rules.toPlainText() or self._default_rules_example(), self.rules_fmt.currentText())
        except Exception as e:
            QMessageBox.warning(self, "Rules parse error", str(e))
            return

        before = pretty_json(self.doc, indent=2)
        res = apply_ops(self.doc, ops)
        after = pretty_json(res.new_doc, indent=2)

        diff = unified_diff(before, after)
        patch = json.dumps(res.ops, ensure_ascii=False, indent=2)

        report = ""
        if res.errors:
            report += "ERRORS:\n" + "\n".join(f"- {x}" for x in res.errors) + "\n\n"
        if res.warnings:
            report += "WARNINGS:\n" + "\n".join(f"- {x}" for x in res.warnings) + "\n\n"
        if not report:
            report = "No errors/warnings."

        self.diff_view.setPlainText(diff or "(no changes)")
        self.patch_view.setPlainText(patch)
        self.report_view.setPlainText(report)
        self.tabs.setCurrentIndex(2)

    def _apply_rules_commit(self) -> None:
        try:
            ops = compile_rules(self.rules.toPlainText() or self._default_rules_example(), self.rules_fmt.currentText())
        except Exception as e:
            QMessageBox.warning(self, "Rules parse error", str(e))
            return

        res = apply_ops(self.doc, ops)
        if res.errors:
            QMessageBox.warning(self, "Rules apply error", "Regole con errori:\n" + "\n".join(res.errors))
            self._preview_rules()
            return

        self._commit_doc(res.new_doc, note="apply rules")
        if self.chk_apply_to_text.isChecked():
            self._sync_guard = True
            try:
                self.text.setPlainText(pretty_json(self.doc, indent=2))
            finally:
                self._sync_guard = False
        self._preview_rules()

    # Batch tab
    def _pick_dir(self, line_edit: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select folder")
        if path:
            line_edit.setText(path)

    def _glob_to_regex(self, pat: str) -> str:
        s = re.escape(pat)
        s = s.replace(r"\*", ".*").replace(r"\?", ".")
        return "^" + s + "$"

    def _run_batch(self) -> None:
        in_dir = self.in_dir.text().strip()
        out_dir = self.out_dir.text().strip()
        pattern = (self.pattern.text() or "*.json").strip()
        try:
            max_files = int((self.max_files.text() or "1000").strip())
        except Exception:
            max_files = 1000

        if not in_dir or not os.path.isdir(in_dir):
            QMessageBox.warning(self, "Batch", "Seleziona una cartella input valida.")
            return
        if not out_dir:
            QMessageBox.warning(self, "Batch", "Seleziona una cartella output.")
            return
        os.makedirs(out_dir, exist_ok=True)

        try:
            ops = compile_rules(self.rules.toPlainText() or self._default_rules_example(), self.rules_fmt.currentText())
        except Exception as e:
            QMessageBox.warning(self, "Rules parse error", str(e))
            return

        rx = self._glob_to_regex(pattern)
        files: List[str] = []
        for root, _, names in os.walk(in_dir):
            for n in names:
                if re.match(rx, n):
                    files.append(os.path.join(root, n))
                    if len(files) >= max_files:
                        break
            if len(files) >= max_files:
                break

        if not files:
            QMessageBox.information(self, "Batch", "Nessun file corrisponde al pattern.")
            return

        prog = QProgressDialog("Running batch...", "Cancel", 0, len(files), self)
        prog.setWindowModality(Qt.WindowModal)
        prog.setMinimumDuration(0)

        ok_count = 0
        err_count = 0
        self.batch_log.clear()

        for i, path in enumerate(files, start=1):
            prog.setValue(i - 1)
            if prog.wasCanceled():
                break

            rel = os.path.relpath(path, in_dir)
            out_path = os.path.join(out_dir, rel)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)

            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                res = apply_ops(data, ops)
                if res.errors:
                    err_count += 1
                    self.batch_log.appendPlainText(f"[ERROR] {rel}: " + "; ".join(res.errors))
                    continue

                atomic_write(out_path, pretty_json(res.new_doc, indent=2))
                ok_count += 1
                self.batch_log.appendPlainText(f"[OK] {rel} -> {os.path.relpath(out_path, out_dir)}")

            except Exception as e:
                err_count += 1
                self.batch_log.appendPlainText(f"[ERROR] {rel}: {e}")

        prog.setValue(len(files))
        self.batch_log.appendPlainText(f"\nDone. OK={ok_count}, ERR={err_count}, TOTAL={min(len(files), max_files)}")
        self.tabs.setCurrentIndex(3)

    # Commit + undo/redo
    def _commit_doc(self, new_doc: Any, note: str) -> None:
        self.doc = new_doc
        self.undo.push(self.doc, note)
        self._sync_guard = True
        try:
            build_tree(self.tree, self.doc)
            self.lbl_status.setText(f"Committed: {note}")
            self._update_actions()
        finally:
            self._sync_guard = False

    def _undo(self) -> None:
        snap = self.undo.undo()
        if not snap:
            return
        self.doc = copy.deepcopy(snap.doc)
        self._refresh_all()

    def _redo(self) -> None:
        snap = self.undo.redo()
        if not snap:
            return
        self.doc = copy.deepcopy(snap.doc)
        self._refresh_all()

    # Small prompt helper
    def _prompt(self, title: str, label: str, default: str) -> Tuple[str, bool]:
        dlg = QMessageBox(self)
        dlg.setWindowTitle(title)
        dlg.setText(label)
        dlg.setIcon(QMessageBox.Question)
        inp = QLineEdit(dlg)
        inp.setText(default)
        inp.setMinimumWidth(560)
        dlg.layout().addWidget(inp, 1, 1, 1, dlg.layout().columnCount())
        dlg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        ret = dlg.exec()
        return inp.text(), (ret == QMessageBox.Ok)

    def _about(self) -> None:
        QMessageBox.information(
            self, "About",
            "JSON Suite GUI (v3)\n\n"
            "- Text + Tree editor\n"
            "- Rules + Preview diff/patch\n"
            "- Batch apply\n"
            "- Undo/Redo\n"
        )

def main() -> None:
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
