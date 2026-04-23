#!/usr/bin/env python3
"""ProfilesTab — plant and soil profile editor for PlantPi UI."""

import os

from QtShim import (
    QWidget, QLabel, QLineEdit, QPushButton, QSpinBox, QDoubleSpinBox,
    QHBoxLayout, QVBoxLayout, QGridLayout, QSplitter, QSplitterHandle,
    QListWidget, QListWidgetItem, QAbstractItemView, QFileDialog, QMessageBox, QInputDialog,
    QFrame, Qt, pyqtSignal, QPainter, QColor,
    Align, Frame, ItemView, MessageBox, Orientation,
)

from _utils import (
    PROFILES_DIR, SOIL_PROFILES_DIR,
    _load_json, _save_json_atomic, _profile_names, _name_to_filename,
)

_RIGHT = Align.Right

_LINE_COLOR  = QColor('#555555')
_HOVER_COLOR = QColor('#3399ff')


class _SplitterHandle(QSplitterHandle):
    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self._hovered = False
        self.setFixedWidth(8)

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), self.palette().window())
        color = _HOVER_COLOR if self._hovered else _LINE_COLOR
        cx = self.width() // 2
        p.setPen(color)
        p.drawLine(cx, 0, cx, self.height())
        p.end()


class _Splitter(QSplitter):
    def createHandle(self):
        return _SplitterHandle(self.orientation(), self)


class ProfileSection(QWidget):
    """Reusable list+form editor for plant or soil profiles."""

    changed = pyqtSignal()

    def __init__(self, title, directory, fields_builder, parent=None):
        super().__init__(parent)
        self._dir = directory
        self._fields_builder = fields_builder
        self._widgets = {}
        self._selected = None

        os.makedirs(directory, exist_ok=True)

        lbl = QLabel(f'<b>{title}</b>')
        self._list = QListWidget()
        _ext = ItemView.ExtendedSelection
        self._list.setSelectionMode(_ext)
        self._list.itemSelectionChanged.connect(self._on_select)
        self._list.currentItemChanged.connect(self._update_action_btns)

        btn_new      = QPushButton('New')
        self._btn_save = QPushButton('Save')
        self._btn_del  = QPushButton('Delete')
        self._btn_ren  = QPushButton('Rename')
        btn_new.clicked.connect(self._new)
        self._btn_save.clicked.connect(self._save)
        self._btn_del.clicked.connect(self._delete)
        self._btn_ren.clicked.connect(self._rename)

        btn_row = QHBoxLayout()
        btn_row.addWidget(btn_new)
        btn_row.addWidget(self._btn_save)
        btn_row.addWidget(self._btn_del)
        btn_row.addWidget(self._btn_ren)

        self._grid = QGridLayout()
        self._grid.setSpacing(6)
        self._grid.setColumnStretch(1, 1)
        self._grid_row = 0

        for entry in self._fields_builder():
            label, widget, key = entry[0], entry[1], entry[2]
            tip = entry[3] if len(entry) > 3 else ''
            self._widgets[key] = widget
            lbl_w = QLabel(label)
            lbl_w.setAlignment(_RIGHT)
            if tip:
                lbl_w.setToolTip(tip)
                widget.setToolTip(tip)
            self._grid.addWidget(lbl_w, self._grid_row, 0, _RIGHT)
            if isinstance(widget, (QDoubleSpinBox, QSpinBox, QLineEdit)):
                self._grid.addWidget(widget, self._grid_row, 1, 1, 2)
            else:
                self._grid.addWidget(widget, self._grid_row, 1)
            if hasattr(widget, 'valueChanged'):
                widget.valueChanged.connect(self._on_field_change)
            self._grid_row += 1

        self._add_extra_grid_rows()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(lbl)
        layout.addWidget(self._list, 1)
        layout.addLayout(btn_row)
        layout.addLayout(self._grid)
        layout.addStretch()

        self._reload_list()
        self._update_action_btns()

    # ------------------------------------------------------------------

    def _reload_list(self):
        self._list.clear()
        for name in _profile_names(self._dir):
            self._list.addItem(QListWidgetItem(name))
        if self._list.count() > 0 and self._list.currentItem() is None:
            self._list.setCurrentRow(0)

    def _on_select(self):
        if len(self._list.selectedItems()) > 1:
            self._set_editable(False)
            self._update_action_btns()
            return
        cur = self._list.currentItem()
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
        pass

    def _is_default_selected(self):
        cur = self._list.currentItem()
        return cur is not None and cur.text() == _DEFAULT_ITEM

    def _update_action_btns(self, *_):
        """Enable/disable save, delete, rename based on current selection."""
        is_default = self._is_default_selected()
        has_sel    = self._list.currentItem() is not None
        multi_sel = len(self._list.selectedItems()) > 1
        self._btn_save.setEnabled(has_sel and not is_default and not multi_sel)
        self._btn_del.setEnabled(has_sel and not is_default)
        self._btn_ren.setEnabled(has_sel and not is_default and not multi_sel)

    def _add_extra_grid_rows(self):
        """Hook for subclasses to append rows to self._grid."""
        pass

    def _new_data(self, fname):
        data = {}
        for key, widget in self._widgets.items():
            if key == 'name':
                data[key] = fname.replace('_', ' ').title()
            elif isinstance(widget, QLineEdit):
                data[key] = ''
            elif isinstance(widget, QDoubleSpinBox):
                mid = (widget.minimum() + widget.maximum()) / 2
                data[key] = round(mid, widget.decimals())
            elif isinstance(widget, QSpinBox):
                data[key] = (widget.minimum() + widget.maximum()) // 2
        return data

    def _new(self):
        existing = set(_profile_names(self._dir))
        base = 'new_profile'
        fname = base
        i = 1
        while fname in existing:
            fname = f'{base}_{i}'
            i += 1
        _save_json_atomic(os.path.join(self._dir, fname + '.json'), self._new_data(fname))
        self._reload_list()
        self.changed.emit()
        for row in range(self._list.count()):
            if self._list.item(row).text() == fname:
                self._list.setCurrentRow(row)
                break

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
        for i in range(self._list.count()):
            if self._list.item(i).text() == fname:
                self._list.setCurrentRow(i)
                break

    def _delete(self):
        sel_rows = self._list.selectedIndexes()
        if len(sel_rows) > 1:
            if QMessageBox.question(self, 'Delete', f'Delete {len(sel_rows)} profiles?',
                MessageBox.Yes | MessageBox.No) != MessageBox.Yes:
                return
            for row in sel_rows:
                try:
                    os.remove(os.path.join(self._dir, self._list.item(row.row()).text() + '.json'))
                except OSError:
                    pass
            self._reload_list()
            self.changed.emit()
            return

        cur = self._list.currentItem()
        if not cur:
            return
        name = cur.text()
        if QMessageBox.question(self, 'Delete', f'Delete profile "{name}"?',
                MessageBox.Yes | MessageBox.No) != MessageBox.Yes:
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


