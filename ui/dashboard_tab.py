#!/usr/bin/env python3
"""DashboardTab — live plant status cards for PlantPi UI."""

import os

try:
    from PyQt5.QtWidgets import (
        QWidget, QFrame, QLabel, QLineEdit, QPushButton, QDoubleSpinBox,
        QGroupBox, QTextEdit, QHBoxLayout, QVBoxLayout,
        QFormLayout, QStackedWidget, QSizePolicy, QComboBox,
        QMessageBox,
    )
    from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QSize, QRectF
    from PyQt5.QtGui import QPainter, QColor, QBrush, QPen, QFont, QPainterPath, QIcon
    _QT = 5
except ImportError:
    from PyQt6.QtWidgets import (
        QWidget, QFrame, QLabel, QLineEdit, QPushButton, QDoubleSpinBox,
        QGroupBox, QTextEdit, QHBoxLayout, QVBoxLayout,
        QFormLayout, QStackedWidget, QSizePolicy, QComboBox,
        QMessageBox,
    )
    from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize, QRectF
    from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QFont, QPainterPath, QIcon
    _QT = 6

from _utils import (
    PROFILES_DIR, SOIL_PROFILES_DIR,
    _load_json, _save_json_atomic, _profile_display_map, _soil_profile_names,
    _name_to_filename,
)


# Three greys: darkest at the outer edge of the card, lightest at the center
_GREY_1 = '#777777'   # plant index
_GREY_2 = '#999999'   # plant name
_GREY_3 = '#bbbbbb'   # moisture value


# ---------------------------------------------------------------------------
# PlantIcon
# ---------------------------------------------------------------------------
class PlantIcon(QWidget):
    """Draws a simple pot + plant. Shows water drops when watering=True."""

    _W, _H = 80, 100

    def __init__(self, parent=None):
        super().__init__(parent)
        self._watering = False
        self.setFixedSize(self._W, self._H)

    @property
    def watering(self):
        return self._watering

    @watering.setter
    def watering(self, val):
        if val != self._watering:
            self._watering = val
            self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing if _QT == 6
                        else QPainter.Antialiasing)

        w, h = self._W, self._H

        # --- pot (brown trapezoid) ---
        pot_top_y   = h * 0.62
        pot_bot_y   = h * 0.92
        pot_top_w   = w * 0.52
        pot_bot_w   = w * 0.44
        cx          = w / 2

        pot = QPainterPath()
        pot.moveTo(cx - pot_top_w / 2, pot_top_y)
        pot.lineTo(cx + pot_top_w / 2, pot_top_y)
        pot.lineTo(cx + pot_bot_w / 2, pot_bot_y)
        pot.lineTo(cx - pot_bot_w / 2, pot_bot_y)
        pot.closeSubpath()
        p.fillPath(pot, QColor('#8B5E3C'))

        # pot rim
        p.setPen(QPen(QColor('#6B3E1C'), 2))
        p.drawLine(int(cx - pot_top_w / 2 - 3), int(pot_top_y),
                   int(cx + pot_top_w / 2 + 3), int(pot_top_y))

        # --- stem ---
        stem_x  = cx
        stem_y0 = pot_top_y - 2
        stem_y1 = h * 0.28
        p.setPen(QPen(QColor('#2E7D32'), 3))
        p.drawLine(int(stem_x), int(stem_y0), int(stem_x), int(stem_y1))

        # --- leaves (three filled ovals) ---
        p.setPen(Qt.PenStyle.NoPen if _QT == 6 else Qt.NoPen)
        p.setBrush(QBrush(QColor('#4CAF50')))
        # left leaf
        p.save()
        p.translate(stem_x - 14, int(stem_y1 + 18))
        p.rotate(-35)
        p.drawEllipse(-14, -8, 28, 16)
        p.restore()
        # right leaf
        p.save()
        p.translate(stem_x + 14, int(stem_y1 + 10))
        p.rotate(35)
        p.drawEllipse(-14, -8, 28, 16)
        p.restore()
        # center leaf (points upward from the stem tip)
        p.save()
        p.translate(stem_x, int(stem_y1 + 2))
        p.rotate(-22)
        p.drawEllipse(-9, -18, 18, 20)
        p.restore()

        # --- water drops (3 blue teardrops above plant) ---
        if self._watering:
            p.setBrush(QBrush(QColor('#42A5F5')))
            p.setPen(Qt.PenStyle.NoPen if _QT == 6 else Qt.NoPen)
            for i, dx in enumerate([-14, 0, 14]):
                drop_x = cx + dx
                drop_y = h * 0.08 + (i % 2) * 8
                drop = QPainterPath()
                drop.moveTo(drop_x, drop_y)
                drop.cubicTo(drop_x + 6, drop_y + 6,
                             drop_x + 6, drop_y + 14,
                             drop_x, drop_y + 16)
                drop.cubicTo(drop_x - 6, drop_y + 14,
                             drop_x - 6, drop_y + 6,
                             drop_x, drop_y)
                p.fillPath(drop, QColor('#42A5F5'))

        p.end()


