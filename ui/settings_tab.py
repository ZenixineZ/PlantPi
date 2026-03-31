#!/usr/bin/env python3
"""SettingsTab — plant channel and CSV config for PlantPi UI."""

try:
    from PyQt5.QtWidgets import (
        QWidget, QLabel, QLineEdit, QPushButton, QSpinBox,
        QHBoxLayout, QVBoxLayout, QFormLayout, QFileDialog,
    )
    from PyQt5.QtCore import pyqtSignal
    _QT = 5
except ImportError:
    from PyQt6.QtWidgets import (
        QWidget, QLabel, QLineEdit, QPushButton, QSpinBox,
        QHBoxLayout, QVBoxLayout, QFormLayout, QFileDialog,
    )
    from PyQt6.QtCore import pyqtSignal
    _QT = 6

from _utils import _HERE


class SettingsTab(QWidget):
    settings_saved    = pyqtSignal(dict)
    save_as_requested = pyqtSignal(str)   # emits chosen file path

    def __init__(self, settings, max_plants=8, parent=None):
        super().__init__(parent)

        form = QFormLayout()

        self._n_plants = QSpinBox()
        self._n_plants.setRange(1, max_plants)
        self._n_plants.setValue(min(settings.get('plant_count', 1), max_plants))
        tip = (f'Max {max_plants} — limited to live plant controllers'
               if max_plants < 8 else
               'Max 8 — one per ADC channel (hardware limit)')
        self._n_plants.setToolTip(tip)
        _lbl = QLabel('Number of plants:'); _lbl.setToolTip(tip)
        form.addRow(_lbl, self._n_plants)

        csv_row = QHBoxLayout()
        self._csv_edit = QLineEdit(settings.get('csv_path', ''))
        _csv_tip = 'Path to the CSV file where sensor readings are logged'
        self._csv_edit.setToolTip(_csv_tip)
        browse = QPushButton('...')
        browse.setFixedWidth(32)
        browse.setToolTip('Browse for a CSV file')
        browse.clicked.connect(self._browse_csv)
        csv_row.addWidget(self._csv_edit)
        csv_row.addWidget(browse)
        _lbl = QLabel('CSV file:'); _lbl.setToolTip(_csv_tip)
        form.addRow(_lbl, csv_row)

        # --- Plant channel assignment ---
        ch_group = QWidget()
        ch_vbox  = QVBoxLayout(ch_group)
        ch_vbox.setContentsMargins(0, 0, 0, 0)
        ch_vbox.setSpacing(4)

        # Column header
        _top_hdr = QLabel('Top Channel (required)')
        _top_hdr.setToolTip('ADC channel 0–7 for the top (or only) soil moisture sensor')
        _bot_hdr = QLabel('Bottom Channel')
        _bot_hdr.setToolTip('ADC channel 0–7 for the bottom sensor; set to None to omit')
        _gpio_hdr = QLabel('Pump GPIO')
        _gpio_hdr.setToolTip('GPIO pin number connected to the pump relay')
        hdr = QHBoxLayout()
        hdr.addWidget(QLabel(''), 1)
        hdr.addWidget(_top_hdr, 2)
        hdr.addWidget(_bot_hdr, 2)
        hdr.addWidget(_gpio_hdr, 2)
        ch_vbox.addLayout(hdr)

        self._sensor_rows  = []   # list of (top_spin, bot_spin, gpio_spin)
        self._sensor_container = ch_vbox

        form.addRow('Plant channels:', ch_group)

        self._rebuild_sensor_rows(
            settings.get('plant_count', 1),
            settings.get('plants', []))
        self._n_plants.valueChanged.connect(
            lambda v: self._rebuild_sensor_rows(v))

        save_btn    = QPushButton('Save')
        save_as_btn = QPushButton('Save As…')
        save_btn.clicked.connect(self._save)
        save_as_btn.clicked.connect(self._save_as)

        btn_row = QHBoxLayout()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(save_as_btn)
        btn_row.addStretch()

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addLayout(btn_row)
        root.addStretch()

    def _rebuild_sensor_rows(self, n, plants=None):
        # Preserve current spinbox values for existing rows
        current = [(ts.value(), bs.value(), gs.value()) for ts, bs, gs in self._sensor_rows]

        # Remove old row widgets (everything after the header HBoxLayout)
        while self._sensor_container.count() > 1:
            item = self._sensor_container.takeAt(1)
            if item.widget():
                item.widget().deleteLater()
        self._sensor_rows.clear()

        for i in range(n):
            if plants is not None and i < len(plants):
                pcfg    = plants[i]
                top_v   = pcfg.get('top_channel')
                top_v   = top_v if top_v is not None else i % 8
                bot_raw = pcfg.get('bottom_channel')
                bot_v   = bot_raw if bot_raw is not None else -1
                gpio_v  = pcfg.get('pump_gpio', 0)
            elif i < len(current):
                top_v, bot_v, gpio_v = current[i]
            else:
                top_v  = i % 8
                bot_v  = -1
                gpio_v = 0

            top_spin = QSpinBox()
            top_spin.setRange(0, 7)
            top_spin.setValue(int(top_v))
            top_spin.setToolTip('Top ADC channel (required, 0–7)')

            bot_spin = QSpinBox()
            bot_spin.setRange(-1, 7)
            bot_spin.setSpecialValueText('None')
            bot_spin.setValue(int(bot_v))
            bot_spin.setToolTip('Bottom ADC channel (optional)')

            gpio_spin = QSpinBox()
            gpio_spin.setRange(0, 27)
            gpio_spin.setValue(int(gpio_v))
            gpio_spin.setToolTip('Relay GPIO pin number')

            _plant_lbl = QLabel(f'Plant {i}:')
            _plant_lbl.setToolTip(f'Channel and GPIO assignment for plant {i}')
            row = QHBoxLayout()
            row.addWidget(_plant_lbl, 1)
            row.addWidget(top_spin, 2)
            row.addWidget(bot_spin, 2)
            row.addWidget(gpio_spin, 2)

            row_widget = QWidget()
            row_widget.setLayout(row)
            self._sensor_container.addWidget(row_widget)
            self._sensor_rows.append((top_spin, bot_spin, gpio_spin))

    def _browse_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select CSV file', self._csv_edit.text(), 'CSV files (*.csv)')
        if path:
            self._csv_edit.setText(path)

    def _current(self):
        return {
            'plant_count': self._n_plants.value(),
            'csv_path':    self._csv_edit.text(),
            'sensors': [
                {
                    'top_channel':    ts.value(),
                    'bottom_channel': bs.value() if bs.value() >= 0 else None,
                    'pump_gpio':      gs.value(),
                }
                for ts, bs, gs in self._sensor_rows
            ],
        }

    def _save(self):
        self.settings_saved.emit(self._current())

    def _save_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, 'Save config as…', _HERE, 'JSON files (*.json)')
        if path:
            self.settings_saved.emit(self._current())   # apply first
            self.save_as_requested.emit(path)

    def current_settings(self):
        return self._current()
