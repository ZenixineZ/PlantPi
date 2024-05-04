#!/usr/bin/python
from gpiozero import AnalogInputDevice,LED

pump = LED(17)


while True:
	pump.on()
	sleep(1)
	pump.off()
	sleep(1)