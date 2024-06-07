#!/usr/bin/python
from gpiozero import DigitalOutputDevice
import time
from datetime import datetime
from time import sleep
import Adafruit_ADS1x15 as ADS
import sys
import requests

## TODO:
#   -DEV:
#       -add notification system
#       -restart handling, service?
#       -Real time graph: find a better graphing library for growing graphs, 
#           ideally one that can be zoomed in easily on the new data
#   -TEST:
#       -figure out threshold mapping to standard scales for light and mositure
#       -test moisture handling and revise thresholding if needed
#       - 


#   Moisture Mapping, tested with resistive gardening probe
#   1:      0.515 
#   >=10:   0.365
#
#   m = (10 - 1)/(0.365 - 0.515) ~= -60
#   y - 1 = 60 * (x - 0.515)
#   b = 60*0.515+1

m = -60
b = 60*0.515+1
def map_moisture(moisture):
    if moisture > 0.515:
        return 0.0
    elif moisture < 0.365:
        return 10.0
    return m*moisture+b
    
def get_time():
    return datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S.%f')

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
        self.moisture_min = moisture_min/10
        self.moisture_max = moisture_max/10
        self.light_min = light_min/10
        self.light_max = light_max/10

class PlantPi:
    def __init__(self, plant_profile : PlantProfile, relay_gpio=14, channel_spec=ChannelSpec(), fill_time=5, fill_pad=0.9):
        self.plant_profile = plant_profile
        assert relay_gpio < 26
        self.pump = DigitalOutputDevice(relay_gpio, active_high=False)
        self.channel_spec = channel_spec

        self.time = 0
        self.moisture_top = 0
        self.moisture_bottom = 0
        self.light1 = 0
        self.light2 = 0
        # Create the ADC object using the I2C bus
        self.adc = ADS.ADS1115()
        self.need_fill = False
        self.need_top_off = False
        self.start_fill = None
        self.pause_fill = None
        self.fill_time = fill_time
        assert fill_time > 0
        self.fill_pad = fill_pad
        assert fill_pad > 0
        d = { \
                'name': plant_profile.name, \
                'moisture_min': plant_profile.moisture_min, \
                'moisture_max': plant_profile.moisture_maxv, \
                'light_min': plant_profile.light_min, \
                'light_max': plant_profile.light_max \
            }
        requests.post('http://127.0.0.1:8080/plant', json=d)

        
            
    def water(self):
        if(self.pump.value == 0):
            self.pump.on()
    
    def stop_watering(self):
        if(self.pump.value == 1):
            self.pump.off()

    def water_if_thirsty(self):
        # If we don't need to fill, check against the low threshold, otherwise, check against the high threshold so we fill it up to that point
        thresh = self.plant_profile.moisture_min
        if self.need_fill:
            thresh = self.plant_profile.moisture_max

        # If both sensors are above the threshold, dont water
        if self.moisture_bottom > thresh and self.moisture_top > thresh:
            self.need_fill = False
            self.need_top_off = False
            self.pause_fill = None
            self.start_fill = None
            return self.stop_watering()
        # If the bottom sensor is below the threshold, water for fill_time seconds, 
        # then wait for 2*fill_time seconds and then repeat if needed to let the water settle.
        # When filling, stop at 100*fill_coef % of max moisture level (for bottom sensor) to let water settle
        if (not self.need_fill and self.moisture_bottom < thresh) or (self.need_fill and self.moisture_bottom < self.fill_pad*thresh):
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
        # Otherwise, only the top sensor below the threshold, water until it isn't
        if self.moisture_top < thresh:
            self.need_top_off = True
            return self.water()
        self.need_top_off = False
        return self.stop_watering()           
                
    def run(self):
        try:
            while True:
                self.time = time.time()
                self.moisture_top = map_moisture(self.adc.read_adc(self.channel_spec.moisture_top)/32767)
                self.moisture_bottom = map_moisture(self.adc.read_adc(self.channel_spec.moisture_bottom)/32767)
                self.light1 = self.adc.read_adc(self.channel_spec.light1)/32767
                self.light2 = self.adc.read_adc(self.channel_spec.light2)/32767
                
                self.water_if_thirsty()    
                d = { \
                     'time': self.time, \
                     'moisture_top': self.moisture_top, \
                     'moisture_bottom': self.moisture_bottom, \
                     'light1': self.light1, \
                     'light2': self.light2, \
                     'pump': self.pump.value == 1 \
                    }
                
                retry = 0
                while retry < 5:
                    try:
                        requests.post('http://127.0.0.1:8080/data', json=d)
                    except requests.exceptions.RequestException:
                        pass                                # Use a shorter 0.25 sec update when watering and a 30 min update otherwise
                if self.need_top_off or self.need_fill or (len(sys.argv) > 1  and sys.argv[1] == '-t'):
                    sleep(0.25)
                else:
                    sleep(1800)
        except KeyboardInterrupt:
            self.stop_watering()

if __name__ == "__main__":
    palm = PlantProfile(name="Majestic Palm", moisture_min=3, moisture_max=7, light_min=4, light_max=6) # light vals are placeholders
    dracaena = PlantProfile(name="Dragon Plant", moisture_min=3, moisture_max=7, light_min=4, light_max=7) # light vals are placeholders
    pp = PlantPi(PlantProfile(name="TEST", moisture_min=0, moisture_max=0, light_min=0, light_max=10))
    pp.run()
