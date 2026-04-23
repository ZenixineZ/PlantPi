#!/usr/bin/env python3
"""PlantPi Desktop UI — Dashboard / Graph / Profiles / Settings"""

import os
import signal
import sys

from QtShim import (
    QApplication, QMainWindow, QTabWidget, QTabBar, QLabel, QProxyStyle, QStyle,
    QObject, QSize, pyqtSignal, QTimer, QIcon,
    Style, exec_app,
)


class _TooltipDelayStyle(QProxyStyle):
    """Overrides the tooltip wake-up delay system hint."""
    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == Style.SH_ToolTip_WakeUpDelay:
            return 1000
        return super().styleHint(hint, option, widget, returnData)

from _utils import (
    _HERE, DEFAULT_CFG_PATH, LATEST_CFG_PATH, PROFILES_DIR,
    _load_json, _save_json_atomic, _profile_names,
)
from .graph_tab import GraphTab
from .dashboard_tab import DashboardTab, PlantIcon
from .profiles_tab import ProfilesTab
from .settings_tab import SettingsTab


# ---------------------------------------------------------------------------
# _Bridge — thread-safe signal relay between PlantPi and the UI
# ---------------------------------------------------------------------------
class _Bridge(QObject):
    updated = pyqtSignal(object)  # emits the samples list; safe across threads

    def __init__(self):
        super().__init__()

    def push(self, samples):
        """Safe to call from any thread — Qt queues the signal across threads."""
        self.updated.emit(samples)

    def shutdown(self):
        pass


