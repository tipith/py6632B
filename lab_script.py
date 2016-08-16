#!/usr/bin/env python
import sys
import time
import logging
import py6632B


# Set the requested battery parameters here 
#  - EOCV = end of charge voltage
#  - EODV = end of discharge voltage
#  - capacity = suspected battery capacity
batteries = {
    'Generic Panasonic 18650': {'EOCV': 4.18, 'EODV': 3.0, 'capacity': 5000},
    'A123 Systems LiFePo4 25560': {'EOCV': 2*3.58, 'EODV': 2*2.0, 'capacity': 2500},
    'Samsung Mini S3': {'EOCV': 4.18, 'EODV': 3.1, 'capacity': 1600},
    'Solar Blaster': {'EOCV': 2*4.18, 'EODV': 2*3.1, 'capacity': 8000}
}


def setup_logging():
    format = logging.Formatter('%(asctime)s %(name)10s: %(message)s', datefmt="%Y-%m-%d %H:%M:%S")

    rootlog = logging.getLogger()
    rootlog.setLevel(logging.DEBUG)

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(format)
    rootlog.addHandler(ch)

    fh = logging.FileHandler('log.txt')
    fh.setFormatter(format)
    rootlog.addHandler(fh)


if __name__ == '__main__':
    setup_logging()

    pwr = py6632B.HP6632B('/dev/ttyUSB0', 1, True)
    pwr.daemon = True
    pwr.start()

    selected_battery = batteries['Solar Blaster']
    
    try:
        for discharge_rate in [2]:
            py6632B.charge_li_ion(pwr, selected_battery)
            time.sleep(600*60)
            #py6632B.discharge_li_ion(pwr, selected_battery, discharge_rate)
            #time.sleep(60*60)

        pwr.set_output_state(0)
    except KeyboardInterrupt:
        # CTRL-C ends the script
        pwr.stop()
