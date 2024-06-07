#!/usr/bin/python
from gpiozero import DigitalOutputDevice
import time
from datetime import datetime
from time import sleep
import Adafruit_ADS1x15 as ADS
import os
import matplotlib.pyplot as plt
import sys

## TODO:
#   -DEV:
#       -add notification system
#       -restart handling
#       -Real time graph
#   -TEST:
#       -figure out threshold mapping to standard scales for light and mositure
#       -test moisture handling and revise thresholding if needed
#       - 
    
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
        self.name = name
        self.moisture_min = moisture_min/10
        self.moisture_max = moisture_max/10
        self.light_min = light_min/10
        self.light_max = light_max/10

class PlantPi:
    def __init__(self, plant_profile : PlantProfile, relay_pin=14, channel_spec=ChannelSpec()):
        self.data_file = None
        self.plant_profile = plant_profile
        self.pump = DigitalOutputDevice(14, active_high=False)
        self.channel_spec = channel_spec

        self.times = []
        self.moisture_top_buff = []
        self.moisture_bottom_buff = []
        self.light1_buff = []
        self.light2_buff = []
        # Create the ADC object using the I2C bus
        self.adc = ADS.ADS1115()
        self.cnt = 0
        self.need_fill = False
        write_header = not os.path.isfile("data.csv")
        self.data_file = open("data.csv", "a")
        if write_header:
            self.data_file.write("TIME,TOP MOISTURE,BOTTOM MOISTURE,LIGHT 1,LIGHT 2,PUMP STATE,PLANT PROFILE\n")
        
    def __del__(self):
        if(self.data_file):
            self.data_file.close()

    def log(self, string):
        print(get_time() + ": " + string)

    def check_light_out_of_range(self):
        light1 = self.light1_buff[-1]
        light2 = self.light2_buff[-1]
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

    def water_if_thirsty(self):
        moisture_top = self.moisture_top_buff[-1]
        moisture_bottom = self.moisture_bottom_buff[-1]
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

    def read_data(self):
            t = time.time()
            moisture_top = self.adc.read_adc(self.channel_spec.moisture_top)/32767
            moisture_bottom = self.adc.read_adc(self.channel_spec.moisture_bottom)/32767
            light1 = self.adc.read_adc(self.channel_spec.light1)/32767
            light2 = self.adc.read_adc(self.channel_spec.light2)/32767
            self.times.append(t)
            self.moisture_top_buff.append(moisture_top)
            self.moisture_bottom_buff.append(moisture_bottom)
            self.light1_buff.append(light1)
            self.light2_buff.append(light2)
            self.data_file.write(','.join([str(t), str(moisture_top), str(moisture_bottom), str(light1), str(light2), str(self.pump.value == 1), self.plant_profile.name])+'\n')
            while self.times[-1]-self.times[0] > 60*60*12:
                del self.times[0]
                del self.moisture_top_buff[0]
                del self.moisture_bottom_buff[0]
                del self.light1_buff[0]
                del self.light2_buff[0]
                
    def graph(self):
        if len(self.times) == 1:
            self.fig, self.sps = plt.subplots(nrows=2,ncols=1)
            self.sps[0].set_title('Top & Bottom Moisture')
            self.sps[0].set_ylim(0, 10)
            self.sps[1].set_title('Light 1 & Light 2')
            self.sps[1].set_ylim(0, 10)
            self.sps[0].grid()
            self.sps[1].grid()

            self.plot_mt, = self.sps[0].plot([],[],'b-')
            self.plot_mb, = self.sps[0].plot([],[],'r-')
            self.plot_l1, = self.sps[1].plot([],[],'c-')
            self.plot_l2, = self.sps[1].plot([],[],'m-')
            self.t0 = time.time()
            plt.show(block=False)
        if len(self.times) > 1:
            t =  [x - self.t0 for x in self.times]
            mt = [x * 10 for x in self.moisture_top_buff]
            mb = [x * 10 for x in self.moisture_bottom_buff]
            l1 = [x * 10 for x in self.light1_buff]
            l2 = [x * 10 for x in self.light2_buff]
            self.plot_mt.set_data(t, mt)
            self.plot_mb.set_data(t, mb)
            self.plot_l1.set_data(t, l1)
            self.plot_l2.set_data(t, l2)
            self.sps[0].legend(loc="upper right", labels=['Top: '+str(mt[-1])[0:4],'Bottom: '+str(mb[-1])[0:4]])                                                                                                                
            self.sps[1].legend(loc="upper right", labels=['1: '+str(l1[-1])[0:4],'2: '+str(l2[-1])[0:4]])
            
            self.sps[0].set_xlim(min(t), max(t))
            self.sps[1].set_xlim(min(t), max(t))
            self.fig.canvas.draw()
            self.fig.canvas.flush_events()
            plt.show(block=False)

    def run(self):
        try:
            while True:
                self.read_data()
                self.water_if_thirsty()    
                self.check_light_out_of_range()
                self.graph()
                # Use a shorter 1 sec update when watering and a 30 min update otherwise
                if self.need_top_off or self.need_fill or (len(sys.argv) > 1  and sys.argv[1] == '-t'):
                    sleep(0.5)
                else:
                    sleep(1800)
        except KeyboardInterrupt:
            plt.close("all")
            raise KeyboardInterrupt            
            
if __name__ == "__main__":
    palm = PlantProfile(name="Majestic Palm", moisture_min=3, moisture_max=7, light_min=4, light_max=6)
    dracaena = PlantProfile(name="Dragon Plant", moisture_min=3, moisture_max=7, light_min=4, light_max=7)
    pp = PlantPi(dracaena)
    pp.run()