# ---------------------------------------------------------------------------
# MoistureDial  — circular arc gauge with large value in the center
# ---------------------------------------------------------------------------
class MoistureDial(QWidget):
    """Arc gauge (0–10 scale) with the numeric value drawn large in the center."""

    _START = 225  # start angle in Qt degrees (225° ≈ 7 o'clock)
    _SPAN  = 270  # total clockwise sweep in degrees

    def __init__(self, label='', parent=None):
        super().__init__(parent)
        self._label = label
        self._value = None
        self._vmin  = 0.0
        self._vmax  = 10.0
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding if _QT == 6 else QSizePolicy.Expanding,
            QSizePolicy.Policy.Expanding if _QT == 6 else QSizePolicy.Expanding,
        )
        self.setMinimumSize(40, 40)

    def sizeHint(self):
        return QSize(84, 84)

    def set_range(self, vmin, vmax):
        self._vmin = float(vmin)
        self._vmax = float(vmax)
        self.update()

    def set_value(self, v):
        if v != self._value:
            self._value = v
            self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(
            QPainter.RenderHint.Antialiasing if _QT == 6 else QPainter.Antialiasing)

        # Keep drawing square and centred inside the (possibly non-square) widget
        s = min(self.width(), self.height())
        p.translate((self.width() - s) / 2, (self.height() - s) / 2)

        pen_w    = max(3, int(s * 0.083))
        hw       = pen_w / 2 + 1
        arc_rect = QRectF(hw, hw, s - 2 * hw, s - 2 * hw)

        # Background track
        bg_pen = QPen(QColor(_GREY_3), pen_w)
        bg_pen.setCapStyle(Qt.PenCapStyle.RoundCap if _QT == 6 else Qt.RoundCap)
        p.setPen(bg_pen)
        p.setBrush(Qt.BrushStyle.NoBrush if _QT == 6 else Qt.NoBrush)
        p.drawArc(arc_rect, self._START * 16, -self._SPAN * 16)

        # Value arc (red → cyan-blue as value rises across min→max range)
        if self._value is not None:
            span = self._vmax - self._vmin
            frac = max(0.0, min(1.0, (self._value - self._vmin) / span)) if span else 0.5
            color = QColor.fromHsv(int(frac ** 2 * 200), 210, 200)
            val_pen = QPen(color, pen_w)
            val_pen.setCapStyle(Qt.PenCapStyle.RoundCap if _QT == 6 else Qt.RoundCap)
            p.setPen(val_pen)
            p.drawArc(arc_rect, self._START * 16, -int(frac * self._SPAN * 16))

        align_c = Qt.AlignmentFlag.AlignCenter if _QT == 6 else Qt.AlignCenter

        # Large center number
        p.setPen(QColor(_GREY_3))
        val_str = f'{self._value:.1f}' if self._value is not None else '—'
        p.setFont(QFont('', max(8, int(s * 0.22)),
                        QFont.Weight.Bold if _QT == 6 else QFont.Bold))
        p.drawText(QRectF(0, -s * 0.10, s, s), align_c, val_str)

        # Small label below the number
        p.setPen(QColor(_GREY_3))
        p.setFont(QFont('', max(6, int(s * 0.10))))
        p.drawText(QRectF(0, s * 0.58, s, s * 0.30), align_c, self._label)

        p.end()


