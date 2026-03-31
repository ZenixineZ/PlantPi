#!/usr/bin/env python3
"""MoistureGraph — pyqtgraph widget for PlantPi moisture history."""

import csv
import io
import os
import time

try:
    from PyQt5.QtWidgets import ( QWidget, QVBoxLayout, QHBoxLayout, 
                                  QDoubleSpinBox, QPushButton, QCheckBox,  
                                  QLabel, QFrame )
    from PyQt5.QtCore import Qt, pyqtSignal, QTimer
    _QT = 5
except ImportError:
    from PyQt6.QtWidgets import ( QWidget, QVBoxLayout, QHBoxLayout, 
                                  QDoubleSpinBox, QPushButton, QCheckBox,  
                                  QLabel, QFrame )
    from PyQt6.QtCore import Qt, pyqtSignal, QTimer
    _QT = 6

import pyqtgraph as pg
pg.setConfigOption('background', '#1a1a1a')
pg.setConfigOption('foreground', '#cccccc')


# Bright, vivid colours chosen for legibility on a dark background
CURVE_COLORS = [
    '#4fc3f7',  # sky blue
    '#ffb74d',  # amber
    '#81c784',  # sage green
    '#f48fb1',  # rose pink
    '#ce93d8',  # lavender
    '#80cbc4',  # teal
    '#fff176',  # yellow
    '#ff8a65',  # deep orange
]

def _vline():
    f = QFrame()
    f.setFrameShape(QFrame.Shape.VLine if _QT == 6 else QFrame.VLine)
    f.setFixedWidth(10)
    return f

_PLOT_MAX_PTS = 800   # cap per curve — more than enough for any screen width

