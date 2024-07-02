#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon May 13 17:02:30 2024

@author: zphillips
"""
import os
import matplotlib.pyplot as plt
plt.switch_backend('Qt5Agg')

from datetime import datetime

from flask import Flask, jsonify, request
import json
import time
import threading

import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)


app = Flask(__name__)


data_file = None
pump = False
times = []
moisture_top_buff = []
moisture_bottom_buff = []
light1_buff = []
light2_buff = []

plant_name = 'NONE'
moisture_max = 0
moisture_min = 0
light_max = 10
light_min = 0

done = False

def get_time():
    return datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S.%f')

def check_light_out_of_range():
    light1 = light1_buff[-1]
    light2 = light2_buff[-1]
    if light1 > light_max:
        log("Sensor 1 Too Bright")
    if light1 < light_min:
        log("Sensor 1 Too Dim")
    if light2 > light_max:
        log("Sensor 2 Too Bright")
    if light2 < light_min:
        log("Sensor 2 Too Dim")
        
def log(string):
    print(get_time() + ": " + string)
 
def server():
    app.run(host='0.0.0.0', port=8080)  
    global done
    done = True
     
def graph():
    plot_mt = None 
    plot_mb = None 
    plot_l1 = None 
    plot_l2 = None 
    last_len = 0
    sps = []
    fig = None
    t0 = None
    while not done:
        le = len(times)
        if le > 0 and last_len == 0:
            last_len = le
            plt.ion()
            fig, sps = plt.subplots(nrows=2,ncols=1)
            sps[0].set_title('Top & Bottom Moisture')
            sps[0].set_ylim(-1, 10)
            sps[1].set_title('Light 1 & Light 2')
            sps[1].set_ylim(0, 10)
            sps[0].grid()
            sps[1].grid()
    
            plot_mt, = sps[0].plot([],[],'b-')
            plot_mb, = sps[0].plot([],[],'r-')
            plot_l1, = sps[1].plot([],[],'c-')
            plot_l2, = sps[1].plot([],[],'m-')
            t0 = times[0]
            plt.pause(0.1)
        elif le > last_len:
            last_len = le
            t =  [x - t0 for x in times]
            mt = [x * 1 for x in moisture_top_buff]
            mb = [x * 1 for x in moisture_bottom_buff]
            l1 = [x * 10 for x in light1_buff]
            l2 = [x * 10 for x in light2_buff]
            plot_mt.set_data(t, mt)
            plot_mb.set_data(t, mb)
            plot_l1.set_data(t, l1)
            plot_l2.set_data(t, l2)
            sps[0].legend(loc="upper right", labels=['Top: '+str(mt[-1])[0:4],'Bottom: '+str(mb[-1])[0:4]])                                                                                                                
            sps[1].legend(loc="upper right", labels=['1: '+str(l1[-1])[0:4],'2: '+str(l2[-1])[0:4]])
            
            sps[0].set_xlim(min(t), max(t))
            sps[1].set_xlim(min(t), max(t))
            fig.canvas.draw()
            fig.canvas.flush_events()
            plt.pause(0.1)
        else:
            plt.pause(0.5)

@app.route("/data", methods=['POST'])
def data():
    global pump
    d = json.loads(request.data)
    times.append(d['time'])
    moisture_top_buff.append(d['moisture_top'])
    moisture_bottom_buff.append(d['moisture_bottom'])
    light1_buff.append(d['light1'])
    light2_buff.append(d['light2'])
    if pump != d['pump']:
        if d['pump']:
            log("Started Watering")
        else:
            log("Stopped Watering")
        pump = d['pump']
    check_light_out_of_range()
    data_file.write(','.join([str(times[-1]), str(moisture_top_buff[-1]), str(moisture_bottom_buff[-1]), str(light2_buff[-1]), str(light1_buff[-1]), str(pump), plant_name])+'\n')
    while times[-1]-times[0] > 60*60*12:
        del times[0]
        del moisture_top_buff[0]
        del moisture_bottom_buff[0]
        del light1_buff[0]
        del light2_buff[0]
    return jsonify('Success')
                
@app.route("/plant", methods=['POST'])
def plant():
    global plant_name
    global moisture_max
    global moisture_min
    global light_max
    global light_min
    l = json.loads(request.data)
    plant_name = l['name']
    moisture_max = l['moisture_max']
    moisture_min = l['moisture_min']
    light_max = l['light_max']
    light_min = l['light_min']
    return jsonify('Success')

if __name__ == '__main__':
    write_header = not os.path.isfile("data.csv")
    data_file = open("data.csv", "a")
    if write_header:
        data_file.write("TIME,TOP MOISTURE,BOTTOM MOISTURE,LIGHT 1,LIGHT 2,PUMP STATE,PLANT PROFILE\n")
    t1 = threading.Thread(target=server)
    t1.start()
    try:
        graph()
    except KeyboardInterrupt:
        pass
    plt.pause(3)
    plt.close('all')
    
    done = True
    t1.join()
    
    data_file.close()
