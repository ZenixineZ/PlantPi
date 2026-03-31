#!/usr/bin/env python3
"""ProfilesTab — plant and soil profile editor for PlantPi UI."""

import os

try:
    from PyQt5.QtWidgets import (
        QWidget, QLabel, QLineEdit, QPushButton, QSpinBox, QDoubleSpinBox,
        QHBoxLayout, QVBoxLayout, QFormLayout, QSplitter,
        QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QInputDialog,
    )
    from PyQt5.QtCore import Qt, pyqtSignal
    _QT = 5
except ImportError:
    from PyQt6.QtWidgets import (
        QWidget, QLabel, QLineEdit, QPushButton, QSpinBox, QDoubleSpinBox,
        QHBoxLayout, QVBoxLayout, QFormLayout, QSplitter,
        QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QInputDialog,
    )
    from PyQt6.QtCore import Qt, pyqtSignal
    _QT = 6

from _utils import (
    PROFILES_DIR, SOIL_PROFILES_DIR,
    _load_json, _save_json_atomic, _profile_names, _name_to_filename,
)


class ProfileSection(QWidget):
    """Reusable list+form editor for plant or soil profiles."""

    changed = pyqtSignal()

    def __init__(self, title, directory, fields_builder, parent=None):
        """
        fields_builder: callable() -> list of (label, widget, key)
        """
        super().__init__(parent)
        self._dir = directory
        self._fields_builder = fields_builder
        self._widgets = {}   # key -> widget
        self._selected = None

        os.makedirs(directory, exist_ok=True)

        lbl = QLabel(f'<b>{title}</b>')
        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_select)

        btn_new = QPushButton('New')
        btn_save = QPushButton('Save')
        btn_del = QPushButton('Delete')
        btn_ren = QPushButton('Rename')
        btn_new.clicked.connect(self._new)
        btn_save.clicked.connect(self._save)
        btn_del.clicked.connect(self._delete)
        btn_ren.clicked.connect(self._rename)

        btn_row = QHBoxLayout()
        btn_row.addWidget(btn_new)
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_del)
        btn_row.addWidget(btn_ren)

        self._form = QFormLayout()

        # Build dynamic fields
        self._extra_label = None
        for entry in self._fields_builder():
            label, widget, key = entry[0], entry[1], entry[2]
            tip = entry[3] if len(entry) > 3 else ''
            self._widgets[key] = widget
            lbl_widget = QLabel(label)
            if tip:
                lbl_widget.setToolTip(tip)
                widget.setToolTip(tip)
            self._form.addRow(lbl_widget, widget)
            if hasattr(widget, 'valueChanged'):
                widget.valueChanged.connect(self._on_field_change)

        self._extra_lbl = QLabel('')
        self._form.addRow('', self._extra_lbl)

        left = QVBoxLayout()
        left.addWidget(lbl)
        left.addWidget(self._list)
        left.addLayout(btn_row)

        right = QVBoxLayout()
        right.addLayout(self._form)
        right.addStretch()

        layout = QHBoxLayout(self)
        layout.addLayout(left, 1)
        layout.addLayout(right, 2)

        self._reload_list()

    def _reload_list(self):
        self._list.clear()
        for name in _profile_names(self._dir):
            self._list.addItem(QListWidgetItem(name))

    def _on_select(self, cur, _prev):
        if cur is None:
            return
        name = cur.text()
        self._selected = name
        data = _load_json(os.path.join(self._dir, name + '.json'))
        for key, widget in self._widgets.items():
            val = data.get(key)
            if val is None:
                continue
            if isinstance(widget, QLineEdit):
                widget.setText(str(val))
            elif isinstance(widget, (QDoubleSpinBox, QSpinBox)):
                widget.setValue(float(val))
        self._on_field_change()

    def _on_field_change(self):
        """Overridden by soil section to update preview label."""
        pass

    def _new(self):
        self._selected = None
        for widget in self._widgets.values():
            if isinstance(widget, QLineEdit):
                widget.setText('')
            elif isinstance(widget, (QDoubleSpinBox, QSpinBox)):
                widget.setValue(widget.minimum())
        self._list.clearSelection()

    def _save(self):
        if 'name' in self._widgets:
            fname = _name_to_filename(self._widgets['name'].text())
            if not fname:
                QMessageBox.warning(self, 'Save', 'Profile name cannot be empty.')
                return
            old_path = os.path.join(self._dir, self._selected + '.json') if self._selected else None
            new_path = os.path.join(self._dir, fname + '.json')
            if old_path and os.path.exists(old_path) and old_path != new_path:
                os.rename(old_path, new_path)
        elif self._selected:
            fname = self._selected
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, 'Save Profile', self._dir, 'JSON Files (*.json)')
            if not path:
                return
            fname = os.path.splitext(os.path.basename(path))[0]
        data = {}
        for key, widget in self._widgets.items():
            if isinstance(widget, QLineEdit):
                data[key] = widget.text()
            elif isinstance(widget, (QDoubleSpinBox, QSpinBox)):
                data[key] = widget.value()
        _save_json_atomic(os.path.join(self._dir, fname + '.json'), data)
        self._selected = fname
        self._reload_list()
        self.changed.emit()
        # Re-select
        for i in range(self._list.count()):
            if self._list.item(i).text() == fname:
                self._list.setCurrentRow(i)
                break

    def _delete(self):
        cur = self._list.currentItem()
        if not cur:
            return
        name = cur.text()
        if QMessageBox.question(
                self, 'Delete', f'Delete profile "{name}"?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                if _QT == 6 else
                QMessageBox.Yes | QMessageBox.No
        ) != (QMessageBox.StandardButton.Yes if _QT == 6 else QMessageBox.Yes):
            return
        try:
            os.remove(os.path.join(self._dir, name + '.json'))
        except OSError:
            pass
        self._reload_list()
        self.changed.emit()

    def _rename(self):
        cur = self._list.currentItem()
        if not cur:
            return
        old_name = cur.text()
        if 'name' in self._widgets:
            new_display, ok = QInputDialog.getText(
                self, 'Rename Profile', f'New display name for "{old_name}":',
                text=self._widgets['name'].text())
            if not ok or not new_display.strip():
                return
            self._widgets['name'].setText(new_display.strip())
            self._save()
        else:
            new_name, ok = QInputDialog.getText(
                self, 'Rename Profile', f'Rename "{old_name}" to:')
            if not ok or not new_name.strip():
                return
            new_name = new_name.strip()
            old_path = os.path.join(self._dir, old_name + '.json')
            new_path = os.path.join(self._dir, new_name + '.json')
            if os.path.exists(new_path):
                QMessageBox.warning(self, 'Rename', f'"{new_name}" already exists.')
                return
            os.rename(old_path, new_path)
            self._reload_list()
            self.changed.emit()
            for i in range(self._list.count()):
                if self._list.item(i).text() == new_name:
                    self._list.setCurrentRow(i)
                    break

    def profile_names(self):
        return _profile_names(self._dir)


