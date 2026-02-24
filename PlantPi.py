#!/usr/bin/python3
import time
from datetime import datetime
from time import sleep
import argparse
import os
import threading
from flask import jsonify, request
import json
from sshkeyboard import listen_keyboard, stop_listening
import sys
plantpi_path = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, plantpi_path)
from Emailer import Emailer
from RestServer import RestServer

DEFAULT_FILL_TIME = 5
DEFAULT_FILL_PAD = 0.9
DEFAULT_MAX_CONTINUOUS = 30
DEFAULT_MAX_DAILY = 300
DEFAULT_SOIL_PROFILE = 'default'

parser = argparse.ArgumentParser(description="Run the Plant Pi")

parser.add_argument("-t", "--test", action='store_true',
                    help='Test mode: sample every 0.5s instead of 30 min')
parser.add_argument("-w", "--water", nargs='*', type=int, default=None, metavar='PLANT_IDX',
                    help='Continuously water plants by index. No indices = all plants. E.g. -w 0 2')
parser.add_argument("-v", "--verbose", action='store_true',
                    help='Print sensor data on the console each cycle')
parser.add_argument("-f", "--file", default=os.path.join(plantpi_path, 'data.csv'),
                    help='Path to CSV file to write data to')
parser.add_argument("-q", "--quiet", action='store_true',
                    help='Disable email notifications')
parser.add_argument("--plant", action='append', metavar='PROFILE,TOP,BOTTOM,GPIO',
                    help='Plant to manage: profile name, top ADC channel (or empty), '
                         'bottom ADC channel (or empty), relay GPIO. At least one sensor required. '
                         'Repeat for multiple plants. E.g. --plant dracaena,0,4,14 --plant palm,1,,15')
parser.add_argument("--fill-times", nargs='+', type=float, default=[DEFAULT_FILL_TIME], metavar='S',
                    help='Fill burst duration in seconds per plant (repeats last value if fewer than plants)')
parser.add_argument("--fill-pads", nargs='+', type=float, default=[DEFAULT_FILL_PAD], metavar='F',
                    help='Fill pad coefficient per plant')
parser.add_argument("--max-continuous", nargs='+', type=float, default=[DEFAULT_MAX_CONTINUOUS], metavar='S',
                    help='Max continuous pump-on seconds per plant before alert and shutdown')
parser.add_argument("--max-daily", nargs='+', type=float, default=[DEFAULT_MAX_DAILY], metavar='S',
                    help='Max total pump-on seconds per day per plant before alert and shutdown')
parser.add_argument("--soil-profiles", nargs='+', default=[DEFAULT_SOIL_PROFILE], metavar='NAME',
                    help='Soil profile name per plant, loaded from profiles/soil/<name>.json')
parser.add_argument("--simulator", nargs='?', const="zeros", default=None,
                    help='Simulate sensor data from a CSV file (SEQ,CH0..CH7 format), '
                         'or all zeros if no file given')

args = parser.parse_args()

if not args.simulator:
    import Adafruit_ADS1x15 as ADS
    from gpiozero import DigitalOutputDevice

logpath = os.path.join(plantpi_path, 'logs')
if not os.path.isdir(logpath):
    os.mkdir(logpath)
logname = 'plantpi-' + datetime.fromtimestamp(time.time()).strftime('%Y%m%d-%H%M%S') + '.log'
logfile = os.path.join(logpath, logname)
with open(logfile, 'w'):
    temp = os.path.join(logpath, 'latest.log-temp')
    os.symlink(logname, temp)
    os.rename(temp, os.path.join(logpath, 'latest.log'))

profile_path = os.path.join(plantpi_path, 'profiles')
if not os.path.isdir(profile_path):
    os.mkdir(profile_path)


def get_time(t=None, frac=True):
    fmt_str = '%m/%d/%Y %H:%M:%S'
    if frac:
        fmt_str += '.%f'
    if t:
        return datetime.fromtimestamp(t).strftime(fmt_str)
    else:
        return datetime.fromtimestamp(time.time()).strftime(fmt_str)


