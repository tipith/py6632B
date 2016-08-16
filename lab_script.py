#!/usr/bin/env python

import time
import logging
import py6632B

if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s %(name)10s: %(message)s', level=logging.DEBUG)
    
    pwr = py6632B.HP6632B('/dev/ttyUSB0', 1, True)
    pwr.daemon = True
    pwr.start()
    
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
