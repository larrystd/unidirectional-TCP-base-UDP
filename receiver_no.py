"""
    Sample code for Receiver
    Python 3
    Usage: python3 receiver.py receiver_port sender_port FileReceived.txt flp rlp
    coding: utf-8

    Notes:
        Try to run the server first with the command:
            python3 receiver_template.py 9000 10000 FileReceived.txt 1 1
        Then run the sender:
            python3 sender_template.py 11000 9000 FileToReceived.txt 1000 1

    Author: Rui Li (Tutor for COMP3331/9331)
"""
# here are the libs you may find it useful:
import datetime, time  # to calculate the time delta of packet transmission
import logging, sys  # to write the log
import socket  # Core lib, to send packet via UDP socket
from threading import Thread  # (Optional)threading will make the timer easily implemented
import random  # for flp and rlp function
import threading

from util import *

BUFFERSIZE = 1024

seg_type_to_name = {
    0: 'DATA',
    1: 'ACK',
    2: 'SYN',
    3: 'FIN',
    4: 'RESET'
}

class Receiver:
    def __init__(self, receiver_port: int, sender_port: int, filename: str, flp: float, rlp: float) -> None:
        '''
        The server will be able to receive the file from the sender via UDP
        :param receiver_port: the UDP port number to be used by the receiver to receive PTP segments from the sender.
        :param sender_port: the UDP port number to be used by the sender to send PTP segments to the receiver.
        :param filename: the name of the text file into which the text sent by the sender should be stored
        :param flp: forward loss probability, which is the probability that any segment in the forward direction (Data, FIN, SYN) is lost.
        :param rlp: reverse loss probability, which is the probability of a segment in the reverse direction (i.e., ACKs) being lost.
        '''
        self.address = "127.0.0.1"  # change it to 0.0.0.0 or public ipv4 address if want to test it between different computers
        self.receiver_port = int(receiver_port)
        self.sender_port = int(sender_port)
        self.server_address = (self.address, self.receiver_port)
        self.store_file = filename
        self.client_address = ""
        self.seq_data = {}
        self.want_seq = 0
        self.data_start_seq = -1
        self.max_win = 1<<14  # 16k
        self.flp = flp
        self.rlp = rlp
        self.t_start = 0
        self.state = State.NONE

        self.logger = logging.getLogger()
        self.logger.setLevel(logging.INFO)
        ch = logging.StreamHandler()
        ch = logging.FileHandler('Receiver_log.txt', 'w+')
        ch.setLevel(logging.INFO)
        # add ch to logger
        self.logger.addHandler(ch)
        # init the UDP socket
        # define socket for the server side and bind address
        print(f"The sender is using the address {self.server_address} to receive message!")
        self.receiver_socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        self.receiver_socket.bind(self.server_address)
        self.receiver_socket.settimeout(2)
    
    def run(self) -> None:
        '''
        This function contain the main logic of the receiver
        '''
        while self.state != State.END:
            # try to receive any incoming message from the sender
            try:
                incoming_message, sender_address = self.receiver_socket.recvfrom(BUFFERSIZE)
            except:
                continue
            if len(incoming_message) == 4:  # SYN FIN RESET
                type, seq = struct.unpack('HH', incoming_message)
                # forward segment loss
                if random.random() <= self.flp:
                    if self.t_start == 0:  # SYN loss
                        self.t_start = get_current_time()
                        t_inv = 0
                    else:
                        t_inv = round(get_current_time() - self.t_start, 2)
                    self.logger.info(f'drp  {t_inv:<10}  {seg_type_to_name[type]}  {seq:<6}  {0:<6}')
                    continue
                if type == Type.SYN.value:
                    self.client_address = sender_address
                    if self.t_start == 0:
                        self.t_start = get_current_time()
                        t_inv = 0
                    else:
                        t_inv = round(get_current_time() - self.t_start, 2)
                    self.logger.info(f'rev  {t_inv:<10}  SYN  {seq:<6}  {0:<6}')
                    print (f"client{sender_address} send syn message, seq: {seq}")
                    self.data_start_seq = seq + 1
                    self.want_seq = seq + 1
                    self.reply_ack(self.want_seq)
                    self.state = State.CONNECT
                
                if type == Type.FIN.value:
                    t_inv = round(get_current_time() - self.t_start, 2)
                    self.logger.info(f'rev  {t_inv:<10}  FIN  {seq:<6}  {0:<6}')
                    print (f"client{sender_address} send fin message, seq: {seq}")
                    self.write_file()
                    self.want_seq = seq + 1
                    self.reply_ack(self.want_seq)
                    self.state = State.CLOSE
                    
                    time_wait_thread = threading.Thread(target=self.time_wait)
                    time_wait_thread.start()
                    
                if type == Type.RESET.value:
                    t_inv = round(get_current_time() - self.t_start, 2)
                    self.logger.info(f'rev  {t_inv:<10}  RST  {seq:<6}  {0:<6}')
                    self.state = State.END
            else:  # data loss
                type, seq = struct.unpack('HH', incoming_message[0:4])
                data = incoming_message[4:]
                if random.random() <= self.flp:
                    t_inv = round(get_current_time() - self.t_start, 2)
                    self.logger.info(f'drp  {t_inv:<10}  {seg_type_to_name[type]} {seq:<6}  {len(data):<6}')
                    continue
                if type == Type.DATA.value:
                    t_inv = round(get_current_time() - self.t_start, 2)
                    self.logger.info(f'rev  {t_inv:<10}  DATA {seq:<6}  {len(data):<6}')
                    self.seq_data[seq] = data
                    
                    if self.want_seq == seq:
                        want_seq = (seq+len(data)) % (1<<16)
                        while want_seq in self.seq_data:
                            want_seq += len(self.seq_data[want_seq])
                            want_seq = want_seq % (1<<16)
                        self.want_seq = want_seq
                    self.reply_ack(self.want_seq)
                    self.state = State.DATA_TRANS

    def reply_ack(self, seq):
        # reverse segment loss 
        if random.random() <= self.rlp:
            t_inv = round(get_current_time() - self.t_start, 2)
            self.logger.info(f'drp  {t_inv:<10}  ACK  {seq:<6}  {0:<6}')
            return
        ack_seg = build_segment_header(Type.ACK, seq)
        self.receiver_socket.sendto(ack_seg, self.client_address)
        
        t_inv = round(get_current_time() - self.t_start, 2)
        self.logger.info(f'snd  {t_inv:<10}  ACK  {self.want_seq:<6}  {0:<6}')
        
    def write_file(self):
        with open(self.store_file, "w+") as file:
            seq = self.data_start_seq
            while seq in self.seq_data:
                file.write(str(self.seq_data[seq], 'utf-8'))
                seq += len(self.seq_data[seq])
                seq %= 1<<16
                
        file.close()
        
    def time_wait(self):
        time.sleep(2)   # wait two second
        self.state = State.END


if __name__ == '__main__':
    # logging is useful for the log part: https://docs.python.org/3/library/logging.html
    logging.basicConfig(
        # filename="Receiver_log.txt",
        stream=sys.stderr,
        level=logging.DEBUG,
        format='%(asctime)s,%(msecs)03d %(levelname)-8s %(message)s',
        datefmt='%Y-%m-%d:%H:%M:%S')

    if len(sys.argv) != 6:
        print(
            "\n===== Error usage, python3 receiver.py receiver_port sender_port FileReceived.txt flp rlp ======\n")
        exit(0)

    receiver = Receiver(*sys.argv[1:])
    receiver.run()
