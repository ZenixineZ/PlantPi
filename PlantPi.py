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

parser = argparse.ArgumentParser(description = "Run the Plant Pi")

parser.add_argument("-t", "--test",  action='store_true', help='Puts the PlantPi into test mode where samples are always taken every half second rather than the usual half hour')
parser.add_argument("-w", "--water",  action='store_true', help='Sets the PlantPi to constantly water the plant')
parser.add_argument("-v", "--verbose",  action='store_true', help='Prints the sensor data on the console')
parser.add_argument("-f", "--file", default=os.path.join(plantpi_path, 'data.csv'),help='Path to a csv file to write data to')
parser.add_argument("-q", "--quiet",  action='store_true', help='Stops the PlantPi from sending email notifications')
parser.add_argument("-p", "--plant", default=None, help='Optional name of the plant profile to use')
parser.add_argument("--simulator", nargs='?', default="zeros", help='For use when developing off-pi, simulates sensor data from a specified CSV file, or all zeros if no file is specified. A sample simulation CSV file is present at sample_simu.csv')

args = parser.parse_args()

if args.simulator == "zeros":
    args.simulator = None
elif args.simulator == None:
    args.simulator = "zeros"
    
if not args.simulator:
    import Adafruit_ADS1x15 as ADS
    from gpiozero import DigitalOutputDevice

logpath = os.path.join(plantpi_path, 'logs')
if not os.path.isdir(logpath):
    os.mkdir(logpath)
logname = 'plantpi-'+datetime.fromtimestamp(time.time()).strftime('%Y%m%d-%H%M%S')+'.log'
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
        lf.write(s+'\n')
        
#   Moisture Mapping, tested with resistive gardening probe, see moisture_mapping.pdf
#   1.5:      0.428 -> dry (0.515 is sensor in open air, but zero ends up falling at about 0.444)
#   >=10:   0.283 -> wet
dry = 0.428
wet = 0.283
m = 8.5/(wet - dry)
b = -m*dry+1.5
def map_moisture(moisture):
    return max(0, min(10, m*moisture+b))
    

class ChannelSpec:
    def __init__(self, moisture_top_chan=0, moisture_bottom_chan=1, light1_chan=2, light2_chan=3):
        self.moisture_top = moisture_top_chan
        self.moisture_bottom = moisture_bottom_chan
        self.light1 = light1_chan
        self.light2 = light2_chan
        
class PlantProfile:
    def __init__(self, name, moisture_min, moisture_max, light_min, light_max):
        assert moisture_min >= 0 and moisture_max >= 0 and light_min >= 0 and light_max >= 0
        self.name = name
        self.moisture_min = moisture_min
        self.moisture_max = moisture_max
        self.light_min = light_min/10
        self.light_max = light_max/10
        
class FakePump:
    def __init__(self):
        self.value = 0
    def on(self):
        self.value = 1
    def off(self):
        self.value = 0

