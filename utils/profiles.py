#!/usr/bin/env python3
"""PlantProfile and SoilProfile data classes for PlantPi."""


class SoilProfile:
    def __init__(self, dry_sensor=0.428, wet_sensor=0.283, dry_std=1.5, wet_std=10):
        self.dry_sensor = dry_sensor
        self.wet_sensor = wet_sensor
        self.dry_std = dry_std
        self.wet_std = wet_std
        # y = mx + b, y is std moisture, x is sensor moisture
        self._m = (wet_std - dry_std) / (wet_sensor - dry_sensor)
        self._b = dry_std - self._m * dry_sensor

    def map_moisture(self, moisture):
        return max(0, min(10, self._m * moisture + self._b))


class PlantProfile:
    def __init__(self, name, moisture_min, moisture_max):
        assert moisture_min >= 0 and moisture_max >= 0 and moisture_min <= moisture_max
        self.name = name
        self.moisture_min = moisture_min
        self.moisture_max = moisture_max
