#!/usr/bin/env python3
"""SettingsTab — plant channel and CSV config for PlantPi UI."""

from QtShim import (
    QWidget, QLabel, QLineEdit, QPushButton, QCheckBox, QSpinBox, QGroupBox,
    QHBoxLayout, QVBoxLayout, QGridLayout, QFileDialog,
    pyqtSignal, Qt, QFont,
    Align, FileDialog, exec_dialog,
)

_HCENTER = Align.HCenter
_CENTER  = Align.Center


class BigSpinBox(QWidget):
    """Large number display with ▲/▼ buttons stacked above/below.

    Mimics QSpinBox's value/range API.  When value == minimum and
    special_minimum_text is set, that string is shown instead of the number.
    """

    valueChanged = pyqtSignal(int)

    def __init__(self, minimum=0, maximum=99, value=1,
                 special_minimum_text='', parent=None):
        super().__init__(parent)
        self._min = minimum
        self._max = maximum
        self._special = special_minimum_text
        self._value = max(minimum, min(maximum, value))

        self._up_btn = QPushButton('▲')
        self._dn_btn = QPushButton('▼')
        self._up_btn.setFixedSize(54, 36)
        self._dn_btn.setFixedSize(54, 36)
        self._up_btn.clicked.connect(self._increment)
        self._dn_btn.clicked.connect(self._decrement)

        self._lbl = QLabel()
        self._lbl.setAlignment(_CENTER)
        f = QFont()
        f.setPointSize(24)
        f.setBold(True)
        self._lbl.setFont(f)
        self._lbl.setMinimumWidth(54)
        self._refresh_label()

        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)
        col.addWidget(self._up_btn, alignment=_HCENTER)
        col.addWidget(self._lbl)
        col.addWidget(self._dn_btn, alignment=_HCENTER)

    def _refresh_label(self):
        if self._special and self._value == self._min:
            self._lbl.setText(self._special)
        else:
            self._lbl.setText(str(self._value))

    def _increment(self):
        if self._value < self._max:
            self._value += 1
            self._refresh_label()
            self.valueChanged.emit(self._value)

    def _decrement(self):
        if self._value > self._min:
            self._value -= 1
            self._refresh_label()
            self.valueChanged.emit(self._value)

    def value(self):
        return self._value

    def setValue(self, v):
        v = max(self._min, min(self._max, int(v)))
        if v != self._value:
            self._value = v
            self._refresh_label()

    def setRange(self, minimum, maximum):
        self._min = minimum
        self._max = maximum
        self.setValue(self._value)

    def setToolTip(self, tip):
        super().setToolTip(tip)
        self._lbl.setToolTip(tip)


