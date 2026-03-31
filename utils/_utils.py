#!/usr/bin/env python3
"""Shared helpers and path constants for the PlantPi UI."""

import json
import os
import re

_HERE = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

DEFAULT_CFG_PATH  = os.path.join(_HERE, 'resources', 'plantpi.json')
LATEST_CFG_PATH   = os.path.join(_HERE, 'resources', 'latest_cfg.json')
PROFILES_DIR      = os.path.join(_HERE, 'profiles')
SOIL_PROFILES_DIR = os.path.join(_HERE, 'profiles', 'soil')


def _name_to_filename(name):
    """Derive a filesystem-safe filename from a display name.

    Strips parenthetical groups, lowercases, and replaces whitespace with underscores.
    """
    name = re.sub(r'\s*\([^)]*\)\s*', ' ', name)
    name = name.strip().lower()
    name = re.sub(r'\s+', '_', name)
    return name


def _load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def _save_json_atomic(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def _profile_names(directory):
    """Return sorted list of profile filenames (without .json)."""
    if not os.path.isdir(directory):
        return []
    return sorted(f[:-5] for f in os.listdir(directory)
                  if f.endswith('.json') and not f.startswith('.'))


def _profile_display_map():
    """Return {display_name: filename} for all profiles in PROFILES_DIR."""
    result = {}
    if not os.path.isdir(PROFILES_DIR):
        return result
    for f in os.listdir(PROFILES_DIR):
        if f.endswith('.json') and not f.startswith('.'):
            fname = f[:-5]
            data = _load_json(os.path.join(PROFILES_DIR, f))
            result[data.get('name', fname)] = fname
    return result


def _soil_profile_names():
    """Return sorted list of soil profile filenames (without .json)."""
    if not os.path.isdir(SOIL_PROFILES_DIR):
        return []
    return sorted(f[:-5] for f in os.listdir(SOIL_PROFILES_DIR)
                  if f.endswith('.json') and not f.startswith('.'))
