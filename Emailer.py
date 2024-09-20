#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Sep 20 15:16:23 2024

@author: zenix
"""
from email.mime.text import MIMEText
import smtplib


class Emailer:
    def __init__(self, server="smtp.gmail.com", port=587):
        self.SMTP_SERVER = server
        self.SMTP_PORT = port
        self.EMAIL_SPACE = ", "
        
    def send_email(self, username, password, to, From, subject, data):
        EMAIL_TO = [to]
        EMAIL_FROM = From
        msg = MIMEText(data)
        msg['Subject'] = subject
        msg['To'] = self.EMAIL_SPACE.join(EMAIL_TO)
        msg['From'] = EMAIL_FROM
        mail = smtplib.SMTP(self.SMTP_SERVER, self.SMTP_PORT)
        mail.ehlo()
        mail.starttls()
        mail.login(username, password)
        mail.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        mail.quit()
    