# ---------------------------------------------------------------------------
# PlantCard  (stacked: page 0 = sensor view, page 1 = config form)
# ---------------------------------------------------------------------------
class PlantCard(QFrame):
    """Card widget for one plant.  Gear icon flips to an inline config form."""

    applied = pyqtSignal(int, dict)   # (plant_idx, cfg_dict)
    profile_saved = pyqtSignal()      # emitted after any profile file is written
    status_message = pyqtSignal(str)  # routed to the main window status bar

    def __init__(self, plant_idx, cfg, profile_names=None, parent=None):
        super().__init__(parent)
        self._idx = plant_idx
        self._has_bottom = cfg.get('bottom_channel') is not None
        self._original_profile = cfg.get('profile', '')
        self._original_soil_profile = cfg.get('soil_profile', '')

        self.setFrameShape(QFrame.Shape.StyledPanel if _QT == 6
                           else QFrame.StyledPanel)
        self.setMinimumWidth(220)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding if _QT == 6 else QSizePolicy.Expanding,
            QSizePolicy.Policy.Expanding if _QT == 6 else QSizePolicy.Expanding,
        )

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_view_page(cfg))
        self._stack.addWidget(self._build_config_page(cfg))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._stack)

        self._update_bottom_visibility(self._has_bottom)

    # ------------------------------------------------------------------
    # Page builders
    # ------------------------------------------------------------------

    def _build_view_page(self, cfg):
        page = QWidget()

        _ac = Qt.AlignmentFlag.AlignHCenter if _QT == 6 else Qt.AlignHCenter
        _at = Qt.AlignmentFlag.AlignTop     if _QT == 6 else Qt.AlignTop

        # Plant index (1-based), small and grey
        idx_lbl = QLabel(f'Plant {self._idx + 1}')
        idx_lbl.setAlignment(_ac)
        _idx_font = idx_lbl.font()
        _idx_font.setPointSize(_idx_font.pointSize() + 1)
        idx_lbl.setFont(_idx_font)
        idx_lbl.setStyleSheet(f'color: {_GREY_1}; text-decoration: underline;')

        # Plant name, bold and centred
        self._name_lbl = QLabel(
            cfg.get('name', cfg.get('profile', f'Plant {self._idx + 1}')))
        self._name_lbl.setFont(
            QFont('', 16, QFont.Weight.Bold if _QT == 6 else QFont.Bold))
        self._name_lbl.setStyleSheet(f'color: {_GREY_2};')
        self._name_lbl.setWordWrap(True)
        self._name_lbl.setAlignment(_ac)

        # Top: centred name block
        name_col = QVBoxLayout()
        name_col.setSpacing(2)
        name_col.addWidget(idx_lbl)
        name_col.addWidget(self._name_lbl)

        name_row = QHBoxLayout()
        name_row.addStretch()
        name_row.addLayout(name_col)
        name_row.addStretch()

        # Icon centred
        self._icon = PlantIcon()
        icon_row = QHBoxLayout()
        icon_row.addStretch()
        icon_row.addWidget(self._icon)
        icon_row.addStretch()

        # Dials stacked vertically, centred
        self._top_dial = MoistureDial('Top')
        self._bot_dial = MoistureDial('Bottom')
        _vmin, _vmax = self._moisture_range(cfg)
        self._top_dial.set_range(_vmin, _vmax)
        self._bot_dial.set_range(_vmin, _vmax)

        dials = QVBoxLayout()
        dials.setSpacing(4)
        dials.addWidget(self._top_dial)
        dials.addWidget(self._bot_dial)



        gear = QPushButton()
        gear.setIcon(QIcon(os.path.join(os.path.dirname(__file__), 'resources', 'gear_white.png')))
        gear.setFixedSize(QSize(32, 32))
        gear.setIconSize(QSize(32, 32))
        gear.setStyleSheet('QPushButton { padding: 0; }')
        gear.setToolTip('Configure plant')
        gear.clicked.connect(lambda: self._stack.setCurrentIndex(1))

        gear_row = QHBoxLayout()
        gear_row.addStretch()
        gear_row.addWidget(gear)
        gear_row.addStretch()

        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addStretch()
        layout.addLayout(name_row)
        layout.addLayout(icon_row)
        layout.addLayout(dials, 1)
        layout.addLayout(gear_row)
        layout.addStretch()
        return page

    @staticmethod
    def _tight_form(grp):
        """Return a compact QFormLayout attached to grp."""
        f = QFormLayout(grp)
        f.setContentsMargins(6, 4, 6, 4)
        f.setSpacing(3)
        f.setHorizontalSpacing(6)
        return f

    def _fit_name_edit(self):
        """Resize the name QTextEdit to fit its document (cursor-safe)."""
        doc_h = self._name_edit.document().size().height()
        margins = self._name_edit.contentsMargins()
        h = int(doc_h) + margins.top() + margins.bottom() + 4
        self._name_edit.setFixedHeight(max(h, 28))

    @staticmethod
    def _bold_groupbox(grp):
        """Make the group-box title bold without affecting child widget fonts."""
        grp.setStyleSheet(
            'QGroupBox { font-weight: bold; } QGroupBox * { font-weight: normal; }')

    def _build_config_page(self, cfg):
        # ---- Plant Profile group ----------------------------------------
        plant_grp = QGroupBox('Plant Profile')
        self._bold_groupbox(plant_grp)
        plant_form = self._tight_form(plant_grp)

        self._profile_map = _profile_display_map()

        # Combobox for selecting an existing plant profile to load
        self._plant_combo = QComboBox()
        self._plant_combo.addItem('— custom —')
        for dname in sorted(self._profile_map.keys()):
            self._plant_combo.addItem(dname)
        if self._original_profile:
            _rev = {v: k for k, v in self._profile_map.items()}
            _init = _rev.get(self._original_profile, '')
            if _init:
                _idx = self._plant_combo.findText(_init)
                if _idx >= 0:
                    self._plant_combo.blockSignals(True)
                    self._plant_combo.setCurrentIndex(_idx)
                    self._plant_combo.blockSignals(False)
        _t = 'Load an existing plant profile to populate the fields below'
        self._plant_combo.setToolTip(_t)
        _lbl = QLabel('Profile:'); _lbl.setToolTip(_t)
        plant_form.addRow(_lbl, self._plant_combo)
        self._plant_combo.currentIndexChanged.connect(self._on_plant_combo_changed)

        initial_display = cfg.get('name', '')
        if not initial_display and cfg.get('profile'):
            pdata = _load_json(os.path.join(PROFILES_DIR, cfg['profile'] + '.json'))
            initial_display = pdata.get('name', cfg['profile'])
        self._name_edit = QTextEdit()
        self._name_edit.setPlainText('')
        self._name_edit.setAcceptRichText(False)
        self._name_edit.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff if _QT == 6
            else Qt.ScrollBarAlwaysOff)
        self._name_edit.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff if _QT == 6
            else Qt.ScrollBarAlwaysOff)
        self._name_edit.document().contentsChanged.connect(self._fit_name_edit)
        QTimer.singleShot(0, lambda: (self._stack.setCurrentIndex(1),
                                      self._name_edit.setPlainText(initial_display),
                                      self._stack.setCurrentIndex(0)))

        _t = 'Display name shown on the plant card'
        self._name_edit.setToolTip(_t)
        _lbl = QLabel('Name:'); _lbl.setToolTip(_t)
        plant_form.addRow(_lbl, self._name_edit)

        _vmin, _vmax = self._moisture_range(cfg)

        self._mmin = QDoubleSpinBox()
        self._mmin.setRange(0, 10)
        self._mmin.setSingleStep(0.5)
        self._mmin.setValue(_vmin)
        _t = 'Pump activates when moisture drops below this level (0–10 scale)'
        self._mmin.setToolTip(_t)
        _lbl = QLabel('Min moisture:'); _lbl.setToolTip(_t)
        plant_form.addRow(_lbl, self._mmin)

        self._mmax = QDoubleSpinBox()
        self._mmax.setRange(0, 10)
        self._mmax.setSingleStep(0.5)
        self._mmax.setValue(_vmax)
        _t = 'Pump stops when moisture reaches this level (0–10 scale)'
        self._mmax.setToolTip(_t)
        _lbl = QLabel('Max moisture:'); _lbl.setToolTip(_t)
        plant_form.addRow(_lbl, self._mmax)

        btn_save_plant = QPushButton('Save Plant Profile…')
        btn_save_plant.setToolTip('Save the current name and moisture thresholds as a reusable profile file')
        btn_save_plant.clicked.connect(self._save_profile)
        plant_form.addRow('', btn_save_plant)

        # ---- Soil Profile group -----------------------------------------
        soil_grp = QGroupBox('Soil Profile')
        self._bold_groupbox(soil_grp)
        soil_form = self._tight_form(soil_grp)

        soil_data = {}
        if cfg.get('soil_profile'):
            soil_data = _load_json(
                os.path.join(SOIL_PROFILES_DIR, cfg['soil_profile'] + '.json'))

        self._soil_combo = QComboBox()
        self._soil_combo.addItem('— default —')
        for _sname in _soil_profile_names():
            self._soil_combo.addItem(_sname)
        if cfg.get('soil_profile'):
            _sidx = self._soil_combo.findText(cfg['soil_profile'])
            if _sidx >= 0:
                self._soil_combo.blockSignals(True)
                self._soil_combo.setCurrentIndex(_sidx)
                self._soil_combo.blockSignals(False)
        _t = 'Load an existing soil calibration profile to populate the fields below'
        self._soil_combo.setToolTip(_t)
        _lbl = QLabel('Profile:'); _lbl.setToolTip(_t)
        soil_form.addRow(_lbl, self._soil_combo)
        self._soil_combo.currentIndexChanged.connect(self._on_soil_combo_changed)

        self._dry_sensor = QDoubleSpinBox()
        self._dry_sensor.setRange(0.0, 1.0)
        self._dry_sensor.setSingleStep(0.001)
        self._dry_sensor.setDecimals(3)
        self._dry_sensor.setValue(soil_data.get('dry_sensor', 0.428))
        _t = 'Normalized ADC reading when soil is completely dry (0–1); default 0.428'
        self._dry_sensor.setToolTip(_t)
        _lbl = QLabel('Dry sensor:'); _lbl.setToolTip(_t)
        soil_form.addRow(_lbl, self._dry_sensor)

        self._wet_sensor = QDoubleSpinBox()
        self._wet_sensor.setRange(0.0, 1.0)
        self._wet_sensor.setSingleStep(0.001)
        self._wet_sensor.setDecimals(3)
        self._wet_sensor.setValue(soil_data.get('wet_sensor', 0.283))
        _t = 'Normalized ADC reading when soil is fully saturated (0–1); default 0.283'
        self._wet_sensor.setToolTip(_t)
        _lbl = QLabel('Wet sensor:'); _lbl.setToolTip(_t)
        soil_form.addRow(_lbl, self._wet_sensor)

        self._dry_std = QDoubleSpinBox()
        self._dry_std.setRange(0.0, 10.0)
        self._dry_std.setSingleStep(0.1)
        self._dry_std.setValue(soil_data.get('dry_std', 1.5))
        _t = 'Moisture scale output (0–10) that corresponds to the dry sensor reading; default 1.5'
        self._dry_std.setToolTip(_t)
        _lbl = QLabel('Dry std:'); _lbl.setToolTip(_t)
        soil_form.addRow(_lbl, self._dry_std)

        self._wet_std = QDoubleSpinBox()
        self._wet_std.setRange(0.0, 10.0)
        self._wet_std.setSingleStep(0.1)
        self._wet_std.setValue(soil_data.get('wet_std', 10.0))
        _t = 'Moisture scale output (0–10) that corresponds to the wet sensor reading; default 10'
        self._wet_std.setToolTip(_t)
        _lbl = QLabel('Wet std:'); _lbl.setToolTip(_t)
        soil_form.addRow(_lbl, self._wet_std)

        btn_save_soil = QPushButton('Save Soil Profile…')
        btn_save_soil.setToolTip('Save the current calibration values as a reusable soil profile file')
        btn_save_soil.clicked.connect(self._save_soil_profile)
        soil_form.addRow('', btn_save_soil)

        # ---- Watering group ---------------------------------------------
        water_grp = QGroupBox('Watering')
        self._bold_groupbox(water_grp)
        water_form = self._tight_form(water_grp)

        self._fill_time = QDoubleSpinBox()
        self._fill_time.setRange(0.1, 300)
        self._fill_time.setSingleStep(1)
        self._fill_time.setSuffix(' s')
        self._fill_time.setValue(cfg.get('fill_time', 5))
        _t = 'Duration of each pump burst during a fill cycle; pump pauses for 2× this between bursts'
        self._fill_time.setToolTip(_t)
        _lbl = QLabel('Fill time:'); _lbl.setToolTip(_t)
        water_form.addRow(_lbl, self._fill_time)

        self._fill_pad = QDoubleSpinBox()
        self._fill_pad.setRange(0.0, 100.0)
        self._fill_pad.setSingleStep(5.0)
        self._fill_pad.setSuffix('%')
        self._fill_pad.setValue(cfg.get('fill_pad', 0.9) * 100)
        _t = 'Stop the fill cycle when bottom moisture reaches this fraction of the max threshold'
        self._fill_pad.setToolTip(_t)
        _lbl = QLabel('Fill pad:'); _lbl.setToolTip(_t)
        water_form.addRow(_lbl, self._fill_pad)

        self._max_cont = QDoubleSpinBox()
        self._max_cont.setRange(1, 3600)
        self._max_cont.setSingleStep(5)
        self._max_cont.setSuffix(' s')
        self._max_cont.setValue(cfg.get('max_continuous', 30))
        _t = 'Safety limit: pump shuts off and sends an alert if it runs continuously beyond this'
        self._max_cont.setToolTip(_t)
        _lbl = QLabel('Max continuous:'); _lbl.setToolTip(_t)
        water_form.addRow(_lbl, self._max_cont)

        self._max_daily = QDoubleSpinBox()
        self._max_daily.setRange(1, 999999)
        self._max_daily.setSingleStep(30)
        self._max_daily.setSuffix(' s')
        self._max_daily.setValue(cfg.get('max_daily', 300))
        _t = 'Safety limit: total pumping budget per day; alert and shutdown when exceeded'
        self._max_daily.setToolTip(_t)
        _lbl = QLabel('Max daily:'); _lbl.setToolTip(_t)
        water_form.addRow(_lbl, self._max_daily)

        self._dry_alert = QDoubleSpinBox()
        self._dry_alert.setRange(0, 86400)
        self._dry_alert.setSingleStep(300)
        self._dry_alert.setSuffix(' s')
        self._dry_alert.setValue(cfg.get('dry_alert', 7200))
        _t = 'Send an email alert if soil stays below the min moisture threshold for this long (0 = disabled)'
        self._dry_alert.setToolTip(_t)
        _lbl = QLabel('Dry alert:'); _lbl.setToolTip(_t)
        water_form.addRow(_lbl, self._dry_alert)

        # ---- Apply/Back row ---------------------------------------------
        btn_apply = QPushButton('Apply')
        btn_back = QPushButton('Back')
        btn_apply.clicked.connect(self._apply)
        btn_back.clicked.connect(lambda: self._stack.setCurrentIndex(0))

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        btn_row.addStretch()
        btn_row.addWidget(btn_back)
        btn_row.addWidget(btn_apply)

        # ---- Assemble page ----------------------------------------------
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)
        layout.addWidget(plant_grp)
        layout.addSpacing(4)
        layout.addWidget(soil_grp)
        layout.addSpacing(4)
        layout.addWidget(water_grp)
        layout.addLayout(btn_row)
        layout.addStretch()
        return page

    # ------------------------------------------------------------------
    # Config helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _moisture_range(cfg):
        """Return (vmin, vmax) from cfg, falling back to the profile file."""
        vmin = cfg.get('moisture_min')
        vmax = cfg.get('moisture_max')
        if (vmin is None or vmax is None) and cfg.get('profile'):
            data = _load_json(os.path.join(PROFILES_DIR, cfg['profile'] + '.json'))
            if vmin is None:
                vmin = data.get('moisture_min')
            if vmax is None:
                vmax = data.get('moisture_max')
        return float(vmin if vmin is not None else 0), float(vmax if vmax is not None else 10)

    def _build_cfg(self):
        _soil_text = self._soil_combo.currentText()
        soil = None if _soil_text.startswith('—') else _soil_text
        return {
            'profile':        self._original_profile,
            'name':           self._name_edit.toPlainText().strip(),
            'moisture_min':   self._mmin.value(),
            'moisture_max':   self._mmax.value(),
            'soil_profile':   soil,
            'fill_time':      self._fill_time.value(),
            'fill_pad':       self._fill_pad.value() / 100,
            'max_continuous': self._max_cont.value(),
            'max_daily':      self._max_daily.value(),
            'dry_alert':      self._dry_alert.value(),
        }

    def _load_profile_by_display(self, display_name):
        fname = self._profile_map.get(display_name)
        if not fname:
            return
        self._original_profile = fname
        data = _load_json(os.path.join(PROFILES_DIR, fname + '.json'))
        self._name_edit.setPlainText(data.get('name', display_name))
        if 'moisture_min' in data:
            self._mmin.setValue(float(data['moisture_min']))
        if 'moisture_max' in data:
            self._mmax.setValue(float(data['moisture_max']))

    def _save_profile(self):
        display_name = self._name_edit.toPlainText().strip()
        if not display_name:
            QMessageBox.warning(self, 'Save Profile', 'Enter a plant name first.')
            return
        fname = _name_to_filename(display_name)
        path = os.path.join(PROFILES_DIR, fname + '.json')
        os.makedirs(PROFILES_DIR, exist_ok=True)
        if os.path.exists(path) and fname != self._original_profile:
            if QMessageBox.question(
                    self, 'Overwrite?', f'"{fname}.json" already exists. Overwrite?',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    if _QT == 6 else QMessageBox.Yes | QMessageBox.No
            ) != (QMessageBox.StandardButton.Yes if _QT == 6 else QMessageBox.Yes):
                return
        _save_json_atomic(path, {
            'name':         display_name,
            'moisture_min': self._mmin.value(),
            'moisture_max': self._mmax.value(),
        })
        self._original_profile = fname
        self._profile_map[display_name] = fname
        self._refresh_plant_combo(display_name)
        self.status_message.emit(f'Plant {self._idx + 1}: profile saved as "{fname}.json".')
        self.profile_saved.emit()

    def _load_soil_profile_by_name(self, name):
        data = _load_json(os.path.join(SOIL_PROFILES_DIR, name + '.json'))
        if 'dry_sensor' in data:
            self._dry_sensor.setValue(float(data['dry_sensor']))
        if 'wet_sensor' in data:
            self._wet_sensor.setValue(float(data['wet_sensor']))
        if 'dry_std' in data:
            self._dry_std.setValue(float(data['dry_std']))
        if 'wet_std' in data:
            self._wet_std.setValue(float(data['wet_std']))

    def _save_soil_profile(self):
        _cur = self._soil_combo.currentText()
        _cur_name = '' if _cur.startswith('—') else _cur
        fname = _name_to_filename(_cur_name) if _cur_name else self._original_soil_profile
        if not fname:
            QMessageBox.warning(self, 'Save Soil Profile',
                                'Select or name a soil profile first.')
            return
        path = os.path.join(SOIL_PROFILES_DIR, fname + '.json')
        os.makedirs(SOIL_PROFILES_DIR, exist_ok=True)
        if os.path.exists(path) and fname != self._original_soil_profile:
            if QMessageBox.question(
                    self, 'Overwrite?', f'"{fname}.json" already exists. Overwrite?',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    if _QT == 6 else QMessageBox.Yes | QMessageBox.No
            ) != (QMessageBox.StandardButton.Yes if _QT == 6 else QMessageBox.Yes):
                return
        _save_json_atomic(path, {
            'dry_sensor': self._dry_sensor.value(),
            'wet_sensor': self._wet_sensor.value(),
            'dry_std':    self._dry_std.value(),
            'wet_std':    self._wet_std.value(),
        })
        self._original_soil_profile = fname
        self._refresh_soil_combo(fname)
        self.status_message.emit(f'Plant {self._idx + 1}: soil profile saved as "{fname}.json".')
        self.profile_saved.emit()

    def _on_plant_combo_changed(self, idx):
        if idx <= 0:
            return
        self._load_profile_by_display(self._plant_combo.currentText())

    def _on_soil_combo_changed(self, idx):
        if idx <= 0:
            self._dry_sensor.setValue(0.428)
            self._wet_sensor.setValue(0.283)
            self._dry_std.setValue(1.5)
            self._wet_std.setValue(10.0)
            self._original_soil_profile = ''
            return
        name = self._soil_combo.currentText()
        self._original_soil_profile = name
        self._load_soil_profile_by_name(name)

    def _refresh_plant_combo(self, select_display=None):
        self._plant_combo.blockSignals(True)
        self._plant_combo.clear()
        self._plant_combo.addItem('— custom —')
        for dname in sorted(self._profile_map.keys()):
            self._plant_combo.addItem(dname)
        if select_display:
            idx = self._plant_combo.findText(select_display)
            if idx >= 0:
                self._plant_combo.setCurrentIndex(idx)
        self._plant_combo.blockSignals(False)

    def _refresh_soil_combo(self, select_name=None):
        cur_text = self._soil_combo.currentText()
        self._soil_combo.blockSignals(True)
        self._soil_combo.clear()
        self._soil_combo.addItem('— default —')
        for name in _soil_profile_names():
            self._soil_combo.addItem(name)
        target = select_name or (cur_text if not cur_text.startswith('—') else None)
        if target:
            idx = self._soil_combo.findText(target)
            if idx >= 0:
                self._soil_combo.setCurrentIndex(idx)
        self._soil_combo.blockSignals(False)

    def _apply(self):
        cfg = self._build_cfg()
        self._top_dial.set_range(cfg['moisture_min'], cfg['moisture_max'])
        self._bot_dial.set_range(cfg['moisture_min'], cfg['moisture_max'])
        self.applied.emit(self._idx, cfg)
        self._stack.setCurrentIndex(0)

    # ------------------------------------------------------------------
    # Public update API
    # ------------------------------------------------------------------

    def _update_bottom_visibility(self, show):
        self._bot_dial.setVisible(show)

    def update_sample(self, sample_dict):
        """Refresh card from a /sample response dict for this plant."""
        name    = sample_dict.get('name', f'Plant {self._idx}')
        m_top   = sample_dict.get('moisture_top', 0)
        m_bot   = sample_dict.get('moisture_bottom', 0)
        pumping = sample_dict.get('pump', False)

        self._name_lbl.setText(name)
        self._icon.watering = pumping

        self._top_dial.set_value(m_top)
        if m_bot is not None and m_bot != 0:
            self._bot_dial.set_value(m_bot)
            self._update_bottom_visibility(True)


    def update_config(self, cfg):
        """Refresh after settings change (e.g. bottom channel toggled)."""
        self._has_bottom = cfg.get('bottom_channel') is not None
        self._update_bottom_visibility(self._has_bottom)

    def refresh_profile_combo(self):
        """Reload profile map from disk and refresh the combo, preserving selection."""
        cur = self._plant_combo.currentText()
        self._profile_map = _profile_display_map()
        self._refresh_plant_combo(cur if not cur.startswith('—') else None)

    def set_status(self, msg):
        self.status_message.emit(msg)


