#!/usr/bin/env python

import serial
import time
import csv
import collections
import io
import threading
import math
import logging


module_logger = logging.getLogger('py6632B')
charge_logger = logging.getLogger('charge')
discharge_logger = logging.getLogger('discharge')


EOL = '\n'
Measurement = collections.namedtuple('Measurement', ['date', 'time', 'volt', 'curr'])


class HP6632B(threading.Thread):
    def __init__(self, comport, log_interval, log_enable):
        threading.Thread.__init__(self)
        
        self.mutex = threading.Lock()
        self.is_running = threading.Event()
        self.is_running.clear()
        self.ser = None
        self.log_enable = log_enable
        self.q = None
        self.cb = None
        self.log_inter = 1.0

        try:
            self.ser = serial.Serial(comport, 9600, timeout = 0.5)
        except serial.SerialException:
            module_logger.error('Connection could not be opened')
            return

        self.reset_device()
        self.id = self.identify()
        
        if self.id.find('HEWLETT-PACKARD,6632B') >= 0:        
            module_logger.info('Connection established, found id ' + self.id + ", output is " + self.get_output_state())
            self.is_running.set()

            if log_interval >= 0.2:
                # it takes ~109 ms to query a measurement
                self.log_inter = log_interval - 0.109
            else:
                # limit logging speed to prevent deadlocks
                self.log_inter = 0.1
        else:
            module_logger.error('error: Connection established, no HP6632B found')
            return
            
    # This thread is responsible for writing to the log file
    def run(self):
        module_logger.info('Starting logging thread, log interval is %.1f s' % self.log_inter)

        if self.log_enable:
            self.c = csv.writer(open(time.strftime('%Y-%m-%d_%H%M') + '_lab_power.csv', 'wb'))
            self.c.writerow(['Date','Time','delta_ms','Voltage','Current'])
            
        t1_ms = int(round(time.time() * 1000))
        
        while self.is_running.is_set():
            time.sleep(self.log_inter)
            t2_ms = int(round(time.time() * 1000))
            dt = t2_ms - t1_ms
            t1_ms = t2_ms
            
            meas = self.get_volt_and_curr()

            if self.cb != None:
                self.cb(meas)

            if self.log_enable:
                self.c.writerow([meas.date, meas.time, dt, meas.volt, meas.curr])
        
        module_logger.info('Stopped logging thread')
          
    def stop(self):
        self.set_output_state(0)
        self.is_running.clear()
        if self.isAlive():
            self.join()
          
    def set_cb(self, cb):
        self.cb = cb

    def write_dev(self, str):
        self.mutex.acquire()
        if self.ser != None:
            self.ser.write(str + EOL)
        else:
            module_logger.warn('Serial connection not open')
        self.mutex.release()
    
    def write_and_read_dev(self, str):
        self.mutex.acquire()
        result = ""
        if self.ser != None:
            self.ser.write(str + EOL)
            result = self.ser.readline()[:-2]
        else:
            module_logger.warn('Serial connection not open')
        self.mutex.release()
        return result
    
    def get_volt_and_curr(self):
        answer = self.write_and_read_dev('MEAS:VOLT?;CURR?').split(';')
        try:
            return Measurement(time.strftime('%Y-%m-%d'), time.strftime('%H:%M:%S'), float(answer[0]), float(answer[1]))
        except ValueError:
            return Measurement(time.strftime('%Y-%m-%d'), time.strftime('%H:%M:%S'), 19.9, 4.9)

    # volt in volts and current in milliamperes
    def set_volt_and_curr(self, volt, curr):
        module_logger.info('set %.2f V, %u mA' % (volt, curr))
        self.write_dev('SOUR:VOLT %.3f; CURR %u MA' % (volt, curr))
        
    # enable or disable output
    def set_output_state(self, state):
        if state == 1:
            self.write_dev('OUTP:STAT 1')
        elif state == 0:
            self.write_dev('OUTP:STAT 0')
        else:
            module_logger.warn('set_output_state: incorrect state!')

    # get the output state
    def get_output_state(self):
        return self.write_and_read_dev("OUTP:STAT?")

    # set display mode, "normal" or "text"
    def set_display_mode(self, mode):
        mode = mode.upper()
        if not mode in ( 'NORM', 'TEXT' ):
            raise RuntimeError("Invalid mode %s, valid ones are NORM and TEXT" % mode)
        return self.write_dev("DISP:MODE " + mode)

    # write text to the display, display mode needs to be set beforehand
    def set_display_text(self, text):
        if len(text) > 14:
            raise RuntimeError("Max text length is 14 characters")
        if '"' in text and "'" in text:
            raise RuntimeError("Text may only contain either single or double quotes, not both")
        if '"' in text:
            return self.write_dev("DISP:TEXT '%s'" % text)
        return self.write_dev('DISP:TEXT "%s"' % text)

    def identify(self):
        """Returns the identification data, standard order is Manufacturer, Model no, Serial no (or 0), Firmware version"""
        return self.write_and_read_dev("*IDN?")

    def oscillate(self, n):
        self.set_volt_and_curr(15, 1000)
        for _ in xrange(n):
            self.set_output_state(1)
            self.set_output_state(0)

    def reset_device(self):
        self.write_dev('*RST' + EOL)

    def hiZ(self):
        # even setting the output off consumes -15 mA from battery.
        # This can go lower if we se the output voltage equal to battery voltage and current to 0
        self.set_output_state(0)
        time.sleep(0.2)
        meas = self.get_volt_and_curr()
        self.set_volt_and_curr(meas.volt, 0)
        self.set_output_state(1)