def _decimate(pts):
    """Stride-subsample a list of (x, y) tuples to at most _PLOT_MAX_PTS entries.

    Uses min/max interleaving within each bucket so peaks and troughs are
    preserved even when the stride is large.
    """
    n = len(pts)
    if n <= _PLOT_MAX_PTS:
        return pts
    bucket = max(1, n // (_PLOT_MAX_PTS // 2))
    out = []
    for i in range(0, n, bucket):
        chunk = pts[i:i + bucket]
        lo = min(chunk, key=lambda p: p[1])
        hi = max(chunk, key=lambda p: p[1])
        # Keep chronological order within the bucket
        out += sorted([lo, hi], key=lambda p: p[0])
    return out


# ---------------------------------------------------------------------------
# Custom ViewBox — X-key + left-drag = horizontal swath zoom
# ---------------------------------------------------------------------------
class _XZoomViewBox(pg.ViewBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.x_zoom = False   # toggled by MoistureGraph key events

    def mouseDragEvent(self, ev, axis=None):
        _left = Qt.MouseButton.LeftButton if _QT == 6 else Qt.LeftButton
        if self.x_zoom and ev.button() == _left:
            ev.accept()
            br = self.boundingRect()
            # Swath spans full height, only x follows the drag
            p1 = pg.Point(ev.buttonDownPos().x(), br.top())
            p2 = pg.Point(ev.pos().x(),           br.bottom())
            self.updateScaleBox(p1, p2)
            if ev.isFinish():
                self.rbScaleBox.hide()
                x1 = self.mapToView(ev.buttonDownPos()).x()
                x2 = self.mapToView(ev.pos()).x()
                if abs(x2 - x1) > 1:          # at least 1 second wide
                    self.setXRange(min(x1, x2), max(x1, x2), padding=0)
        else:
            super().mouseDragEvent(ev, axis=axis)


# ---------------------------------------------------------------------------
# MoistureGraph
# ---------------------------------------------------------------------------
class MoistureGraph(QWidget):
    """pyqtgraph canvas that plots CSV moisture data.

    Mouse controls:
      Left drag        — pan
      X + left drag    — horizontal swath zoom
      Wheel            — zoom x-axis in/out
    """

    _MAX_CACHE_AGE = 7 * 24 * 3600  # 7 days — also the hard zoom-out limit

    # Emits the visible width in minutes whenever the x range changes.
    range_changed = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(
            Qt.FocusPolicy.StrongFocus if _QT == 6 else Qt.StrongFocus)

        self._cache_path = None
        self._file_pos   = 0
        self._row_cache  = []
        self._fieldnames = []

        # ---- plot widget ----
        date_axis = pg.DateAxisItem(orientation='bottom')
        self._vb  = _XZoomViewBox()
        self._pw  = pg.PlotWidget(viewBox=self._vb,
                                  axisItems={'bottom': date_axis})
        self._pw.showGrid(x=True, y=True, alpha=0.15)
        self._pw.setLabel('left', 'Moisture (0–10)')
        self._pw.setYRange(0, 11, padding=0)
        # Lock y so wheel/drag only affect the time axis
        self._pw.setMouseEnabled(x=True, y=False)
        self._pw.enableAutoRange(x=False, y=False)
        # Pan mode — left drag pans; X+left drag handled by _XZoomViewBox
        self._vb.setMouseMode(pg.ViewBox.PanMode)
        # No setLimits — we enforce maxXRange ourselves in _on_x_range_changed
        # to avoid pyqtgraph panning the view when the wheel hits the limit.
        self._pw.setMenuEnabled(False)
        self._legend = self._pw.addLegend(offset=(-10, 10), colCount=8)

        # Single handler: clamp future + emit range_changed for the spin box
        self._vb.sigXRangeChanged.connect(self._on_x_range_changed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._pw)

        self._curves = {}    # label  -> PlotDataItem
        self._hlines = {}    # hkey   -> InfiniteLine
        self._x_range = None # last valid (vmin, vmax) — used to freeze at min span

    # ------------------------------------------------------------------
    def keyPressEvent(self, ev):
        _x = Qt.Key.Key_X if _QT == 6 else Qt.Key_X
        if ev.key() == _x and not ev.isAutoRepeat():
            self._vb.x_zoom = True
        super().keyPressEvent(ev)

    def keyReleaseEvent(self, ev):
        _x = Qt.Key.Key_X if _QT == 6 else Qt.Key_X
        if ev.key() == _x:
            self._vb.x_zoom = False
        super().keyReleaseEvent(ev)

    def focusOutEvent(self, ev):
        self._vb.x_zoom = False
        super().focusOutEvent(ev)

    # ------------------------------------------------------------------
    _MIN_SPAN = 60  # 1 minute in seconds

    def _on_x_range_changed(self, vb, x_range):
        """Clamp right edge to now, left edge to MAX_CACHE_AGE ago, and width to
        [MIN_SPAN, MAX_CACHE_AGE]; emit range_changed."""
        vmin, vmax = x_range
        now = time.time()
        width = vmax - vmin
        oldest = now - self._MAX_CACHE_AGE
        if width < self._MIN_SPAN:
            if self._x_range is not None:
                self._pw.setXRange(*self._x_range, padding=0)
            else:
                mid = (vmin + vmax) / 2
                self._pw.setXRange(mid - self._MIN_SPAN / 2, mid + self._MIN_SPAN / 2, padding=0)
            return
        if vmax > now:
            self._pw.setXRange(now - width, now, padding=0)
            return
        if width > self._MAX_CACHE_AGE:
            self._pw.setXRange(vmax - self._MAX_CACHE_AGE, vmax, padding=0)
            return
        if vmin < oldest:
            self._pw.setXRange(oldest, oldest + width, padding=0)
            return
        self._x_range = (vmin, vmax)
        self.range_changed.emit(width / 60)

    # ------------------------------------------------------------------
    def _update_cache(self, csv_path):
        """Append only new rows from the CSV. Returns True if new rows were added."""
        if not csv_path or not os.path.exists(csv_path):
            return False
        try:
            size = os.path.getsize(csv_path)
        except OSError:
            return False

        # Reset if the file path changed or the file shrank (e.g. PlantPi trimmed it)
        if csv_path != self._cache_path or self._file_pos > size:
            self._cache_path = csv_path
            self._file_pos   = 0
            self._row_cache  = []
            self._fieldnames = []

        if self._file_pos >= size:
            return False  # nothing new to read

        try:
            with open(csv_path, 'rb') as fb:
                fb.seek(self._file_pos)
                chunk = fb.read()
                self._file_pos += len(chunk)
            text = chunk.decode('utf-8', errors='replace')
            buf  = io.StringIO(text)
            before = len(self._row_cache)
            if not self._fieldnames:
                reader = csv.DictReader(buf)
                self._fieldnames = list(reader.fieldnames or [])
                for row in reader:
                    if row.get('TIME'):
                        self._row_cache.append(dict(row))
            else:
                reader = csv.DictReader(buf, fieldnames=self._fieldnames)
                for row in reader:
                    t = row.get('TIME', '')
                    if t and t != 'TIME':
                        self._row_cache.append(dict(row))
        except Exception:
            return False

        cutoff = time.time() - self._MAX_CACHE_AGE
        if self._row_cache and float(self._row_cache[0].get('TIME', cutoff)) < cutoff:
            self._row_cache = [r for r in self._row_cache
                               if float(r.get('TIME', 0)) >= cutoff]

        return len(self._row_cache) != before

    # ------------------------------------------------------------------
    def refresh(self, csv_path, n_plants, window_hours, visible_curves,
                plant_cfgs=None, force=False, snap=True):
        """Update curves from the in-memory cache.

        force=True  — redraw even if no new CSV rows arrived.
        snap=True   — on force, hard-reset to [now - window, now].
        snap=False  — on force, extend the left edge back; only push the right
                      edge back if the left edge hits the data limit; stop if
                      both limits are reached.
        """
        if not csv_path or not os.path.exists(csv_path):
            return

        new_data = self._update_cache(csv_path)
        if not new_data and not force:
            return

        now    = time.time()
        cutoff = now - window_hours * 3600  # used only for force-reset of x range

        # Filter rows by the actual visible left edge (not by window_hours from now),
        # so panning into history doesn't discard the data that's on screen.
        vmin, vmax = self._pw.viewRange()[0]
        row_cutoff = min(vmin, cutoff)  # include all data visible or in the target window
        fieldnames = self._fieldnames
        rows = [r for r in self._row_cache
                if r.get('TIME') and float(r['TIME']) >= row_cutoff]

        _dash = Qt.PenStyle.DashLine if _QT == 6 else Qt.DashLine
        _dot  = Qt.PenStyle.DotLine  if _QT == 6 else Qt.DotLine

        color_idx = 0
        for pi in range(n_plants):
            top_col = f'PLANT_{pi}_MAPPED_TOP'
            bot_col = f'PLANT_{pi}_MAPPED_BOTTOM'

            for col, suffix in [(top_col, 'Top'), (bot_col, 'Bottom')]:
                lbl   = f'Plant {pi} {suffix}'
                color = CURVE_COLORS[color_idx % len(CURVE_COLORS)]
                color_idx += 1

                if col not in fieldnames or lbl not in visible_curves:
                    if lbl in self._curves:
                        self._curves[lbl].setVisible(False)
                    continue

                pts = [(float(r['TIME']), float(r[col]))
                       for r in rows if r.get(col)]
                pts = _decimate(pts)

                if lbl not in self._curves:
                    self._curves[lbl] = self._pw.plot(
                        pen=pg.mkPen(color, width=1.5), name=lbl)

                self._curves[lbl].setVisible(True)
                if pts:
                    xs, ys = zip(*pts)
                    self._curves[lbl].setData(list(xs), list(ys))
                else:
                    self._curves[lbl].setData([], [])

            # Threshold lines
            lc = CURVE_COLORS[pi * 2 % len(CURVE_COLORS)]
            for kind, cfg_key, style in [
                ('min', 'moisture_min', _dash),
                ('max', 'moisture_max', _dot),
            ]:
                hkey = f'plant_{pi}_{kind}'
                val  = (plant_cfgs[pi].get(cfg_key)
                        if plant_cfgs and pi < len(plant_cfgs) else None)
                if val is not None:
                    if hkey not in self._hlines:
                        line = pg.InfiniteLine(
                            pos=val, angle=0, movable=False,
                            pen=pg.mkPen(lc, width=1.0, style=style, alpha=140))
                        self._pw.addItem(line)
                        self._hlines[hkey] = line
                    else:
                        self._hlines[hkey].setValue(val)
                    self._hlines[hkey].setVisible(True)
                elif hkey in self._hlines:
                    self._hlines[hkey].setVisible(False)

        # Range update policy:
        epsilon = window_hours * 3600 * 0.02   # 2 % of the displayed window
        vmin_cur, vmax_cur = self._pw.viewRange()[0]
        if force and snap:
            self._pw.setXRange(cutoff, now, padding=0)
        elif force and not snap:
            # Extend left edge first; if it hits the data limit push the right
            # edge back; if that also hits a limit leave the range as-is.
            oldest    = now - self._MAX_CACHE_AGE
            new_width = window_hours * 3600
            new_vmin  = vmax_cur - new_width
            new_vmax  = vmax_cur
            if new_vmin < oldest:
                new_vmin = oldest
                new_vmax = min(now, oldest + new_width)
            self._pw.setXRange(new_vmin, new_vmax, padding=0)
        elif abs(vmax_cur - now) <= epsilon:
            self._pw.setXRange(now - (vmax_cur - vmin_cur), now, padding=0)

# ---------------------------------------------------------------------------
# Time-span spinbox  (minutes internally; displays "N min" or "N.N h")
# ---------------------------------------------------------------------------
class TimeSpinBox(QDoubleSpinBox):
    """Minutes < 60 → integer + 'min'; minutes ≥ 60 → decimal + 'h'."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(1, 525600)   # 1 min … 1 year
        self.setDecimals(1)
        self.setSuffix('')         # suffix is part of textFromValue
        self.setValue(60)          # default 1 h

    def textFromValue(self, val):
        if val < 60:
            return f'{int(round(val))} min'
        if val < 1440:
            return f'{val / 60:.1f} h'
        return f'{val / 1440:.2f} d'

    def valueFromText(self, text):
        t = text.strip()
        if 'd' in t:
            return float(t.replace('d', '').strip()) * 1440
        if 'h' in t:
            return float(t.replace('h', '').strip()) * 60
        return float(t.replace('min', '').strip())

    def validate(self, text, pos):
        t = text.strip().replace('d', '').replace('h', '').replace('min', '').strip()
        try:
            float(t)
            return (2, text, pos)   # Acceptable
        except ValueError:
            return (1, text, pos)   # Intermediate

    def stepBy(self, steps):
        val = self.value()
        if val < 60:
            new_val = val + steps           # 1-min steps
        elif val < 1440:
            new_val = val + steps * 60      # 1-hour steps
            if new_val < 60:
                new_val = 59
        else:
            new_val = val + steps * 1440    # 1-day steps
            if new_val < 1440:
                new_val = 1380              # drop back into hour range (23 h)
        self.setValue(max(1, new_val))

# ---------------------------------------------------------------------------
# Graph tab
# ---------------------------------------------------------------------------
class GraphTab(QWidget):
    def __init__(self, n_plants, plantpi_cfg, csv_path, poll_interval=5, parent=None):
        super().__init__(parent)
        self._n_plants = n_plants
        self._plantpi_cfg = plantpi_cfg
        self._csv_path = csv_path
        self._checkboxes = {}  # label -> QCheckBox

        _max_minutes = MoistureGraph._MAX_CACHE_AGE / 60

        # Controls strip
        self._time_spin = TimeSpinBox()
        self._time_spin.setMaximum(_max_minutes)
        self._time_spin.valueChanged.connect(lambda _: self._refresh(force=True, snap=False))

        self._live_btn = QPushButton('Live')
        self._live_btn.setFixedWidth(48)
        self._live_btn.setToolTip('Snap to 1 hour of most recent data')
        self._live_btn.clicked.connect(self._snap_live)

        self._ctrl_layout = QHBoxLayout()
        self._ctrl_layout.addWidget(QLabel('Time:'))
        self._ctrl_layout.addWidget(self._time_spin)
        self._ctrl_layout.addWidget(self._live_btn)
        self._ctrl_layout.addWidget(_vline())

        self._cb_container = QHBoxLayout()
        self._ctrl_layout.addLayout(self._cb_container)
        self._ctrl_layout.addStretch()

        self._graph = MoistureGraph()
        self._graph.range_changed.connect(self._on_graph_range_changed)

        root = QVBoxLayout(self)
        root.addLayout(self._ctrl_layout)
        root.addWidget(self._graph, 1)

        self._auto_timer = QTimer()
        self._auto_timer.timeout.connect(self._refresh)
        # Timer managed by MainWindow; not started here

        self.set_plant_count(n_plants, plantpi_cfg)

    def _rebuild_checkboxes(self):
        # Remove existing
        while self._cb_container.count():
            item = self._cb_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._checkboxes.clear()

        # Check which columns exist in CSV
        csv_cols = set()
        if self._csv_path and os.path.exists(self._csv_path):
            try:
                with open(self._csv_path, newline='') as f:
                    hdr = csv.DictReader(f).fieldnames or []
                csv_cols = set(hdr)
            except Exception:
                pass

        for i in range(self._n_plants):
            for suffix, col_key in [('Top', f'PLANT_{i}_MAPPED_TOP'),
                                     ('Bottom', f'PLANT_{i}_MAPPED_BOTTOM')]:
                lbl = f'Plant {i} {suffix}'
                if not csv_cols or col_key in csv_cols:
                    cb = QCheckBox(lbl)
                    cb.setChecked(True)
                    cb.stateChanged.connect(lambda _: self._refresh(force=True))
                    self._cb_container.addWidget(cb)
                    self._checkboxes[lbl] = cb

    def set_plant_count(self, n, plantpi_cfg):
        self._n_plants = n
        self._plantpi_cfg = plantpi_cfg
        self._rebuild_checkboxes()
        self._refresh()

    def set_csv(self, path):
        self._csv_path = path
        self._rebuild_checkboxes()
        self._refresh()

    def set_poll_interval(self, seconds):
        self._auto_timer.setInterval(seconds * 1000)

    def pause(self):
        self._auto_timer.stop()

    def resume(self):
        self._refresh(force=True)
        self._auto_timer.start(int(1000/4))  # poll for new CSV rows every 250ms

    def _on_graph_range_changed(self, minutes):
        """Keep the time-span spin in sync with the current zoom level."""
        self._time_spin.blockSignals(True)
        self._time_spin.setValue(minutes)
        self._time_spin.blockSignals(False)

    def _snap_live(self):
        """Snap the right edge to now using the current timespan."""
        self._refresh(force=True, snap=True)

    def _refresh(self, force=False, snap=True):
        hours = self._time_spin.value() / 60   # stored as minutes
        visible = {lbl for lbl, cb in self._checkboxes.items() if cb.isChecked()}
        plants = self._plantpi_cfg.get('plants', [])
        self._graph.refresh(self._csv_path, self._n_plants, hours,
                            visible, plants, force=force, snap=snap)