_PLANT_DEFAULTS = {
    'name':         'Default',
    'icon':         'None',
    'moisture_min': 3.0,
    'moisture_max': 7.0,
}
_SOIL_DEFAULTS = {
    'dry_sensor': 0.428,
    'wet_sensor': 0.283,
    'dry_std':    1.5,
    'wet_std':    10.0,
}
_DEFAULT_ITEM = '— default —'


class PlantProfileSection(ProfileSection):
    """Plant section with a non-editable default entry."""

    def _add_extra_grid_rows(self):
        icon_w = QLineEdit()
        icon_w.setPlaceholderText('Path to icon image…')
        icon_w.textChanged.connect(self._validate_icon)
        browse_btn = QPushButton('…')
        browse_btn.setFixedWidth(32)
        browse_btn.setToolTip('Browse for an icon image')
        browse_btn.clicked.connect(self._browse_icon)

        self._widgets['icon'] = icon_w

        lbl = QLabel('Icon:')
        lbl.setToolTip('Path to an icon image file (PNG, JPG, etc.)')
        icon_w.setToolTip('Path to an icon image file (PNG, JPG, etc.)')

        self._grid.addWidget(lbl,   self._grid_row, 0, _RIGHT)
        self._grid.addWidget(icon_w, self._grid_row, 1)
        self._grid.addWidget(browse_btn, self._grid_row, 2)
        self._grid_row += 1

    def _validate_icon(self, text):
        icon_w = self._widgets.get('icon')
        if icon_w is None:
            return
        if not text or os.path.isfile(text) or text == 'None':
            icon_w.setStyleSheet('')
        else:
            icon_w.setStyleSheet('QLineEdit { border: 1px solid #cc4444; }')

    def _browse_icon(self):
        icon_w = self._widgets.get('icon')
        current = icon_w.text() if icon_w else ''
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select Icon', current,
            'Images (*.png *.jpg *.jpeg *.svg *.bmp *.gif)')
        if path and icon_w:
            icon_w.setText(path)

    def _set_editable(self, editable):
        for w in self._widgets.values():
            w.setEnabled(editable)

    def _reload_list(self):
        self._list.clear()
        self._list.addItem(QListWidgetItem(_DEFAULT_ITEM))
        for name in _profile_names(self._dir):
            if name == 'default':
                continue
            self._list.addItem(QListWidgetItem(name))
        if self._list.currentItem() is None:
            self._list.setCurrentRow(0)

    def _on_select(self):
        if len(self._list.selectedItems()) > 1:
            self._set_editable(False)
            self._update_action_btns()
            return
        cur = self._list.currentItem()
        if cur is None:
            return
        name = cur.text()
        if name == _DEFAULT_ITEM:
            self._selected = 'default'
            self._widgets['name'].setText(_PLANT_DEFAULTS['name'])
            self._widgets['icon'].setText('None')
            self._widgets['moisture_min'].setValue(_PLANT_DEFAULTS['moisture_min'])
            self._widgets['moisture_max'].setValue(_PLANT_DEFAULTS['moisture_max'])
            self._set_editable(False)
            self._update_action_btns()
            return
        self._selected = name
        data = _load_json(os.path.join(self._dir, name + '.json'))
        for key, widget in self._widgets.items():
            val = data.get(key)
            if val is None:
                continue
            if isinstance(widget, QLineEdit):
                if key == 'icon' and not str(val):
                    widget.setText('None')
                else:
                    widget.setText(str(val))
            elif isinstance(widget, (QDoubleSpinBox, QSpinBox)):
                widget.setValue(float(val))
        self._set_editable(True)
        self._update_action_btns()

    def _set_editable(self, editable):
        for w in self._widgets.values():
            w.setEnabled(editable)

    def _delete(self):
        cur = self._list.currentItem()
        if cur and cur.text() == _DEFAULT_ITEM:
            return
        super()._delete()

    def _rename(self):
        cur = self._list.currentItem()
        if cur and cur.text() == _DEFAULT_ITEM:
            return
        super()._rename()

    def _save(self):
        cur = self._list.currentItem()
        if cur and cur.text() == _DEFAULT_ITEM:
            return
        icon_w = self._widgets.get('icon')
        if icon_w and icon_w.text() and not os.path.isfile(icon_w.text()):
            QMessageBox.warning(self, 'Invalid Icon',
                                f'Icon path does not exist:\n{icon_w.text()}')
            return
        super()._save()


