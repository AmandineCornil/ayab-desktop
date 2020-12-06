#!/bin/bash

cd "`dirname $0`"
source venv/bin/activate

cd src/main/python

python << EOF
import time
import ayab.plugins.ayab_plugin.ayab_communication as comm

MSG_INDSTATE = 0x84

port = '/dev/ttyACM0'

def handle_indState_msg(msg):
    hall_l = int((msg[2] << 8) + msg[3])
    hall_r = int((msg[4] << 8) + msg[5])

    carriage_type = '?'
    if msg[6] == 1:
        carriage_type = 'K'
    elif msg[6] == 2:
        carriage_type = 'L'
    elif msg[6] == 3:
        carriage_type = 'G'

    carriage_position = int(msg[7])

    if msg[8] == 1:
        direction = "Left"
    elif msg[8] == 2:
        direction = "Right"
    else:
        direction = "Unknown"

    if msg[9] == 1:
        hallactive = "Left"
    elif msg[9] == 2:
        hallactive = "Right"
    else:
        hallactive = "Unknown"

    if msg[10] == 1:
        beltshift = "Regular"
    elif msg[10] == 2:
        beltshift = "Shifted"
    elif msg[10] == 3:
        beltshift = "Lace Regular"
    elif msg[10] == 4:
        beltshift = "Lace Shifted"
    else:
        beltshift = "Unknown"

    startNeedle = msg[11]
    stopNeedle = msg[12]
    solenoid8_15 = msg[13]
    solenoid0_7 = msg[14]

    print("Carriage (%c), Hall (%3d%c , %3d%c), Belt:%-12s" %
        (
            carriage_type,
            hall_l,
            '*' if hallactive == "Left" else ' ',
            hall_r,
            '*' if hallactive == "Right" else ' ',
            beltshift
        )
    )
    print("Position:%3d (%-7s), Start-StopNeedle:%03d-%03d, Solenoids:%s %s" % 
        (
            carriage_position,
            direction,
            startNeedle,
            stopNeedle,
            bin(256+solenoid0_7)[3:],
            bin(256+solenoid8_15)[3:],
        )
    )


shield = comm.AyabCommunication()
shield.open_serial(port)
time.sleep(1)
shield.req_test()

try:
    while True:
        msg = shield.update()
        if msg and (msg[0] == MSG_INDSTATE):
            handle_indState_msg(msg)
except KeyboardInterrupt:
    pass
finally:
    shield.close_serial()

EOF