class SoilProfileSection(ProfileSection):
    """Soil section with derived mapping preview."""

    def _on_field_change(self):
        try:
            ds = self._widgets['dry_sensor'].value()
            ws = self._widgets['wet_sensor'].value()
            dd = self._widgets['dry_std'].value()
            wd = self._widgets['wet_std'].value()
            m = (wd - dd) / (ws - ds) if ws != ds else 0
            b = dd - m * ds
            self._extra_lbl.setText(
                f'Mapping: {ds:.3f} → {m*ds+b:.2f}, {ws:.3f} → {m*ws+b:.2f}')
        except Exception:
            pass


def _plant_fields():
    name_w = QLineEdit()
    mmin_w = QDoubleSpinBox(); mmin_w.setRange(0, 10); mmin_w.setSingleStep(0.5)
    mmax_w = QDoubleSpinBox(); mmax_w.setRange(0, 10); mmax_w.setSingleStep(0.5)
    return [
        ('Display name:', name_w, 'name',
         'Plant display name — the filename is derived from this (parenthetical suffixes stripped)'),
        ('Moisture min:', mmin_w, 'moisture_min',
         'Pump activates when moisture drops below this level (0–10 scale)'),
        ('Moisture max:', mmax_w, 'moisture_max',
         'Pump stops when moisture reaches this level (0–10 scale)'),
    ]


def _soil_fields():
    name_w = QLineEdit()
    ds_w = QDoubleSpinBox(); ds_w.setRange(0, 1); ds_w.setSingleStep(0.001); ds_w.setDecimals(3)
    ws_w = QDoubleSpinBox(); ws_w.setRange(0, 1); ws_w.setSingleStep(0.001); ws_w.setDecimals(3)
    dd_w = QDoubleSpinBox(); dd_w.setRange(0, 10); dd_w.setSingleStep(0.5)
    wd_w = QDoubleSpinBox(); wd_w.setRange(0, 10); wd_w.setSingleStep(0.5)
    return [
        ('Display name:', name_w, 'name',
         'Soil profile display name — the filename is derived from this'),
        ('Dry sensor:', ds_w, 'dry_sensor',
         'Normalized ADC reading when soil is completely dry (0–1); default 0.428'),
        ('Wet sensor:', ws_w, 'wet_sensor',
         'Normalized ADC reading when soil is fully saturated (0–1); default 0.283'),
        ('Dry std:', dd_w, 'dry_std',
         'Moisture scale output (0–10) that corresponds to the dry sensor reading; default 1.5'),
        ('Wet std:', wd_w, 'wet_std',
         'Moisture scale output (0–10) that corresponds to the wet sensor reading; default 10'),
    ]


class ProfilesTab(QWidget):
    profiles_changed = pyqtSignal(list)   # updated plant profile names

    def __init__(self, parent=None):
        super().__init__(parent)

        self._plant_sec = ProfileSection(
            'Plant Profiles', PROFILES_DIR, _plant_fields)
        self._soil_sec = SoilProfileSection(
            'Soil Profiles', SOIL_PROFILES_DIR, _soil_fields)

        self._plant_sec.changed.connect(self._on_changed)
        self._soil_sec.changed.connect(self._on_changed)

        splitter = QSplitter(
            Qt.Orientation.Horizontal if _QT == 6 else Qt.Horizontal)
        splitter.addWidget(self._plant_sec)
        splitter.addWidget(self._soil_sec)
        splitter.setSizes([400, 400])

        root = QVBoxLayout(self)
        root.addWidget(splitter)

    def _on_changed(self):
        self.profiles_changed.emit(self._plant_sec.profile_names())

    def plant_profile_names(self):
        return self._plant_sec.profile_names()

    def reload(self):
        """Refresh both lists (e.g. after a save from a PlantCard)."""
        self._plant_sec._reload_list()
        self._soil_sec._reload_list()
