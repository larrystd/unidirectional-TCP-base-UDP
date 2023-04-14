from enum import Enum
import struct
import random
import time

# random.seed(10)

class Type(Enum):
    DATA = 0
    ACK = 1
    SYN = 2
    FIN = 3
    RESET = 4
    
class State(Enum):
    NONE = 0
    CONNECT = 1
    READ_FILE = 2
    DATA_TRANS = 3
    CLOSE = 4
    END = 5
    
def build_segment_header(type: Type, seq: int):
    # for DATA SEQ FIN RESET
    header = struct.pack('HH', type.value, seq)
    return header

def generate_random_int(left: int, right: int):
    return random.randint(left, right)

def get_current_time():
    return time.time() * 1000

def normal_seq(seq: int):
    if seq >= (1<<16):
        return seq - (1<<16)
    return seq