class SoilProfileSection(ProfileSection):
    """Soil section with a default entry, paired sensor/std columns, and mapping preview."""

    def _add_extra_grid_rows(self):
        def _dspin(lo, hi, step, dec):
            w = QDoubleSpinBox()
            w.setRange(lo, hi)
            w.setSingleStep(step)
            w.setDecimals(dec)
            w.valueChanged.connect(self._on_field_change)
            return w

        self._widgets['dry_sensor'] = _dspin(0, 1, 0.001, 3)
        self._widgets['dry_std']    = _dspin(0, 10, 0.5, 1)
        self._widgets['wet_sensor'] = _dspin(0, 1, 0.001, 3)
        self._widgets['wet_std']    = _dspin(0, 10, 0.5, 1)
        self._soil_spinboxes = [
            self._widgets['dry_sensor'], self._widgets['dry_std'],
            self._widgets['wet_sensor'], self._widgets['wet_std'],
        ]
        self._load_soil_defaults()

        # Stretch name field across both data columns
        if 'name' in self._widgets:
            self._grid.removeWidget(self._widgets['name'])
            self._grid.addWidget(self._widgets['name'], 0, 1, 1, 4)

        def _hline():
            h = QFrame()
            h.setMinimumWidth(8)
            h.setFrameShape(Frame.HLine)
            h.setFrameShadow(Frame.Sunken)
            return h

        dry_row = self._grid_row
        wet_row = self._grid_row + 1

        # Dry row
        lbl_d = QLabel('Dry Sensor:')
        lbl_d.setAlignment(_RIGHT)
        self._grid.addWidget(lbl_d,                        dry_row, 0, _RIGHT)
        self._grid.addWidget(self._widgets['dry_sensor'],  dry_row, 1)
        self._grid.addWidget(_hline(),                     dry_row, 2)
        lbl_d_std = QLabel('Dry Standard:')
        lbl_d_std.setAlignment(_RIGHT)
        self._grid.addWidget(lbl_d_std,                    dry_row, 3, _RIGHT)
        self._grid.addWidget(self._widgets['dry_std'],     dry_row, 4)

        # Wet row
        lbl_w = QLabel('Wet Sensor:')
        lbl_w.setAlignment(_RIGHT)
        self._grid.addWidget(lbl_w,                        wet_row, 0, _RIGHT)
        self._grid.addWidget(self._widgets['wet_sensor'],  wet_row, 1)
        self._grid.addWidget(_hline(),                     wet_row, 2)
        lbl_w_std = QLabel('Wet Standard:')
        lbl_w_std.setAlignment(_RIGHT)
        self._grid.addWidget(lbl_w_std,                    wet_row, 3, _RIGHT)
        self._grid.addWidget(self._widgets['wet_std'],     wet_row, 4)

        self._grid_row = wet_row + 1

        self._grid.setColumnStretch(1, 1)
        self._grid.setColumnStretch(4, 1)

    def _load_soil_defaults(self):
        for key, val in _SOIL_DEFAULTS.items():
            self._widgets[key].setValue(val)

    def _set_soil_editable(self, editable):
        for w in self._soil_spinboxes:
            w.setEnabled(editable)
        if 'name' in self._widgets:
            self._widgets['name'].setEnabled(editable)

    def _reload_list(self):
        self._list.clear()
        self._list.addItem(QListWidgetItem(_DEFAULT_ITEM))
        for name in _profile_names(self._dir):
            self._list.addItem(QListWidgetItem(name))
        if self._list.currentItem() is None:
            self._list.setCurrentRow(0)

    def _on_select(self):
        if len(self._list.selectedItems()) > 1:
            self._set_soil_editable(False)
            self._update_action_btns()
            return
        cur = self._list.currentItem()
        if cur is None:
            return
        name = cur.text()
        if name == _DEFAULT_ITEM:
            self._selected = None
            self._load_soil_defaults()
            if 'name' in self._widgets:
                self._widgets['name'].setText('Default')
            self._set_soil_editable(False)
            self._on_field_change()
            self._update_action_btns()
            return
        self._selected = name
        data = _load_json(os.path.join(self._dir, name + '.json'))
        if 'name' in self._widgets:
            self._widgets['name'].setText(data.get('name', name))
        for key in ('dry_sensor', 'wet_sensor', 'dry_std', 'wet_std'):
            if key in data:
                self._widgets[key].setValue(float(data[key]))
        self._set_soil_editable(True)
        self._on_field_change()
        self._update_action_btns()

    def _on_field_change(self):
        try:
            ds = self._widgets['dry_sensor'].value()
            ws = self._widgets['wet_sensor'].value()
            dd = self._widgets['dry_std'].value()
            wd = self._widgets['wet_std'].value()
            m = (wd - dd) / (ws - ds) if ws != ds else 0
            b = dd - m * ds
            self._extra_lbl.setText(
                f'Mapping: {ds:.3f} → {m*ds+b:.2f},  {ws:.3f} → {m*ws+b:.2f}')
        except Exception:
            pass

    def _new_data(self, fname):
        return {
            'name':       fname.replace('_', ' ').title(),
            **_SOIL_DEFAULTS,
        }

    def _delete(self):
        cur = self._list.currentItem()
        if cur and cur.text() == _DEFAULT_ITEM:
            return
        super()._delete()

    def _rename(self):
        cur = self._list.currentItem()
        if cur and cur.text() == _DEFAULT_ITEM:
            return
        super()._rename()

    def _save(self):
        if self._selected is None:
            return
        ds = self._widgets['dry_sensor'].value()
        ws = self._widgets['wet_sensor'].value()
        if ds == ws:
            QMessageBox.warning(self, 'Invalid Soil Profile',
                                'Dry sensor and wet sensor values cannot be equal — '
                                'this would cause a division by zero in the moisture mapping.')
            return
        super()._save()


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
    return [
        ('Display name:', name_w, 'name',
         'Soil profile display name — the filename is derived from this'),
    ]


class ProfilesTab(QWidget):
    profiles_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._plant_sec = PlantProfileSection(
            'Plant Profiles', PROFILES_DIR, _plant_fields)
        self._soil_sec = SoilProfileSection(
            'Soil Profiles', SOIL_PROFILES_DIR, _soil_fields)

        self._plant_sec.changed.connect(self._on_changed)
        self._soil_sec.changed.connect(self._on_changed)

        splitter = _Splitter(Orientation.Horizontal)
        splitter.addWidget(self._plant_sec)
        splitter.addWidget(self._soil_sec)
        splitter.setSizes([400, 400])

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.addWidget(splitter)

    def _on_changed(self):
        self.profiles_changed.emit(self._plant_sec.profile_names())

    def plant_profile_names(self):
        return self._plant_sec.profile_names()

    def reload(self):
        self._plant_sec._reload_list()
        self._soil_sec._reload_list()
