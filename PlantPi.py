#!/usr/bin/python
from gpiozero import AnalogInputDevice,LED
from time import sleep

pump = LED(17)


while True:
	print("ON")
	pump.on()
	sleep(1)
	print("OFF")
	pump.off()
	sleep(1)