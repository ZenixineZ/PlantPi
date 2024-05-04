#!/usr/bin/python
from gpiozero import DigitalOutputDevice
from time import sleep
import Adafruit_ADS1x15 as ADS

## TODO:
#   -add data logger
#   -add notification system
#   -figure out threshold mapping to standard scales for light and mositure
#   -add plant profiles
#   -test moisture handling
#   -think of a better way of dealing with data than simple thresholding if needed
#   -
class ChannelSpec:
    def __init__(self, moisture_top_chan=0, moisture_bottom_chan=1, light1_chan=2, light2_chan=3):
        self.moisture_top = moisture_top_chan
        self.moisture_bottom = moisture_bottom_chan
        self.light1 = light1_chan
        self.light2 = light2_chan


class PlantPi:
    def __init__(self, relay_pin=14, channel_spec=ChannelSpec()):

        self.pump = DigitalOutputDevice(14, active_high=False)
        self.channel_spec = channel_spec

        # Create the ADC object using the I2C bus
        self.adc = ADS.ADS1115()
        self.cnt = 0

    def check_light_out_of_range(self, thresh_high, thresh_low, light1, light2):
        if light1 > thresh_high:
            print("Sensor 1 Too Bright")
        if light1 < thresh_low:
            print("Sensor 1 Too Dim")
        if light2 > thresh_high:
            print("Sensor 2 Too Bright")
        if light2 < thresh_low:
            print("Sensor 2 Too Dim")

    def plant_thirsty(self, thresh, moisture_top, moisture_bottom):
        if moisture_bottom > thresh and moisture_top > thresh:
            return False
        if moisture_bottom < thresh:
            if self.cnt == 15:
                self.cnt -= 15
            if self.cnt == 5:
                return False
            self.cnt += 1
    
    def run(self):
        while True:
            moisture_top = self.adc.read_adc(self.channel_spec.moisture_top)/32767
            moisture_bottom  = self.adc.read_adc(self.channel_spec.moisture_top)/32767
            light1 = self.adc.read_adc(self.channel_spec.moisture_top)/32767
            light2 = self.adc.read_adc(self.channel_spec.moisture_top)/32767
            
            water_thresh = 0.5
            # if self.plant_thirsty(water_thresh, moisture_top, moisture_bottom):
            #     self.pump.on()
            # else:
            #     self.pump.off()
                
            light_thresh_high = 0.8
            light_thresh_low = 0.2
            self.check_light_out_of_range(light_thresh_high, light_thresh_low, light1, light2)
            sleep(1)
            
            
if __name__ == "__main__":
    pp = PlantPi()
    pp.run()