# reference http://www.elblinger-elektronik.de/pdf/panasonic_ion.pdf (page 12)
def charge_li_ion(pwr, battery, amount=None):
    PRECHARGE_C     = 20
    CHARGE_C        = 10
    CHRG_COMPLETE_C = 30
    
    precharge_rate = battery['capacity'] / PRECHARGE_C
    charge_rate = battery['capacity'] / CHARGE_C
    end_rate = battery['capacity'] / CHRG_COMPLETE_C
    
    loop_interval = 5
    
    charge_logger.info('starting')
    volt_t1 = 0
    volt_t2 = 0
    mah = 0
    old_mah = 0
    dvdt = 0
    
    pwr.hiZ()
    
    # wait while we can reliably measure the OCV. dvdt should be less than 1 mV/min
    charge_logger.info('wait until open-circuit voltage is stable (0.1 mV/min)')
    volt_t1 = pwr.get_volt_and_curr().volt
    while True:
        time.sleep(loop_interval)
        volt_t2 = pwr.get_volt_and_curr().volt
        dvdt = abs(volt_t1 - volt_t2)
        volt_t1 = volt_t2
        mv_per_min = 1000*dvdt * (60/loop_interval)
        charge_logger.info('%.2f V, %0.2f mV/min' % (volt_t2, mv_per_min))
        if mv_per_min < 0.1:
            charge_logger.info('open-circuit voltage is stable')
            break

    # check if the OCV = EOCV
    if volt_t2 > battery['EOCV'] - 0.002:
        return

    # start the charge timer
    t1 = time.time()
    t2 = 0
    t3 = 0
    
    while True:
        loop_start = time.time()
        meas = pwr.get_volt_and_curr()
        mah += 1000*meas.curr * loop_interval/3600
        
        if mah - old_mah > 25:
            charge_logger.info('%.2f V, %u mAh' % (meas.volt, mah))
            old_mah = mah

        if (time.time() - t1) > 15*60*60:
            charge_logger.info('end, over 15 hours total')
            break
        if meas.volt > battery['EOCV'] + 0.005:
            charge_logger.warn('end, overcharged')
            break
        if amount is not None and math.fabs(mah) > amount:
            discharge_logger.info('end, charged requested amount')
            break
  
        if meas.volt < battery['EODV']:
            if t3 == 0:
                charge_logger.info('precharging at %u mA (C/%u). voltage under EODV (%.2f < %.2f)' % (precharge_rate, PRECHARGE_C, meas.volt, battery['EODV']))
                pwr.set_volt_and_curr(battery['EOCV'], precharge_rate)
                t3 = time.time()
            elif (time.time() - t3) > 120*60:
                charge_logger.info('end, over 2 hours below EODV')
                break
        else:
            if t2 == 0:
                charge_logger.info('charging at %u mA (C/%u)' % (charge_rate, CHARGE_C))
                pwr.set_volt_and_curr(battery['EOCV'], charge_rate)
                t2 = time.time()
            elif (1000*meas.curr) < end_rate:
                charge_logger.info('end, charging current (%u mA) less than (C/%u)' % (1000*meas.curr, CHRG_COMPLETE_C))
                break

            if (time.time() - t2) > 12*60*60:
                charge_logger.info('end, over 12 hours charging')
                break
        
        # reduce sleep time by the amount processing took to increace mAh calculation accuracy (serial interface is sloow)
        time.sleep(loop_interval - (time.time() - loop_start))

    discharge_logger.info('ended in %u minutes. %.2f V, %.2f A, %i mAh' % ((time.time() - t1)/60, meas.volt, meas.curr, mah))
    pwr.hiZ()
    
    
def discharge_li_ion(pwr, battery, rate, amount=None):
    discharge_logger.info('starting')
    
    discharge_ma = battery['capacity'] / rate
    loop_interval = 5
    
    t1 = time.time()
    mah = 0
    old_mah = 0
    
    discharge_logger.info('discharging %u mA (C/%u)' % (discharge_ma, rate))
    pwr.set_volt_and_curr(1, discharge_ma)
    pwr.set_output_state(1)
    
    while True:
        loop_start = time.time()
        meas = pwr.get_volt_and_curr()
        mah -= 1000*meas.curr*10/3600
        
        if math.fabs(mah - old_mah) > 100:
            discharge_logger.info('%.2f V, %.2f A, %i mAh' % (meas.volt, meas.curr, mah))
            old_mah = mah
        if meas.volt < battery['EODV']:
            discharge_logger.info('end, voltage below EODV')
            break
        if amount is not None and math.fabs(mah) > amount:
            discharge_logger.info('end, discharged requested amount')
            break
        
        # reduce sleep time by the amount processing took to increace mAh calculation accuracy (serial interface is sloow)
        time.sleep(loop_interval - (time.time() - loop_start))
    
    discharge_logger.info('ended in %u minutes. %.2f V, %.2f A, %i mAh' % ((time.time() - t1)/60, meas.volt, meas.curr, mah))
    pwr.hiZ()
