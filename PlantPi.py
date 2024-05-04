#!/usr/bin/python
from gpiozero import AnalogInputDevice,DigitalOutputDevice
from time import sleep
# import board
# import busio
import adafruit_ads1x15.ads1015 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

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
# i2c = busio.I2C(board.SCL, board.SDA)

# Create the ADC object using the I2C bus
ads = ADS.ADS1115()

# Create single-ended input on channel 0
chan1 = AnalogIn(ads, ADS.P0)
chan2 = AnalogIn(ads, ADS.P1)
chan3 = AnalogIn(ads, ADS.P2)
chan4 = AnalogIn(ads, ADS.P3)

while True:
# Read all the ADC channel values in a list.
    values = [0]*4
    for i in range(4):
        # Read the specified ADC channel using the previously set gain value.
        values[i] = adc.read_adc(i, gain=GAIN)
        # Note you can also pass in an optional data_rate parameter that controls
        # the ADC conversion time (in samples/second). Each chip has a different
        # set of allowed data rate values, see datasheet Table 9 config register
        # DR bit values.
        #values[i] = adc.read_adc(i, gain=GAIN, data_rate=128)
        # Each value will be a 12 or 16 bit signed integer value depending on the
        # ADC (ADS1015 = 12-bit, ADS1115 = 16-bit).
    # Print the ADC values.
    print('| {0:>6} | {1:>6} | {2:>6} | {3:>6} |'.format(*values))
    # Pause for half a second.
    sleep(1)


# 	print("ON")
# 	pump.on()
# 	sleep(2)
# 	print("OFF")
# 	pump.off()
# 	sleep(2)