class SettingsTab(QWidget):
    settings_saved        = pyqtSignal(dict)
    save_config_requested = pyqtSignal(str)

    def __init__(self, settings, max_plants=8, parent=None):
        super().__init__(parent)
        self._cfg_path = settings.get('cfg_path', '')

        tip_nplants = (f'Max {max_plants} — limited to live plant controllers'
                       if max_plants < 8 else
                       'Max 8 — one per ADC channel (hardware limit)')

        # ---- Number of plants (BigSpinBox centred at top) ---------------
        self._n_plants = BigSpinBox(minimum=1, maximum=max_plants,
                                    value=min(settings.get('plant_count', 1), max_plants))
        self._n_plants.setToolTip(tip_nplants)

        n_lbl = QLabel('Number of plants')
        n_lbl.setAlignment(_CENTER)
        n_lbl.setToolTip(tip_nplants)

        n_col = QVBoxLayout()
        n_col.setSpacing(4)
        n_col.addWidget(self._n_plants, alignment=_HCENTER)
        n_col.addWidget(n_lbl)

        n_row = QHBoxLayout()
        n_row.addStretch()
        n_row.addLayout(n_col)
        n_row.addStretch()

        # ---- Plant channel assignment (grid: rows=fields, cols=plants) --
        self._ch_container = QWidget()
        self._sensor_grid = QGridLayout(self._ch_container)
        self._sensor_grid.setContentsMargins(0, 0, 0, 0)
        self._sensor_grid.setSpacing(6)

        # Fixed row labels in column 0
        _RIGHT = Align.Right
        for r, (txt, tip) in enumerate([
            ('Top channel:',    'ADC channel 0–7 for the top (or only) soil moisture sensor'),
            ('Bottom channel:', 'ADC channel 0–7 for the bottom sensor; — = none'),
            ('Pump GPIO:',      'GPIO pin number connected to the pump relay'),
        ], start=1):
            lbl = QLabel(txt)
            lbl.setAlignment(_RIGHT)
            lbl.setToolTip(tip)
            self._sensor_grid.addWidget(lbl, r, 0)

        self._sensor_rows = []
        self._rebuild_sensor_rows(
            settings.get('plant_count', 1),
            settings.get('plants', []))
        self._n_plants.valueChanged.connect(lambda v: self._rebuild_sensor_rows(v))

        # ---- CSV path (below channel rows) ------------------------------
        _csv_tip = 'Path to the CSV file where sensor readings are logged'
        csv_lbl = QLabel('Data file:')
        csv_lbl.setToolTip(_csv_tip)

        self._csv_edit = QLineEdit(settings.get('csv_path', ''))
        self._csv_edit.setMinimumHeight(36)
        self._csv_edit.setToolTip(_csv_tip)

        browse = QPushButton('...')
        browse.setFixedWidth(40)
        browse.setMinimumHeight(36)
        browse.setToolTip('Browse for a CSV file')
        browse.clicked.connect(self._browse_csv)

        csv_row = QHBoxLayout()
        csv_row.addWidget(csv_lbl)
        csv_row.addWidget(self._csv_edit)
        csv_row.addWidget(browse)

        # ---- Run options ------------------------------------------------
        def _chk(text, tip, key, default=False):
            cb = QCheckBox(text)
            cb.setToolTip(tip)
            cb.setChecked(bool(settings.get(key, default)))
            return cb

        self._test      = _chk('Test mode',              'Sample every 0.5 s instead of long_sample minutes',  'test')
        self._verbose   = _chk('Verbose',                'Print each sensor reading to stdout',                 'verbose')
        self._quiet     = _chk('Quiet (no email)',        'Disable all email notifications',                    'quiet')
        self._simu_quit = _chk('Quit on simulator end',  'Auto-quit when simulator CSV data is exhausted',      'simu_quit')

        chk_grid = QGridLayout()
        chk_grid.setSpacing(6)
        chk_grid.addWidget(self._test,      0, 0)
        chk_grid.addWidget(self._verbose,   0, 1)
        chk_grid.addWidget(self._quiet,     1, 0)
        chk_grid.addWidget(self._simu_quit, 1, 1)

        def _ispin(lo, hi, val, tip):
            sb = QSpinBox()
            sb.setRange(lo, hi)
            sb.setValue(max(lo, min(hi, int(val))))
            sb.setMinimumHeight(30)
            sb.setToolTip(tip)
            return sb

        self._long_sample   = _ispin(1, 1440, settings.get('long_sample', 30),
                                     'Sensor sampling interval in minutes (test mode ignores this)')
        self._cistern_gpio  = _ispin(0, 27,   settings.get('cistern_gpio', 0),
                                     'GPIO pin for the cistern level sensor (0 = not used)')

        spin_row = QHBoxLayout()
        spin_row.addWidget(QLabel('Sample interval (min):'))
        spin_row.addWidget(self._long_sample)
        spin_row.addSpacing(16)
        spin_row.addWidget(QLabel('Cistern GPIO:'))
        spin_row.addWidget(self._cistern_gpio)
        spin_row.addStretch()

        _simu_tip = 'Path to a simulator CSV file; leave blank to use zero sensor data'
        simu_lbl = QLabel('Simulator file:')
        simu_lbl.setToolTip(_simu_tip)
        self._simu_edit = QLineEdit(settings.get('simulator', ''))
        self._simu_edit.setMinimumHeight(30)
        self._simu_edit.setToolTip(_simu_tip)
        simu_browse = QPushButton('...')
        simu_browse.setFixedWidth(40)
        simu_browse.setMinimumHeight(30)
        simu_browse.setToolTip('Browse for a simulator CSV file')
        simu_browse.clicked.connect(self._browse_simu)

        simu_row = QHBoxLayout()
        simu_row.addWidget(simu_lbl)
        simu_row.addWidget(self._simu_edit)
        simu_row.addWidget(simu_browse)

        run_box = QGroupBox('Run Options')
        run_layout = QVBoxLayout(run_box)
        run_layout.setSpacing(8)
        run_layout.addLayout(chk_grid)
        run_layout.addLayout(spin_row)
        run_layout.addLayout(simu_row)

        # ---- Buttons (bottom) -------------------------------------------
        save_cfg_btn = QPushButton('Save Config…')
        save_cfg_btn.setMinimumHeight(36)
        save_cfg_btn.clicked.connect(self._save_config)

        apply_btn = QPushButton('Apply')
        apply_btn.setMinimumHeight(36)
        apply_btn.setMinimumWidth(100)
        apply_btn.clicked.connect(self._apply)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(save_cfg_btn)
        btn_row.addWidget(apply_btn)

        # ---- Assemble ---------------------------------------------------
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(8, 8, 8, 8)
        root.addLayout(n_row)
        root.addWidget(self._ch_container)
        root.addLayout(csv_row)
        root.addWidget(run_box)
        root.addStretch()
        root.addLayout(btn_row)

    def _rebuild_sensor_rows(self, n, plants=None):
        current = [(ts.value(), bs.value(), gs.value()) for ts, bs, gs in self._sensor_rows]

        # Remove plant header labels (row 0) and all spinboxes (rows 1-3),
        # keeping only the fixed row-label widgets in column 0.
        for r in range(4):
            for c in range(1, self._sensor_grid.columnCount()):
                item = self._sensor_grid.itemAtPosition(r, c)
                if item and item.widget():
                    item.widget().setParent(None)
                    item.widget().deleteLater()
        self._sensor_rows.clear()

        _CENTER = Align.Center
        for i in range(n):
            col = i + 1   # col 0 is the row-label column

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

            # Row 0: plant header
            hdr = QLabel(f'Plant {i+1}')
            hdr.setAlignment(_CENTER)
            self._sensor_grid.addWidget(hdr, 0, col)

            top_spin = BigSpinBox(minimum=0, maximum=7, value=int(top_v))
            top_spin.setToolTip('Top ADC channel (required, 0–7)')
            self._sensor_grid.addWidget(top_spin, 1, col)

            bot_spin = BigSpinBox(minimum=-1, maximum=7, value=int(bot_v),
                                  special_minimum_text='—')
            bot_spin.setToolTip('Bottom ADC channel (optional; — = none)')
            self._sensor_grid.addWidget(bot_spin, 2, col)

            gpio_spin = BigSpinBox(minimum=0, maximum=27, value=int(gpio_v))
            gpio_spin.setToolTip('Relay GPIO pin number')
            self._sensor_grid.addWidget(gpio_spin, 3, col)

            self._sensor_rows.append((top_spin, bot_spin, gpio_spin))

    def _browse_simu(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select simulator CSV', self._simu_edit.text(), 'CSV files (*.csv)')
        if path:
            self._simu_edit.setText(path)

    def _browse_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select CSV file', self._csv_edit.text(), 'CSV files (*.csv)')
        if path:
            self._csv_edit.setText(path)

    def _current(self):
        return {
            'plant_count':  self._n_plants.value(),
            'csv_path':     self._csv_edit.text(),
            'test':         self._test.isChecked(),
            'verbose':      self._verbose.isChecked(),
            'quiet':        self._quiet.isChecked(),
            'simu_quit':    self._simu_quit.isChecked(),
            'long_sample':  self._long_sample.value(),
            'cistern_gpio': self._cistern_gpio.value(),
            'simulator':    self._simu_edit.text(),
            'sensors': [
                {
                    'top_channel':    ts.value(),
                    'bottom_channel': bs.value() if bs.value() >= 0 else None,
                    'pump_gpio':      gs.value(),
                }
                for ts, bs, gs in self._sensor_rows
            ],
        }

    def _save_config(self):
        dlg = QFileDialog(self, 'Save Config', self._cfg_path, 'JSON files (*.json)')
        dlg.setAcceptMode(FileDialog.AcceptSave)
        dlg.setFileMode(FileDialog.AnyFile)
        dlg.setOption(FileDialog.DontUseNativeDialog, True)
        if self._cfg_path:
            dlg.selectFile(self._cfg_path)
        if exec_dialog(dlg):
            files = dlg.selectedFiles()
            if files:
                path = files[0]
                if not path.endswith('.json'):
                    path += '.json'
                self._cfg_path = path
                self.save_config_requested.emit(path)

    def _apply(self):
        self.settings_saved.emit(self._current())

    def current_settings(self):
        return self._current()
