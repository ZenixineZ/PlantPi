#!/usr/bin/python
from gpiozero import AnalogInputDevice,DigitalOutputDevice
from time import sleep
import board
import busio
import Adafruit-ADS1x15.ads1115 as ADS
from Adafruit-ADS1x15.analog_in import AnalogIn

class ADS1115(AnalogInputDevice):
    
    def __init__(self, channel, differential=False, **spi_args):
        self.channel = channel
        
        self.differential = differential
        super().__init__(bits=16, max_voltage=3.0, **spi_args)	
        
    @property
    def channel(self):
        return self.channel
    
    @property
    def differential(self):
        return self.differential
    
    def _read(self):
        return self._words_to_int(self._spi.transfer(self._send())[-2:], self.bits)

pump = DigitalOutputDevice(14, active_high=True)

# Create the I2C bus
i2c = busio.I2C(board.SCL, board.SDA)

# Create the ADC object using the I2C bus
ads = ADS.ADS1115(i2c)

# Create single-ended input on channel 0
chan1 = AnalogIn(ads, ADS.P0)
chan2 = AnalogIn(ads, ADS.P1)
chan3 = AnalogIn(ads, ADS.P2)
chan4 = AnalogIn(ads, ADS.P3)

while True:
    print("{:>5}\t{:>5.3f} | {:>5}\t{:>5.3f} | {:>5}\t{:>5.3f} | {:>5}\t{:>5.3f}".format(chan1.value, chan1.voltage, chan2.value, chan2.voltage, chan3.value, chan3.voltage, chan4.value, chan4.voltage))
    sleep(1)

# 	print("ON")
# 	pump.on()
# 	sleep(2)
# 	print("OFF")
# 	pump.off()
# 	sleep(2)