def log(s):
    print(s)
    with open(logfile, 'a+') as lf:
        lf.write(f'[{get_time()}] {s}\n')


#   Moisture Mapping, tested with resistive gardening probe and capacitive sensors attached to rpi
#   1.5:      0.428 -> dry (0.515 is sensor in open air, but zero ends up falling at about 0.444)
#   >=10:   0.283 -> wet
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
        assert moisture_min >= 0 and moisture_max >= 0
        self.name = name
        self.moisture_min = moisture_min
        self.moisture_max = moisture_max


class FakePump:
    def __init__(self):
        self.value = 0

    def on(self):
        self.value = 1

    def off(self):
        self.value = 0


class FakeADC:
    def __init__(self):
        self.values = {}  # local channel (0-3) -> normalized float (0-1)

    def read_adc(self, ch):
        return int(self.values.get(ch, 0.0) * 32767)



def expand_to_n(lst, n, default):
    """Extend list to length n by padding with default."""
    return (lst + [default] * n)[:n]


class PlantController:
    def __init__(self, plant_profile, soil_profile, adcs, pump, top_channel, bottom_channel=None,
                 fill_time=DEFAULT_FILL_TIME, fill_pad=DEFAULT_FILL_PAD,
                 max_continuous=DEFAULT_MAX_CONTINUOUS, max_daily=DEFAULT_MAX_DAILY):
        self.plant_profile = plant_profile
        self.soil_profile = soil_profile
        self.adcs = adcs
        self.pump = pump
        self.top_channel = top_channel      # int or None
        self.bottom_channel = bottom_channel  # int or None
        self.fill_time = fill_time
        self.fill_pad = fill_pad
        self.max_continuous = max_continuous
        self.max_daily = max_daily
        # sensor readings (raw ADC-normalized and mapped to 0-10 scale)
        self.moisture_top_raw = 0.0
        self.moisture_top = 0.0
        self.moisture_bottom_raw = 0.0
        self.moisture_bottom = 0.0
        # watering state
        self.need_fill = False
        self.need_top_off = False
        self.start_fill = None
        self.pause_fill = None
        self.water_start_time = None
        self.last_accum_time = None
        self.total_water_time = 0.0
        self.last_pump_val = 0
        self.rest_water = False

    def water(self, t, clear_fill=False):
        if clear_fill:
            self.need_fill = False
            self.need_top_off = False
            self.pause_fill = None
            self.start_fill = None
        if self.pump.value == 0:
            self.water_start_time = t
            self.pump.on()
            log(f'[{self.plant_profile.name}] Pump On\n')

    def stop_watering(self):
        if self.pump.value == 1:
            self.water_start_time = None
            self.last_accum_time = None
            self.pump.off()
            log(f'[{self.plant_profile.name}] Pump Off\n')

    def get_data(self):
        if self.top_channel is not None:
            self.moisture_top_raw = self.adcs[self.top_channel // 4].read_adc(self.top_channel % 4) / 32767
            self.moisture_top = self.soil_profile.map_moisture(self.moisture_top_raw)
        else:
            self.moisture_top_raw = 0
            self.moisture_top = 0
        if self.bottom_channel is not None:
            self.moisture_bottom_raw = self.adcs[self.bottom_channel // 4].read_adc(self.bottom_channel % 4) / 32767
            self.moisture_bottom = self.soil_profile.map_moisture(self.moisture_bottom_raw)
        else:
            self.moisture_bottom_raw = 0
            self.moisture_bottom = 0

    def water_if_thirsty(self, t, alerter):
        if self.water_start_time:
            prev = self.last_accum_time if self.last_accum_time is not None else self.water_start_time
            self.total_water_time += t - prev
            self.last_accum_time = t
        # Safety checks
        if self.water_start_time:
            on_time = t - self.water_start_time
            if on_time > self.max_continuous:
                subject = f'[{self.plant_profile.name}] Pump Overuse Alert'
                msg = (f'Error: [{self.plant_profile.name}] Pump has been on for over '
                       f'{self.max_continuous} seconds. Shutting down, please inspect sensor data')
                log(msg)
                alerter(subject, msg)
                self.stop_watering()
                raise RuntimeError(msg)
        if self.total_water_time > self.max_daily:
            subject = f'[{self.plant_profile.name}] Daily Pump Limit Exceeded Alert'
            msg = (f'Error: [{self.plant_profile.name}] Pump has been on for over '
                   f'{self.max_daily} seconds today. Shutting down, please inspect sensor data')
            log(msg)
            alerter(subject, msg)
            self.stop_watering()
            raise RuntimeError(msg)

        # Primary sensor drives fill logic (bottom preferred); secondary (top) drives top-off
        has_secondary = self.top_channel is not None and self.bottom_channel is not None
        primary = self.moisture_bottom if self.bottom_channel is not None else self.moisture_top
        secondary = self.moisture_top if has_secondary else None

        thresh = self.plant_profile.moisture_min
        if self.need_fill or (has_secondary and self.need_top_off):
            thresh = self.plant_profile.moisture_max

        # If primary (and secondary if present) are above threshold, stop watering
        if primary > thresh and (secondary is None or secondary > thresh):
            self.need_fill = False
            self.need_top_off = False
            self.pause_fill = None
            self.start_fill = None
            return self.stop_watering()

        # Fill cycle: primary sensor below threshold
        if (not self.need_fill and (secondary is None or not self.need_top_off) and primary < thresh) or \
           (self.need_fill and primary < self.fill_pad * thresh):
            self.need_fill = True
            self.need_top_off = False
            if (not self.pause_fill) and self.start_fill and t - self.start_fill > self.fill_time:
                self.pause_fill = t
            if self.pause_fill and t - self.pause_fill < 2 * self.fill_time:
                self.start_fill = None
                return self.stop_watering()
            if not self.start_fill:
                self.start_fill = t
            self.pause_fill = None
            return self.water(t)

        self.need_fill = False
        self.pause_fill = None
        self.start_fill = None

        # Top-off: only when both sensors available and only secondary (top) is below threshold
        if has_secondary and secondary < thresh and primary < self.plant_profile.moisture_max:
            self.need_top_off = True
            return self.water(t)
        self.need_top_off = False
        return self.stop_watering()


class PlantPi:
    def __init__(self, plant_args):
        if not plant_args:
            log('Error: At least one --plant argument is required. E.g. --plant dracaena,0,4,14')
            sys.exit(1)

        # Load plant profiles from disk
        self.profiles = []
        for f in os.listdir(profile_path):
            if f.endswith('.json'):
                with open(os.path.join(profile_path, f), 'r') as p:
                    j = json.load(p)
                    try:
                        pp = PlantProfile(j['name'], j['moisture_min'], j['moisture_max'])
                        pp.filename = f[:-5]
                        self.profiles.append(pp)
                    except Exception as e:
                        log(f"Warning: Failed to parse {os.path.join(profile_path, f)} into PlantProfile: {e}")

        # Load soil profiles
        soil_profile_dir = os.path.join(profile_path, 'soil')
        soil_profile_names = expand_to_n(args.soil_profiles, len(plant_args), DEFAULT_SOIL_PROFILE)
        loaded_soil_profiles = []
        for name in soil_profile_names:
            if name == DEFAULT_SOIL_PROFILE:
                loaded_soil_profiles.append(SoilProfile())
            else:
                path = os.path.join(soil_profile_dir, name + '.json')
                if os.path.exists(path):
                    with open(path) as f:
                        j = json.load(f)
                        loaded_soil_profiles.append(SoilProfile(
                            j.get('dry_sensor', 0.428), j.get('wet_sensor', 0.283),
                            j.get('dry_std', 1.5), j.get('wet_std', 10)))
                else:
                    log(f"Warning: soil profile '{name}' not found at {path}, using defaults")
                    loaded_soil_profiles.append(SoilProfile())

        # Expand per-plant vector args
        n = len(plant_args)
        fill_times = expand_to_n(args.fill_times, n, DEFAULT_FILL_TIME)
        fill_pads = expand_to_n(args.fill_pads, n, DEFAULT_FILL_PAD)
        max_continuous = expand_to_n(args.max_continuous, n, DEFAULT_MAX_CONTINUOUS)
        max_daily = expand_to_n(args.max_daily, n, DEFAULT_MAX_DAILY)

        # Initialize ADCs (hardware or fake for simulator)
        if args.simulator:
            self.adcs = [FakeADC(), FakeADC()]
        else:
            self.adcs = [ADS.ADS1115(address=0x48), ADS.ADS1115(address=0x49)]

        # Parse --plant args and build PlantControllers
        self.plant_controllers = []
        for i, plant_arg in enumerate(plant_args):
            parts = plant_arg.split(',')
            if len(parts) != 4:
                log(f"Error: --plant '{plant_arg}': expected format PROFILE,TOP,BOTTOM,GPIO")
                sys.exit(1)
            profile_name, top_str, bottom_str, gpio_str = parts
            top_ch = int(top_str) if top_str else None
            bottom_ch = int(bottom_str) if bottom_str else None
            if top_ch is None and bottom_ch is None:
                log(f"Error: --plant '{plant_arg}': at least one sensor channel required")
                sys.exit(1)
            try:
                gpio = int(gpio_str)
                assert gpio < 26
            except (ValueError, AssertionError):
                log(f"Error: --plant '{plant_arg}': invalid GPIO '{gpio_str}' (must be integer < 26)")
                sys.exit(1)

            # Look up plant profile by name, lowercase name, or filename
            plant_profile = None
            for pp in self.profiles:
                if pp.name == profile_name or pp.name.lower() == profile_name or pp.filename == profile_name:
                    plant_profile = pp
                    break
            if plant_profile is None:
                log(f"Error: --plant '{plant_arg}': profile '{profile_name}' not found in {profile_path}")
                sys.exit(1)

            pump = DigitalOutputDevice(gpio, active_high=False) if not args.simulator else FakePump()

            self.plant_controllers.append(PlantController(
                plant_profile, loaded_soil_profiles[i], self.adcs, pump, top_ch, bottom_ch,
                fill_time=fill_times[i], fill_pad=fill_pads[i],
                max_continuous=max_continuous[i], max_daily=max_daily[i]
            ))
            log(f"Plant {i}: '{plant_profile.name}', top_ch={top_ch}, bottom_ch={bottom_ch}, gpio={gpio}")

        # Email setup
        self.emailer = Emailer()
        self.email_user = None
        self.email_pwd = None
        self.email_to = None
        self.email_from = None
        with open(os.path.join(plantpi_path, 'email_auth.json'), 'r') as f:
            auth = json.load(f)
            if 'user' in auth:
                self.email_user = auth['user']
            if 'password' in auth:
                self.email_pwd = auth['password']
            if 'to' in auth:
                self.email_to = auth['to']
            if 'from' in auth:
                self.email_from = auth['from']

        fields = [('user', self.email_user), ('password', self.email_pwd),
                  ('to', self.email_to), ('from', self.email_from)]
        missing = [name for name, val in fields if val is None]
        invalid = [name for name, val in fields
                   if name != 'password' and val is not None
                   and not ('@' in val and '.' in val.split('@')[-1])]

        if missing or invalid or args.quiet:
            if not args.quiet:
                if missing:
                    log(f'Warning: email_auth.json is missing fields {missing}, notifications will be disabled\n')
                if invalid:
                    log(f'Warning: email_auth.json has invalid email addresses for fields {invalid}, notifications will be disabled\n')
            self.email_user = None
            self.email_pwd = None
            self.email_to = None
            self.email_from = None

        # Simulator setup
        self.simu_seq = 0
        self.simu = {}        # seq -> {global_channel_idx: float}
        if args.simulator and args.simulator != "zeros":
            with open(args.simulator, 'r') as f:
                f.readline()  # skip header (SEQ,CH0,CH1,...,CH7)
                for l in f:
                    l = l.strip()
                    if not l:
                        continue
                    ls = l.split(',')
                    seq = int(ls[0])
                    self.simu[seq] = {i: float(ls[i + 1]) for i in range(min(8, len(ls) - 1))}

        self.done = False
        self.sample = False
        self.kb_water = False          # True while keyboard 'w' is held
        self.kb_water_indices = set()  # number keys held with 'w'; empty = all plants
        self.cond = threading.Condition()
        self.qt = None

    def _cli_waters(self, plant_idx):
        """True if the --water flag targets this plant index."""
        if args.water is None:
            return False
        return not args.water or plant_idx in args.water  # empty list = all plants

    def _kb_waters(self, plant_idx):
        """True if keyboard 'w' is held and targets this plant index."""
        if not self.kb_water:
            return False
        return not self.kb_water_indices or plant_idx in self.kb_water_indices  # empty set = all

    def advance_simulator(self):
        if self.simu_seq in self.simu:
            for ch, val in self.simu[self.simu_seq].items():
                self.adcs[ch // 4].values[ch % 4] = val
        self.simu_seq += 1

    def get_data_rest(self):
        d = request.data
        j = json.loads(d) if d else {}
        if 'start_time' in j or 'end_time' in j:
            s = j.get('start_time', 0)
            e = j.get('end_time', 1e10)
            with open(args.file, 'r') as f:
                lines = [l for l in f.readlines()[1:] if s < float(l.split(',')[0]) < e]
                return jsonify(''.join(lines))
        else:
            with open(args.file, 'r') as f:
                lines = f.readlines()[1:]
                s = 0
                i = len(lines)
                while i > 0:
                    size = len(lines[i - 1].encode('utf-8'))
                    if s + size > 100000000:
                        break
                    s += size
                    i -= 1
                del lines[:i]
                return jsonify(''.join(lines))

    def get_sample_rest(self):
        self.time = time.time()
        result = []
        for i, pc in enumerate(self.plant_controllers):
            pc.get_data()
            d = {'plant': i, 'name': pc.plant_profile.name,
                 'time': get_time(self.time, False), 'pump': pc.pump.value == 1,
                 'moisture_top': pc.moisture_top, 'moisture_bottom': pc.moisture_bottom}
            result.append(d)
        self.sample = True
        with self.cond:
            self.cond.notify_all()
        return jsonify(result)

    def water_rest(self):
        d = request.data
        j = json.loads(d) if d else {}
        plant_idx = j.get('plant', None)

        if plant_idx is not None:
            try:
                plant_idx = int(plant_idx)
                assert 0 <= plant_idx < len(self.plant_controllers)
            except (ValueError, AssertionError):
                return jsonify(f"Invalid plant index '{plant_idx}'"), 400

        targets = self.plant_controllers if plant_idx is None else [self.plant_controllers[plant_idx]]
        target_label = 'all plants' if plant_idx is None else f'plant {plant_idx}'

        if "time" in j:
            try:
                duration = int(j['time'])
            except (ValueError, TypeError):
                return jsonify("Failed to water: 'time' must be an integer")
            for pc in targets:
                pc.rest_water = True
            with self.cond:
                self.cond.notify_all()
            sleep(duration)
            for pc in targets:
                pc.rest_water = False
            return jsonify(f'Watered {target_label} for {duration} seconds')
        else:
            currently_watering = all(pc.rest_water for pc in targets)
            if currently_watering:
                for pc in targets:
                    pc.rest_water = False
                return jsonify(f'Stopped watering {target_label}')
            else:
                for pc in targets:
                    pc.rest_water = True
                with self.cond:
                    self.cond.notify_all()
                return jsonify(f'Started watering {target_label}')

    def set_plant_profile_rest(self):
        j = json.loads(request.data)
        plant_idx = j.get('plant', 0)
        try:
            plant_idx = int(plant_idx)
            assert 0 <= plant_idx < len(self.plant_controllers)
        except (ValueError, AssertionError):
            return jsonify(f"Invalid plant index '{plant_idx}'"), 400

        pc = self.plant_controllers[plant_idx]
        msg = None
        if 'moisture_max' in j:
            pc.plant_profile = PlantProfile(str(j['name']), float(j['moisture_min']), float(j['moisture_max']))
            msg = f'Plant {plant_idx} profile set to:\n' + json.dumps(j, indent=4)
        else:
            for p in self.profiles:
                if p.name == str(j['name']):
                    pc.plant_profile = p
                    msg = f'Plant {plant_idx} profile set to {p.name}'
                    break
        if not msg:
            msg = f"Failed to set plant profile: Couldn't find requested profile '{str(j['name'])}'"
        log(msg + '\n')
        return jsonify(msg)

    def __del__(self):
        for pc in getattr(self, 'plant_controllers', []):
            try:
                pc.stop_watering()
            except:
                pass

    def alert(self, subject, message):
        if self.email_user and self.email_pwd and self.email_to and self.email_from:
            try:
                self.emailer.send_email(self.email_user, self.email_pwd, self.email_to,
                                        self.email_from, subject, message)
                log(f'Email sent from {self.email_from} to {self.email_to}\n')
            except Exception as e:
                log(f'Warning: Failed to send notification email: {e}\n')

    def on_press(self, key):
        if key == 's':
            if not args.verbose:
                self.time = time.time()
                for i, pc in enumerate(self.plant_controllers):
                    pc.get_data()
                    lines = [f'Plant {i} ({pc.plant_profile.name}):',
                             f'  Pump: {pc.pump.value == 1}']
                    if pc.top_channel is not None:
                        lines.append(f'  Top: {pc.moisture_top}')
                    if pc.bottom_channel is not None:
                        lines.append(f'  Bottom: {pc.moisture_bottom}')
                    log('\n'.join(lines))
            self.sample = True
            with self.cond:
                self.cond.notify_all()
        elif key == 'q':
            self.done = True
            with self.cond:
                self.cond.notify_all()
            stop_listening()
        elif key == 'w':
            self.kb_water = True
            with self.cond:
                self.cond.notify_all()
        elif key.isdigit() and self.kb_water:
            self.kb_water_indices.add(int(key))

    def on_release(self, key):
        if key == 'w':
            self.kb_water = False
            self.kb_water_indices.clear()
        elif key.isdigit():
            self.kb_water_indices.discard(int(key))

    def query_thread(self):
        try:
            log('Press "s" key to print sample')
            log('Hold "w" key to water all plants (hold number keys with "w" to target specific plants)')
            log('Press "q" key to quit\n')
            listen_keyboard(on_press=self.on_press, on_release=self.on_release, until=None)
        except KeyboardInterrupt:
            stop_listening()
            self.done = True
            with self.cond:
                self.cond.notify_all()

    def run(self):
        if not args.file or not (len(os.path.dirname(args.file)) == 0 or
                                  os.path.exists(os.path.dirname(args.file))):
            args.file = None

        names = ', '.join(f"'{pc.plant_profile.name}'" for pc in self.plant_controllers)
        log(f"Running with {len(self.plant_controllers)} plant(s): {names}\n")

        self.rest_server = RestServer(__name__)
        if args.file:
            self.rest_server.add_endpoint(methods=['GET'], url='/data', endpoint_name='Data',
                                          handler=self.get_data_rest)
        self.rest_server.add_endpoint(methods=['GET'], url='/sample', endpoint_name='Sample',
                                      handler=self.get_sample_rest)
        self.rest_server.add_endpoint(methods=['POST'], url='/water', endpoint_name='Water',
                                      handler=self.water_rest)
        self.rest_server.add_endpoint(methods=['POST'], url='/plant', endpoint_name='Plant',
                                      handler=self.set_plant_profile_rest)
        self.rest_server.start()

        if not args.verbose or not args.test:
            self.qt = threading.Thread(target=self.query_thread)
            self.qt.start()

        # Build CSV header dynamically based on which sensors each plant has
        header_parts = ['TIME']
        for i, pc in enumerate(self.plant_controllers):
            header_parts.append(f'PLANT_{i}_NAME')
            if pc.top_channel is not None:
                header_parts += [f'PLANT_{i}_TOP', f'PLANT_{i}_MAPPED_TOP']
            if pc.bottom_channel is not None:
                header_parts += [f'PLANT_{i}_BOTTOM', f'PLANT_{i}_MAPPED_BOTTOM']
            header_parts.append(f'PLANT_{i}_PUMP')
        header = ','.join(header_parts) + '\n'

        try:
            while not self.done:
                self.time = time.time()
                if args.simulator:
                    self.advance_simulator()

                # Read sensors into each PlantController
                for pc in self.plant_controllers:
                    pc.get_data()

                # Watering logic per plant
                for i, pc in enumerate(self.plant_controllers):
                    if self._cli_waters(i) or self._kb_waters(i) or pc.rest_water:
                        pc.water(self.time, clear_fill=True)
                    else:
                        pc.water_if_thirsty(self.time, self.alert)

                # Pump activation email alerts
                for pc in self.plant_controllers:
                    if pc.pump.value == 1 and pc.last_pump_val == 0 and not pc.pause_fill:
                        parts = [f'Time: {get_time(self.time, False)}',
                                 f'Plant: {pc.plant_profile.name}',
                                 f'Pump: On']
                        if pc.top_channel is not None:
                            parts.append(f'Top: {pc.moisture_top}')
                        if pc.bottom_channel is not None:
                            parts.append(f'Bottom: {pc.moisture_bottom}')
                        self.alert(f'[{pc.plant_profile.name}] Pump Activated',
                                   '\n'.join(parts) + '\n')
                    pc.last_pump_val = pc.pump.value

                if args.verbose:
                    lines = []
                    for i, pc in enumerate(self.plant_controllers):
                        lines.append(f'  Plant {i} ({pc.plant_profile.name}): Pump={pc.pump.value == 1}')
                        if pc.top_channel is not None:
                            lines.append(f'    TOP: {pc.moisture_top_raw} -> {pc.moisture_top}')
                        if pc.bottom_channel is not None:
                            lines.append(f'    BOTTOM: {pc.moisture_bottom_raw} -> {pc.moisture_bottom}')
                    log('\n'.join(lines))

                # CSV logging
                if args.file:
                    with open(args.file, 'a+') as f:
                        t = f.tell()
                        f.seek(0)
                        lines = f.readlines()
                        f.seek(t)
                        if len(lines) == 0:
                            f.write(header)
                        elif lines[0] != header:
                            f.truncate(0)
                            f.write(header)
                        row_parts = [str(self.time)]
                        for pc in self.plant_controllers:
                            row_parts.append(pc.plant_profile.name)
                            if pc.top_channel is not None:
                                row_parts += [str(pc.moisture_top_raw), str(pc.moisture_top)]
                            if pc.bottom_channel is not None:
                                row_parts += [str(pc.moisture_bottom_raw), str(pc.moisture_bottom)]
                            row_parts.append(str(pc.pump.value))
                        f.write(','.join(row_parts) + '\n')

                # Sleep: fast loop when any plant is actively watering or in test mode
                any_active = any(pc.need_top_off or pc.need_fill for pc in self.plant_controllers)
                any_manual = self.kb_water or any(pc.rest_water for pc in self.plant_controllers)
                if any_active or any_manual or args.water is not None or args.test:
                    sleep(0.5)
                else:
                    with self.cond:
                        self.cond.wait_for(
                            lambda: self.done or self.kb_water or self.sample or
                                    any(pc.rest_water for pc in self.plant_controllers),
                            timeout=1800)
                        self.sample = False

        except KeyboardInterrupt:
            pass
        log("Quitting...")
        stop_listening()
        if self.qt:
            self.qt.join()
        self.rest_server.stop()
        for pc in self.plant_controllers:
            pc.stop_watering()


if __name__ == "__main__":
    try:
        log("Starting PlantPi...\n")
        pp = PlantPi(args.plant)
        pp.run()
    except KeyboardInterrupt:
        log("\nQuitting...")
