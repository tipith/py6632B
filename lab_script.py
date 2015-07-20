#!/usr/bin/env python

import serial
import time
import csv
import collections
import io
import threading
import math
import logging

# Some inspiration taken from https://github.com/rambo/python-scpi/ for the display commands.

module_logger = logging.getLogger('HP6632B_module')

EOL = '\n'
Measurement = collections.namedtuple('Measurement', ['date', 'time', 'volt', 'curr'])

class HP6632B(threading.Thread):
    def __init__(self, comport, log_interval, log_enable):
        threading.Thread.__init__(self)
        
        self.logger = logging.getLogger('HP6632B')
        
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
            self.logger.error('Connection could not be opened')
            return

        self.reset_device()
        self.id = self.identify()
        
        if self.id.find('HEWLETT-PACKARD,6632B') >= 0:        
            self.logger.info('Connection established, found id ' + self.id + ", output is " + self.get_output_state())
            self.is_running.set()

            if log_interval >= 0.2:
                # it takes ~109 ms to query a measurement
                self.log_inter = log_interval - 0.109
            else:
                # limit logging speed to prevent deadlocks
                self.log_inter = 0.1
        else:
            self.logger.error('error: Connection established, no HP6632B found')
            return
            
    # This thread is responsible for writing to the log file
    def run(self):
        self.logger.info('Starting logging thread, log interval is ' + repr(self.log_inter) + ' s')

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
        
        self.logger.info('Stopped logging thread')
          
    def stop(self):
        self.logger.info('Stopping logging thread')
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
        self.mutex.release()
    
    def write_and_read_dev(self, str):
        self.mutex.acquire()
        result = ""
        if self.ser != None:
            self.ser.write(str + EOL)
            result = self.ser.readline()[:-2]
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
        self.logger.info('Setting voltage to ' + repr(volt) + ' and current to ' + repr(curr) )
        self.write_dev('SOUR:VOLT ' + repr(volt) + '; CURR ' + repr(curr) + ' MA')
        
    # enable or disable output
    def set_output_state(self, state):
        if state == 1:
            self.write_dev('OUTP:STAT 1')
        elif state == 0:
            self.write_dev('OUTP:STAT 0')
        else:
            self.logger.warn('set_output_state: incorrect state!')

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



# reference http://www.elblinger-elektronik.de/pdf/panasonic_ion.pdf (page 12)
def charge_li_ion(pwr, EOCV, EODV, C):
    precharge_C     = 10
    charge_C        = 1
    chrg_complete_C = 20
    
    module_logger.info('CHARGE: Starting the lithium-ion charge')
    volt_t1 = 0
    volt_t2 = 0
    mah = 0
    old_mah = 0
    dvdt = 0
    
    # Even setting the output off consumes -15 mA from battery.
    # As a workaround we set the EOCV voltage, 0 mA current and the output on.
    pwr.set_output_state(1)
    pwr.set_volt_and_curr(EOCV, 0)
    
    # wait while we can reliably measure the OCV. dvdt should be less than 1 mV/min
    volt_t1 = pwr.get_volt_and_curr().volt
    while True:
        time.sleep(10)
        volt_t2 = pwr.get_volt_and_curr().volt
        dvdt = abs(volt_t1 - volt_t2)
        volt_t1 = volt_t2
        module_logger.info('CHARGE: OCV = ' + repr(volt_t2) + ', change ' + repr(1000*6*dvdt) + ' mV/min')
        if (6*dvdt) < 0.0001:
            break

    # check if the OCV = EOCV
    if volt_t2 > EOCV - 0.002:
        return

    # start the charge timer
    t1 = time.time()
    t2 = 0
    t3 = 0
    
    while True:
        meas = pwr.get_volt_and_curr()
        mah += 1000*meas.curr*10/3600
        
        if mah - old_mah > 25:
            module_logger.info('CHARGE: mAh: ' + repr(mah))
            old_mah = mah
    
        if (time.time() - t1) > 720*60:
            module_logger.info('CHARGE: timeout error (over 720 min)')
            break
    
        if meas.volt > EOCV + 0.005:
            module_logger.warn('CHARGE: battery overcharged')
            break
  
        if meas.volt < EODV:
            if t3 == 0:
                pwr.set_volt_and_curr(EOCV, C/precharge_C)
                module_logger.info('CHARGE: battery voltage under EODV, charging at ' + repr(C/precharge_C) + ' mA (C/' + repr(precharge_C) + ')')
                t3 = time.time()
            if (time.time() - t2) > 120*60:
                module_logger.info('CHARGE: timeout error (over 120 min EODV)')
                break
        else:
            if t2 == 0:
                pwr.set_volt_and_curr(EOCV, C/charge_C)
                module_logger.info('CHARGE: battery voltage over EODV, charging at ' + repr(C/charge_C) + ' mA (C/' + repr(charge_C) + ')')
                t2 = time.time()

            # keep the charging at least 60 min even if the charge current is below end condition
            if ((time.time() - t2) > (60*60)) and (meas.curr < (C/chrg_complete_C)):
                module_logger.info('CHARGE: charging current less than ' + repr(meas.curr) + ' (C/' + repr(chrg_complete_C) + '), ending charge')
                break
        
        time.sleep(10)

    module_logger.info('CHARGE: Battery charge ended in ' + repr((time.time() - t1)/60) + ' minutes')
    pwr.set_output_state(0)
    
    
    