# ---------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self, cfg_path, csv_path=None, plantpi=None):
        super().__init__()
        self._cfg = _load_json(cfg_path, {})
        self._plantpi = plantpi

        # csv_path arg wins; else config 'file'; else default
        _csv = csv_path or self._cfg.get('file', os.path.join(_HERE, 'data.csv'))
        self._cfg['file'] = _csv

        n = max(1, len(self._cfg.get('plants', [])))
        # When running with a live PlantPi, cap plant count to the number of
        # controllers actually started (can't add more without restarting).
        max_plants = len(plantpi.plant_controllers) if plantpi is not None else 8
        n = min(n, max_plants)

        settings = {
            'plant_count':  n,
            'csv_path':     _csv,
            'plants':       self._cfg.get('plants', []),
            'cfg_path':     cfg_path,
            'test':         self._cfg.get('test', False),
            'verbose':      self._cfg.get('verbose', False),
            'quiet':        self._cfg.get('quiet', False),
            'simu_quit':    self._cfg.get('simu_quit', True),
            'long_sample':  self._cfg.get('long_sample', 30),
            'cistern_gpio': self._cfg.get('cistern_gpio', 0),
            'simulator':    self._cfg.get('simulator', ''),
        }

        profile_names = _profile_names(PROFILES_DIR)

        self.setWindowTitle('PlantPi')
        self.resize(900, 750)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.setAccessibleName('main_tabs')
        self._tabs.tabBar().setAccessibleName('main_tab_bar')
        self._dash = DashboardTab(n, profile_names, self._cfg, plantpi)
        self._graph = GraphTab(n, self._cfg, _csv)
        self._profiles = ProfilesTab()
        self._settings = SettingsTab(settings, max_plants=max_plants)

        self._tabs.addTab(self._dash, 'Dashboard')
        self._tabs.addTab(self._graph, 'Graph')
        self._tabs.addTab(self._profiles, 'Profiles')
        self._tabs.addTab(self._settings, 'Settings')

        self.setCentralWidget(self._tabs)

        # Wire signals
        self._dash.plant_cfg_applied.connect(self._on_plant_cfg_applied)
        self._dash.profile_saved.connect(self._profiles.reload)
        self._dash.status_message.connect(self._on_status_message)
        self._profiles.profiles_changed.connect(self._on_profiles_changed)
        self._settings.settings_saved.connect(self._on_settings_saved)
        self._settings.save_config_requested.connect(self._on_save_config_requested)

        # Pause/resume graph timer based on tab visibility
        self._tabs.currentChanged.connect(self._on_tab_changed)

        # Live sensor bridge — PlantPi pushes samples directly into this
        self._bridge = None
        if plantpi is not None:
            self._bridge = _Bridge()
            self._bridge.updated.connect(self._on_sample)
        else:
            pass

    # ------------------------------------------------------------------
    def _on_tab_changed(self, idx):
        if self._tabs.widget(idx) is self._graph:
            self._graph.resume()
        else:
            self._graph.pause()

    def _on_sample(self, samples):
        self._dash.update_sample(samples)

    def _on_plant_cfg_applied(self, idx, new_plant_cfg):
        """Update in-memory config and live state only (no disk write)."""
        plants = self._cfg.setdefault('plants', [])
        while len(plants) <= idx:
            plants.append({})
        plants[idx].update(new_plant_cfg)

        # Update live PlantPi state directly if available
        if (self._plantpi is not None and
                idx < len(self._plantpi.plant_controllers)):
            pc = self._plantpi.plant_controllers[idx]
            pc.plant_profile = type(pc.plant_profile)(
                new_plant_cfg.get('plant_name'),
                new_plant_cfg.get('icon', pc.plant_profile.icon),
                new_plant_cfg.get('moisture_min', pc.plant_profile.moisture_min),
                new_plant_cfg.get('moisture_max', pc.plant_profile.moisture_max),
            )
            pc.soil_profile = type(pc.soil_profile)(
                new_plant_cfg.get('soil_name'),
                new_plant_cfg.get('dry_sensor', pc.soil_profile.dry_sensor),
                new_plant_cfg.get('wet_sensor', pc.soil_profile.wet_sensor),
                new_plant_cfg.get('dry_std', pc.soil_profile.dry_std),
                new_plant_cfg.get('wet_std', pc.soil_profile.wet_std),
            )

        self._on_status_message(f'Plant {idx + 1} settings applied')

        _save_json_atomic(LATEST_CFG_PATH, self._cfg)

        self._on_status_message(f'Saved to {os.path.basename(LATEST_CFG_PATH)}')


    def _on_status_message(self, _msg):
        pass

    def _on_profiles_changed(self, _names):
        for card in self._dash._cards:
            card.refresh_profile_combo()
            card.refresh_soil_profile_combo()

    def _on_save_config_requested(self, path):
        s = self._settings.current_settings()
        self._cfg.update({
            'plant_count':  s['plant_count'],
            'file':         s['csv_path'],
            'test':         s['test'],
            'verbose':      s['verbose'],
            'quiet':        s['quiet'],
            'simu_quit':    s['simu_quit'],
            'long_sample':  s['long_sample'],
            'cistern_gpio': s['cistern_gpio'],
            'simulator':    s['simulator'],
        })
        plants = self._cfg.setdefault('plants', [])
        # Merge channel assignments from settings tab
        for i, sensor in enumerate(s.get('sensors', [])):
            while len(plants) <= i:
                plants.append({})
            plants[i].update(sensor)
        # Merge current card widget state (profile, soil, watering fields)
        for i, card_cfg in enumerate(self._dash.card_configs()):
            while len(plants) <= i:
                plants.append({})
            plants[i].update(card_cfg)
        _save_json_atomic(path, self._cfg)
        self._on_status_message(f'Config saved to {os.path.basename(path)}')

    def _on_settings_saved(self, s):
        self._cfg.update({
            'plant_count':  s['plant_count'],
            'file':         s['csv_path'],
            'test':         s['test'],
            'verbose':      s['verbose'],
            'quiet':        s['quiet'],
            'simu_quit':    s['simu_quit'],
            'long_sample':  s['long_sample'],
            'cistern_gpio': s['cistern_gpio'],
            'simulator':    s['simulator'],
        })
        # Merge sensor channel assignments into per-plant configs
        plants = self._cfg.setdefault('plants', [])
        for i, sensor in enumerate(s.get('sensors', [])):
            while len(plants) <= i:
                plants.append({})
            plants[i].update(sensor)

        _save_json_atomic(LATEST_CFG_PATH, self._cfg)

        profile_names = _profile_names(PROFILES_DIR)
        self._dash.set_plant_count(s['plant_count'], profile_names, self._cfg)
        self._graph.set_plant_count(s['plant_count'], self._cfg)
        self._graph.set_csv(s['csv_path'])

        self._on_status_message(f'Saved to {os.path.basename(LATEST_CFG_PATH)}')

    @property
    def bridge(self):
        return self._bridge

    def closeEvent(self, event):
        if self._bridge is not None:
            self._bridge.shutdown()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------
def launch(cfg_path=None, csv_path=None, plantpi=None):
    """Launch the Qt UI programmatically (e.g. from PlantPi.py --ui).

    plantpi:  live PlantPi instance for direct sensor reads and state updates.
    csv_path: overrides the config's 'file' path for the graph.
    """
    if cfg_path is None:
        cfg_path = DEFAULT_CFG_PATH
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName('PlantPi')
    app.setStyle(_TooltipDelayStyle())

    # On macOS the menu-bar / dock name comes from CFBundleName, not Qt's app name.
    if sys.platform == 'darwin':
        try:
            from Foundation import NSBundle
            info = NSBundle.mainBundle().infoDictionary()
            info['CFBundleName'] = 'PlantPi'
            info['CFBundleDisplayName'] = 'PlantPi'
        except Exception:
            pass

    # Let Ctrl+C quit cleanly instead of SIGABRT-crashing inside Qt's C++ loop.
    signal.signal(signal.SIGINT, lambda *_: app.quit())

    # Build the app icon by rendering the PlantIcon widget off-screen.
    _icon_widget = PlantIcon()
    _icon_widget.resize(_icon_widget._W, _icon_widget._H)
    app.setWindowIcon(QIcon(_icon_widget.grab()))

    win = MainWindow(cfg_path, csv_path=csv_path, plantpi=plantpi)
    if plantpi is not None and win.bridge is not None:
        plantpi._ui_bridge = win.bridge
    win.show()
    return exec_app(app)
