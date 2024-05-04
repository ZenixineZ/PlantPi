#!/usr/bin/python
from gpiozero import DigitalOutputDevice
import time
from datetime import datetime
from time import sleep
import Adafruit_ADS1x15 as ADS
import os

## TODO:
#   -add notification system
#   -figure out threshold mapping to standard scales for light and mositure
#   -test moisture handling
#   -think of a better way of dealing with data than simple thresholding if needed
#   -

def get_time():
    return datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S')

class ChannelSpec:
    def __init__(self, moisture_top_chan=0, moisture_bottom_chan=1, light1_chan=2, light2_chan=3):
        self.moisture_top = moisture_top_chan
        self.moisture_bottom = moisture_bottom_chan
        self.light1 = light1_chan
        self.light2 = light2_chan
        
class PlantProfile:
    def __init__(self, name, moisture_min, moisture_max, light_min, light_max):
        self.name = name
        self.moisture_min = moisture_min/10
        self.moisture_max = moisture_max/10
        self.light_min = light_min/10
        self.light_max = light_max/10

class PlantPi:
    def __init__(self, plant_profile : PlantProfile, relay_pin=14, channel_spec=ChannelSpec()):

        self.plant_profile = plant_profile
        self.pump = DigitalOutputDevice(14, active_high=False)
        self.channel_spec = channel_spec

        # Create the ADC object using the I2C bus
        self.adc = ADS.ADS1115()
        self.cnt = 0
        self.need_fill = False
        write_header = not os.path.isfile("data.csv")
        self.data_file = open("data.csv", "a")
        if write_header:
            self.data_file.write("TIME,TOP MOISTURE,BOTTOM MOISTURE,LIGHT 1,LIGHT 2,PUMP STATE,PLANT PROFILE\n")
        
    def __del__(self):
        self.data_file.close()

    def log(self, string):
        print(get_time() + ", " + string)

    def check_light_out_of_range(self, light1, light2):
        if light1 > self.plant_profile.light_max:
            self.log("Sensor 1 Too Bright")
        if light1 < self.plant_profile.light_min:
            self.log("Sensor 1 Too Dim")
        if light2 > self.plant_profile.light_max:
            self.log("Sensor 2 Too Bright")
        if light2 < self.plant_profile.light_min:
            self.log("Sensor 2 Too Dim")
            
    def water(self):
        if(self.pump.value == 0):
            self.pump.on()
            self.log("Started Watering")
    
    def stop_watering(self):
        if(self.pump.value == 1):
            self.pump.off()
            self.log("Stopped Watering")

    def water_if_thirsty(self, moisture_top, moisture_bottom):
        # If we don't need to fill, check against the low threshold, otherwise, check against the high threshold so we fill it up to that point
        thresh = self.plant_profile.moisture_min
        if self.need_fill:
            thresh = self.plant_profile.moisture_max
        # If both sensors are above the threshold, dont water
        if moisture_bottom > thresh and moisture_top > thresh:
            self.need_fill = False
            self.need_top_off = False
            self.cnt = 0
            return self.stop_watering()
        # If the bottom sensor is below the threshold, water for 5 seconds, wait for 10 and then repeat if needed to allow the water time to settle
        if moisture_bottom < thresh:
            self.need_fill = True
            self.need_top_off = False
            if self.cnt == 15:
                self.cnt = 0
            if self.cnt >= 5:
                return self.stop_watering()
            self.cnt += 1
            return self.water()
        
        self.need_fill = False
        # Otherwise, only the top sensor below the threshold, water until it isn't
        if moisture_top < thresh:
            self.need_top_off = True
            return self.water()
        self.cnt = 0
        self.need_top_off = False
        return self.stop_watering()


    def run(self):
        while True:
            moisture_top = self.adc.read_adc(self.channel_spec.moisture_top)/32767
            moisture_bottom  = self.adc.read_adc(self.channel_spec.moisture_top)/32767
            light1 = self.adc.read_adc(self.channel_spec.moisture_top)/32767
            light2 = self.adc.read_adc(self.channel_spec.moisture_top)/32767
            self.data_file.write(','.join([get_time(), str(moisture_top), str(moisture_bottom), str(light1), str(light2), str(self.pump.value == 0), self.plant_profile.name])+'\n')
            self.water_if_thirsty(moisture_top, moisture_bottom)    
            self.check_light_out_of_range(light1, light2)
            # Use a shorter 1 sec update when watering and a 30 min update otherwise
            if self.need_top_off or self.need_fill:
                sleep(1)
            else:
                sleep(180)
            
            
if __name__ == "__main__":
    palm = PlantProfile("Majestic Palm", 3, 7, 4, 6)
    dracaena = PlantProfile("Dragon Plant", 3, 7, 4, 7)
    pp = PlantPi(dracaena)
    pp.run()