def discharge_li_ion(pwr, EODV, C, rate):
    module_logger.info('DISCHARGE: Starting the lithium-ion discharge ')
    
    t1 = time.time()
    mah = 0
    old_mah = 0
    
    module_logger.info('DISCHARGE: setting discharge current to ' + repr(C/rate) + ' mA (C/' + repr(rate) +')')
    pwr.set_volt_and_curr(1, C/rate)
    pwr.set_output_state(1)
    
    while True:
        meas = pwr.get_volt_and_curr()
        mah -= 1000*meas.curr*10/3600
        if math.fabs(mah - old_mah) > 100:
            module_logger.info('DISCHARGE: ' + repr(meas.volt) + ' V, ' + repr(meas.curr) + ' A, ' + repr(mah) + ' mAh')
            old_mah = mah
        if meas.volt < EODV:
            module_logger.info('DISCHARGE: end of discharge in ' + repr((time.time() - t1)/60) + ' minutes')
            break
        time.sleep(10)
    
    pwr.set_output_state(0)



def set_hiz_output(pwr, EOCV):
    # even setting the output off consumes -15 mA from battery.
    # This can go lower if we se the voltage to battery EOCV and current to 0
    pwr.set_output_state(1)
    pwr.set_volt_and_curr(EOCV, 0)
    
if __name__ == '__main__':
    # Generate the lab power supply object. This will start logging at the speed specified
    pwr = HP6632B('/dev/ttyUSB0', 1)
    pwr.daemon = True
    pwr.start()
    
    time.sleep(2)

    # Set the requested battery parameters here 
    #  - EOCV = end of charge voltage
    #  - EODV = end of discharge voltage
    #  - suspected battery capacity
    
    # lithium ion (based on Panasonic 18650: charge at 4.2 V / C/5 A / 120 min )
    #EOCV = 4.18
    #EODV = 3.0
    #capacity = 5000
    
    # lifepo (A123 systems 25560: charge at 3.6 V / 1*C A / 60 min )
    # The used pack is 2 series
    # http://info.a123systems.com/Portals/133376/content/data%20sheets/a123%20datasheet_26650m1b.pdf
    #EOCV = 2*3.58
    #EODV = 2*2
    #capacity = 2500
    
    # samsung s3 mini battery test
    EOCV = 4.18
    EODV = 3.1
    capacity = 1600

    try:
        for discharge_rate in [2]:
            # let things settle before a cycle is started
            set_hiz_output(pwr,EOCV)
            time.sleep(5*60)
		 
            # start the charging
            charge_li_ion(pwr, EOCV, EODV, capacity)
            
            # let thing settle again, it takes quite a long time for the OCV to settle
            set_hiz_output(pwr,EOCV)
            time.sleep(30*60)

            # discharge at the requested rate until EODV is reached
            discharge_li_ion(pwr, EODV, capacity, discharge_rate)

            # let things settle for an hour before new cycle is started
            set_hiz_output(pwr,EODV)
            time.sleep(60*60)

        pwr.set_output_state(0)
    except KeyboardInterrupt:
        # CTRL-C ends the script
        pwr.stop()
