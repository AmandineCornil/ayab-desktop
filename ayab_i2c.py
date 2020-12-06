import sys
import time

sys.path.append('./src/main/python')

import ayab.plugins.ayab_plugin.ayab_communication as comm

port = '/dev/ttyACM0'

REPI2CREAD_MSG = 0x21

MCP23008_REGISTER = {
    0x00 : 'IODIR',
    0x01 : 'IPOL',
    0x02 : 'GPINTEN',
    0x03 : 'DEFVAL',
    0x04 : 'INTCON',
    0x05 : 'IOCON',
    0x06 : 'GPPU',
    0x07 : 'INTF',
    0x08 : 'INTCAP',
    0x09 : 'GPIO',
    0x0a : 'OLAT',
}

shield = comm.AyabCommunication()
shield.open_serial(port)
# Wait for Arduino reset (consequence of serail open)
time.sleep(1)

def mcp23008_set(i2c_address, command, value):
    shield.req_i2c_write(i2c_address,command, value)

def mcp23008_dump(i2c_address=0x20, address=None):
    for command, name in MCP23008_REGISTER.items():
        if not address or address == command:
            shield.req_i2c_read(i2c_address,command)
            result = shield.update()
            if result[0] == REPI2CREAD_MSG:
                print(f"%7s[0x%02x] = 0x%02x" % (name, command, result[1]))
            else:
                printf("Expected msg 0x%02x (got 0x%02x)" % (REPI2CREAD_MSG, result[0]))

#shield.close_serial()


