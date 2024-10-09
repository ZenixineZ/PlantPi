#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Oct  7 00:43:05 2024

@author: zenix
"""
from flask import Flask

from werkzeug.serving import make_server
import threading

class EndpointAction():

    def __init__(self, action):
        self.action = action

    def __call__(self, *args):
        return self.action()
    

class RestServer(threading.Thread):
    def __init__(self, name, port=8080):
        self.app = Flask(name)
        threading.Thread.__init__(self)
        self.server = make_server('0.0.0.0', port, self.app)
        self.ctx = self.app.app_context()
        self.ctx.push()

    def run(self):
        self.server.serve_forever()

    def add_endpoint(self, methods=None, url=None, endpoint_name=None, handler=None):
        self.app.add_url_rule(url, endpoint_name, EndpointAction(handler), methods=methods)
        
    def stop(self):
        self.server.shutdown()