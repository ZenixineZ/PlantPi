#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Sep 15 02:40:10 2024

@author: zenix
"""

import os
from matplotlib import pyplot as plt
from datetime import datetime
import numpy as np

plt.close("all")



dry = 0.428
wet = 0.283
m = 8.5/(wet - dry)
b = -m*dry+1.5
def map_moisture(moisture):
    return max(0, min(10, m*moisture+b))


def read_file(filename):
    with open(f'{os.path.expanduser("~")}/git/PlantPi/{filename}') as file:
        t = []
        a1 = []
        a2 = []
        a3 = []
        for line in file.readlines():
            ls = line.split(",")
            if len(t) == 0:
                t = ls
                continue
            ls = line.split(",")
            a1.append(float(ls[0]))
            a2.append(float(ls[1]))
            a3.append(float(ls[2]))
        return [t, a1, a2, a3]
    return None


tit_data, time_data, top_data, bot_data = read_file('moisture_data.csv')
tit_stick, time_stick, top_stick, bot_stick = read_file('moisture_stick.csv')


top_data = [map_moisture(i) for i in top_data]
bot_data = [map_moisture(i) for i in bot_data]


time_labels = []
time_ticks = []
diff = 0
last = 0
c = 0
navg = 100
navg_top = 25
for i in time_data:
    bot_data[c] = np.mean(bot_data[c:c+navg])
    top_data[c] = np.mean(top_data[c:c+navg_top])
    c += 1
    if diff > 3600*24:
        time_labels.append(datetime.fromtimestamp(i).strftime('%m/%d %H:%M'))
        time_ticks.append(i)
        diff = 0
    else:
        diff += i - last
    last = i



time_ticks.extend(time_stick)
time_labels.extend([datetime.fromtimestamp(i).strftime('%m/%d %H:%M') for i in time_stick])

ax = plt.axes()
ax.plot(time_data, top_data, "tab:blue")
ax.plot(time_data, bot_data, "tab:orange")
ax.set_xticks(ticks=time_ticks, labels=time_labels, rotation=45, horizontalalignment='right')
ax.plot(time_stick, top_stick, color="tab:blue", marker="x", linestyle='None')
ax.plot(time_stick, bot_stick, color="tab:orange", marker="*", linestyle='None')

plt.legend(labels=['Top', 'Bottom'])
ax.grid() 
plt.show()