# ---------------------------------------------------------------------------
# DashboardTab
# ---------------------------------------------------------------------------
class DashboardTab(QWidget):
    plant_cfg_applied = pyqtSignal(int, dict)
    profile_saved = pyqtSignal()
    status_message = pyqtSignal(str)

    def __init__(self, n_plants, profile_names, plantpi_cfg, parent=None):
        super().__init__(parent)
        self._cards = []

        self._card_layout = QHBoxLayout()
        self._card_layout.setAlignment(
            Qt.AlignmentFlag.AlignLeft if _QT == 6 else Qt.AlignLeft)

        root = QVBoxLayout(self)
        root.addLayout(self._card_layout)

        plants = plantpi_cfg.get('plants', [])
        for i in range(n_plants):
            cfg = plants[i] if i < len(plants) else {}
            self._add_card(i, cfg, profile_names)

    def _add_card(self, idx, cfg, profile_names):
        card = PlantCard(idx, cfg, profile_names)
        card.applied.connect(lambda i, c: self.plant_cfg_applied.emit(i, c))
        card.profile_saved.connect(self._on_profile_saved)
        card.status_message.connect(self.status_message.emit)
        self._cards.append(card)
        self._card_layout.addWidget(card, 1)

    def set_plant_count(self, n, profile_names, plantpi_cfg):
        plants = plantpi_cfg.get('plants', [])
        cur = len(self._cards)
        if n > cur:
            for i in range(cur, n):
                cfg = plants[i] if i < len(plants) else {}
                self._add_card(i, cfg, profile_names)
        elif n < cur:
            for _ in range(cur - n):
                card = self._cards.pop()
                card.setParent(None)
                card.deleteLater()

    def _on_profile_saved(self):
        for card in self._cards:
            card.refresh_profile_combo()
        self.profile_saved.emit()

    def update_sample(self, samples):
        for item in samples:
            if not isinstance(item, dict):
                continue
            idx = item.get('plant')
            if idx is not None and 0 <= idx < len(self._cards):
                self._cards[idx].update_sample(item)