class PlantPi:
    def __init__(self, plant_profile_name, relay_gpio=14, channel_spec=ChannelSpec(), fill_time=5, fill_pad=0.9):
        self.plant_profile = None
        assert relay_gpio < 26
        self.channel_spec = channel_spec
        self.time = 0
        self.moisture_top = 0
        self.moisture_bottom = 0
        self.light1 = 0
        self.light2 = 0
        self.done = False
        self.sample = False
        # Create the ADC object using the I2C bus
        if not args.simulator:
            self.pump = DigitalOutputDevice(relay_gpio, active_high=False)
            self.adc = ADS.ADS1115()
        else:
            self.pump = FakePump()
            
        self.need_fill = False
        self.need_top_off = False
        self.start_fill = None
        self.pause_fill = None
        self.fill_time = fill_time
        self.last_pump_val = 0
        assert fill_time > 0
        self.fill_pad = fill_pad
        assert fill_pad > 0
        #setup email notifier
        self.emailer = Emailer()
        self.email_user = None
        self.email_pwd = None
        self.email_to = None
        self.email_from = None
        with open(os.path.join(plantpi_path,'email_auth.json'), 'r') as f:
            auth = json.load(f)
            if 'user' in auth:
                self.email_user = auth['user']
            if 'password' in auth:
                self.email_pwd = auth['password']
            if 'to' in auth:
                self.email_to = auth['to']
            if 'from' in auth:
                self.email_from = auth['from']
                
        if self.email_user == None or self.email_pwd == None or self.email_to == None or self.email_from == None or args.quiet:
            self.email_user = None
            self.email_pwd = None
            self.email_to = None
            self.email_from = None
            if not args.quiet:
                log('Warning: Failed to parse email_auth.json, notifications will be disabled\n')    
            
        self.simu_seq = 0
        self.last_simu_vals = []
        self.simu = {}
        if args.simulator != None and args.simulator != "zeros":
            with open(args.simulator, 'r') as f:
                for l in f.readlines()[1:]:
                    if len(l) == 0:
                        continue
                    ls = l.split(',')
                    self.simu[int(ls[0])] = float(ls[1]), float(ls[2]), float(ls[3]), float(ls[4])

        self.qt = None
        
        
        self.profiles = []
        for f in os.listdir(profile_path):
            if f.endswith('.json'):
                with open(os.path.join(profile_path,f), 'r') as p:
                    j = json.load(p)
                    try:
                        pp = PlantProfile(j['name'], j['moisture_min'], j['moisture_max'], j['light_min'], j['light_max'])
                        if plant_profile_name and (plant_profile_name == pp.name or plant_profile_name == pp.name.lower() or f[:-5] == plant_profile_name):
                            self.plant_profile = pp
                        self.profiles.append(pp)
                    except Exception as e:
                        log(f"Warning: Failed to parse {os.path.join(profile_path,f)} into PlantProfile: {e.message}")
                if plant_profile_name and not self.plant_profile:
                    log(f"Warning: Failed to find requested profile '{plant_profile_name}'")
                        
        if not self.plant_profile:
            if len(self.profiles) == 0:
                log(f'No available profiles, please add some to {profile_path}')
                exit(0)
            print('Available Plant Profiles')            
            for i in range(len(self.profiles)):
                print(f'\t{i+1}: {self.profiles[i].name}')
            n = 0
            while True:
                try:    
                    n = int(input('Please select a plant profile from the list above by number: '))
                    print()
                except KeyboardInterrupt as e:
                    raise e
                except:
                    pass
                if n <= 0 or n > len(self.profiles):
                    print(f'Error: Please enter an integer in the range 1 -> {len(self.profiles)}')
                else:
                    break
            self.plant_profile = self.profiles[n-1]                
    
    def get_data_rest(self):
        d = request.data
        j = {}
        if d:
            j = json.loads(d)
        if 'start_time' in j or 'end_time' in j:
            if 'start_time' in j:
                s = j['start_time']
            else:
                s = 0
            if 'end_time' in j:
                e = j['end_time']
            else:
                e = 1e10
            with open(args.file, 'r') as f:
                lines = []
                for l in f.readlines()[1:]:
                    ls = l.split(',')
                    t = float(ls[0])
                    if t < e and t > s:
                        lines.append(l)
                return jsonify(''.join(lines))
        else:
            with open(args.file, 'r') as f:
                lines = f.readlines()[1:]
                s = 0
                for l in lines:
                    s += len(l.encode('utf-8'))
                
                i = 1
                while s > 100000000:
                    s -= len(lines[i].encode('utf-8'))
                    i += 1
                if i > 1:
                    del lines[1:i]
                
                return jsonify(''.join(lines))
            
    
    def get_sample_rest(self):
        t, moisture_top, moisture_bottom, light1, light2 = self.get_data()
        moisture_top = map_moisture(moisture_top)
        moisture_bottom = map_moisture(moisture_bottom)
        d = { \
              'time': get_time(t, False), \
              'pump': self.pump.value == 1 ,\
              'moisture_top': moisture_top, \
              'moisture_bottom': moisture_bottom, \
              'light1': light1, \
              'light2': light2 \
            }
        self.sample = True
        with self.cond:
            self.cond.notify_all()
        return jsonify(d)
    
    def water_rest(self):
        d = request.data
        j = {}
        if d:
            j = json.loads(d)
        if "time" in j:
            args.water = True
            with self.cond:
                self.cond.notify_all()
            slept = False
            try:
                sleep(int(j['time']))
                slept = True
            except:
                pass
            args.water = False
            if slept:
                return jsonify(f'Watered for {int(j["time"])} seconds')
            return jsonify("Failed to water: 'time' must be an integer")
        else:
            if args.water:
                args.water = False
                return jsonify('Stopped watering')
            else:
                args.water = True
                with self.cond:
                    self.cond.notify_all()
                return jsonify('Started watering')
            
    def set_plant_profile_rest(self):
        j = json.loads(request.data)
        msg = None
        if 'moisture_max' in j:
            self.plant_profile = PlantProfile(str(j['name']), float(j['moisture_min']), float(j['moisture_max']), float(j['light_min']), float(j['light_max']))
            msg = 'Plant profile set to:\n'+json.dumps(j, indent=4)
        else:
            for p in self.profiles:
                if p.name == str(j['name']):
                    msg = f'Plant profile set to {p.name}'
                    break
                    
        if not msg:
            msg = f"Failed to set plant profile: Couldn't find requested profile '{str(j['name'])}'"
        log(msg+'\n')
        return jsonify(msg)
        
                    
    def __del__(self):
        try:
            self.stop_watering()
        except:
            pass
                    
    def get_data(self):
        if args.simulator:
            mt = 0.0
            mb = 0.0
            l1 = 0.0
            l2 = 0.0
            if len(self.simu):
                if self.simu_seq in self.simu.keys():
                    self.last_simu_vals = self.simu[self.simu_seq]
                mt, mb, l1, l2 = self.last_simu_vals
                self.simu_seq += 1
            return time.time(), mt, mb, l1, l2
        else:
            return time.time(), \
                    self.adc.read_adc(self.channel_spec.moisture_top)/32767, \
                    self.adc.read_adc(self.channel_spec.moisture_bottom)/32767, \
                    self.adc.read_adc(self.channel_spec.light1)/32767, \
                    self.adc.read_adc(self.channel_spec.light2)/32767
    def water(self):
        if(self.pump.value == 0):
            self.pump.on()
            log('Pump On\n')
    
    def stop_watering(self):
        if(self.pump.value == 1):
            self.pump.off()
            log('Pump Off\n')

    def water_if_thirsty(self):
        # If we don't need to fill, check against the low threshold, otherwise, check against the high threshold so we fill it up to that point
        thresh = self.plant_profile.moisture_min
        if self.need_fill or self.need_top_off:
            thresh = self.plant_profile.moisture_max

        # If both sensors are above the threshold, dont water
        if self.moisture_bottom > thresh and self.moisture_top > thresh:
            self.need_fill = False
            self.need_top_off = False
            self.pause_fill = None
            self.start_fill = None
            return self.stop_watering()
        
        # If the bottom sensor is below the threshold and we aren't currently topping off, water for fill_time seconds, 
        # then wait for 2*fill_time seconds and then repeat if needed to let the water settle.
        # When filling, stop at 100*fill_coef % of max moisture level (for bottom sensor) to let water settle
        if (not self.need_fill and not self.need_top_off and self.moisture_bottom < thresh ) or (self.need_fill and self.moisture_bottom < self.fill_pad*thresh):
            self.need_fill = True
            self.need_top_off = False                

            if (not self.pause_fill) and self.start_fill and self.time - self.start_fill > self.fill_time:
                self.pause_fill = self.time
            if self.pause_fill and self.time - self.pause_fill < 2*self.fill_time:
                self.start_fill = None
                return self.stop_watering()
            if not self.start_fill:
                self.start_fill = self.time
            self.pause_fill = None
            return self.water()
        
        self.need_fill = False
        self.pause_fill = None
        self.start_fill = None
        
        # Otherwise, only the top sensor below the threshold, water until it isn't. Don't water if bottom is too wet
        if self.moisture_top < thresh and self.moisture_bottom < self.plant_profile.moisture_max:
            self.need_top_off = True
            return self.water()
        self.need_top_off = False
        return self.stop_watering()

    def on_press(self, key):
        if key == 's':
            if not args.verbose:
                t, moisture_top, moisture_bottom, light1, light2 = self.get_data()
                moisture_top = map_moisture(moisture_top)
                moisture_bottom = map_moisture(moisture_bottom)
                log(f'\rSample:\n{get_time(t, False)}:\nPump: {self.pump.value == 1}')
                log(f'Top: {moisture_top}')
                log(f'Bottom: {moisture_bottom}')
                log(f'Light 1: {light1}')
                log(f'Light 2: {light2}\n')
            self.sample = True
            with self.cond:
                self.cond.notify_all()
        elif key == 'q':
            self.done = True
            with self.cond:
                self.cond.notify_all()
            stop_listening()
        elif key == 'w':
            args.water = True
            with self.cond:
                self.cond.notify_all()
            
    def on_release(self, key):
        if key == 'w':
            args.water = False

    def query_thread(self):
        try:
            log('Press "s" key to print sample')
            log('Hold "w" key to water')
            log('Press "q" key to quit\n')
            listen_keyboard(on_press=self.on_press, on_release=self.on_release, until=None)
        except KeyboardInterrupt:
            stop_listening()
            self.done = True
            with self.cond:
                self.cond.notify_all()

    def run(self):
        file = None
        if not args.file or not (len(os.path.dirname(args.file)) == 0 or os.path.exists(os.path.dirname(args.file))):
            args.file = None

        log(f"Running with plant profile '{self.plant_profile.name}'...\n")
        
        self.rest_server = RestServer(__name__)
        if args.file:
            self.rest_server.add_endpoint(methods=['GET'], url='/data', endpoint_name='Data', handler=self.get_data_rest)
        self.rest_server.add_endpoint(methods=['GET'], url='/sample', endpoint_name='Sample', handler=self.get_sample_rest)
        self.rest_server.add_endpoint(methods=['POST'], url='/water', endpoint_name='Water', handler=self.water_rest)
        self.rest_server.add_endpoint(methods=['POST'], url='/plant', endpoint_name='Plant', handler=self.set_plant_profile_rest)
        self.rest_server.start()

        if not args.verbose or not args.test:
            self.cond = threading.Condition()
            self.qt = threading.Thread(target=self.query_thread)
            self.qt.start()
            
        try:
            while not self.done:
                
                self.time, self.moisture_top, self.moisture_bottom, self.light1, self.light2 = self.get_data()

                mt = self.moisture_top
                mb = self.moisture_bottom
                self.moisture_top = map_moisture(self.moisture_top)
                self.moisture_bottom = map_moisture(self.moisture_bottom)
                
                if args.water:
                    self.water()
                    sleep(0.5)
                    self.need_fill = False
                    self.need_top_off = False
                    self.pause_fill = None
                    self.start_fill = None
                    continue

                self.water_if_thirsty()  
                if self.email_user and self.email_pwd and self.email_to and self.email_from:
                    if self.pump.value == 1 and self.last_pump_val == 0 and not self.pause_fill:
                        msg = f'{get_time(self.time, False)}\n' \
                              f'Pump: {self.pump.value == 1}\n' \
                              f'Top: {self.moisture_top}\n' \
                              f'Bottom: {self.moisture_bottom}\n' \
                              f'Light 1: {self.light1}\n' \
                              f'Light 2: {self.light2}\n'
                        try:
                            self.emailer.send_email(self.email_user, self.email_pwd, self.email_to, self.email_from, "PlantPi Pump Activated", msg)
                            log(f'Email sent from {self.email_from} to {self.email_to}\n')
                        except Exception as e:
                            log(f'Warning: Failed to send notification email: {e.message}\n', flush=True)
                    self.last_pump_val = self.pump.value

                if args.verbose:
                    log(f'{get_time(self.time, False)}:\nPump: {self.pump.value == 1}')
                    log(f'TOP: {mt} -> {self.moisture_top}')
                    log(f'BOTTOM: {mb} -> {self.moisture_bottom}')
                    log(f'Light 1: {self.light1}')
                    log(f'Light 2: {self.light2}\n')
  

                header = 'TIME,TOP,MAPPED TOP,BOTTOM,MAPPED BOTTOM,LIGHT1,LIGHT2,PUMP\n'
                if args.file:
                    with open(args.file, 'a+') as file:
                        t = file.tell()
                        file.seek(0)
                        lines = file.readlines()
                        file.seek(t)
                        if len(lines) == 0:
                            file.write(header)
                        elif lines[0] != header:
                            file.truncate(0)
                            file.write(header)
                        file.write(f'{self.time},{mt},{self.moisture_top},{mb},{self.moisture_bottom},{self.light1},{self.light2},{self.pump.value}\n')

                
                # Use a shorter 0.5 sec update when watering and a 30 min update otherwise
                if self.need_top_off or self.need_fill or args.test:
                    sleep(0.5)
                else:
                    with self.cond:
                        self.cond.wait_for(lambda : (self.done==True or args.water==True or self.sample==True), timeout=1800)
                        self.sample = False
        except KeyboardInterrupt:
            pass
        log("Quitting...")
        stop_listening()
        if self.qt:
            self.qt.join()
        self.rest_server.stop()
        self.stop_watering()

if __name__ == "__main__":
    try:
        log("Starting PlantPi...\n")
        pp = PlantPi(args.plant)
        pp.run()
    except KeyboardInterrupt:
        log("\nQuitting...")
