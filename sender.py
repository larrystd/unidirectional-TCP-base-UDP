"""
    Sample code for Sender (multi-threading)
    Python 3
    Usage: python3 sender.py receiver_port sender_port FileToSend.txt max_recv_win rto
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
import threading
import os

from util import *

BUFFERSIZE = 1024


class Sender:
    # def __init__(self, sender_port: int, receiver_port: int, filename: str, max_win: int, rot: int) -> None:
    def __init__(self, sender_port = 10001, receiver_port= 10002, filename= 'asyoulik.txt', max_win= 3000, rot= 300) -> None:
        '''
        The Sender will be able to connect the Receiver via UDP
        :param sender_port: the UDP port number to be used by the sender to send PTP segments to the receiver
        :param receiver_port: the UDP port number on which receiver is expecting to receive PTP segments from the sender
        :param filename: the name of the text file that must be transferred from sender to receiver using your reliable transport protocol.
        :param max_win: the maximum window size in bytes for the sender window.
        :param rot: the value of the retransmission timer in milliseconds. This should be an unsigned integer.
        '''
        self.sender_port = int(sender_port)
        self.receiver_port = int(receiver_port)
        self.sender_address = ("127.0.0.1", self.sender_port)
        self.receiver_address = ("127.0.0.1", self.receiver_port)
        self.state = State.NONE
        self.rot = rot
        self.bufsize = 1024
        self.max_data_size = 1000
        self.file_path = filename
        self.file_size = -1
        self.max_win = max_win
        self.send_seg_list = []  # send seg list
        self.send_time_list = []  # every segment's sending time list
        self.win_size = -1  # current slide window size
        self.init_seq = -1
        self.data_seq = -1
        self.fin_seq = -1
        self.waiting_time = 0.01
        self.retransmiss_id_list = []  # retransmiss segment id list
        self.data_seq_to_id = {}
        self.data_id_to_seq = {}
        self.cond = threading.Condition()  # lock and condition variable
        
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.INFO)
        ch = logging.StreamHandler()
        ch = logging.FileHandler('Sender_log.txt', 'w+')
        ch.setLevel(logging.INFO)
        # add ch to logger
        self.logger.addHandler(ch)

        # init the UDP socket
        print (f"The sender is using the address {self.sender_address}")
        self.sender_socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        self.sender_socket.bind(self.sender_address)
        self.sender_socket.settimeout(self.rot/1000)
        
        self._is_active = True  # for the multi-threading
        listen_thread = threading.Thread(target=self.listen)
        listen_thread.start()

    def connect(self):
        '''connect with receiver with SYN segment
        '''
        self.state = State.CONNECT
        self.init_seq = generate_random_int(0, (1<<16)-1)
        # self.init_seq = 63443
        syn_seg = build_segment_header(Type.SYN, self.init_seq)
        # If SYN transfer times > 3, then send RESET
        trans_syn_times = 1
        with self.cond:
            self.t_start = get_current_time()
            while self.state == State.CONNECT:
                t_inv = round(get_current_time() - self.t_start, 2)
                self.sender_socket.sendto(syn_seg, self.receiver_address)
                if trans_syn_times == 1:
                    self.logger.info(f'snd  {0:<10}  SYN  {self.init_seq:<6}  {0:<6}')
                else:
                    self.logger.info(f'snd  {t_inv:<10}  SYN  {self.init_seq:<6}  {0:<6}')
                self.cond.wait()  # wait for ack result
                
                if self.state == State.READ_FILE:  # connect success
                    break
                # send RESET
                if trans_syn_times == 3:
                    rst_seg = build_segment_header(Type.RESET, 0)
                    t_inv = round(get_current_time() - self.t_start, 2)
                    self.sender_socket.sendto(rst_seg, self.receiver_address)
                    self.logger.info(f'snd  {t_inv:<10}  RST  {0:<6}  {0:<6}')
                    self.state = State.END
                    self._is_active = False
                    return
                    
                trans_syn_times += 1
                
    def listen(self):
        '''(Multithread is used)listen the response from receiver'''
        logging.debug("Sub-thread for listening is running")
        while self._is_active:
            if self.state == State.CONNECT:
                self.reply_connect()
            elif self.state == State.READ_FILE:
                with self.cond:
                    self.cond.wait()  # wait for data transfer
            elif self.state == State.DATA_TRANS:
                self.reply_data_trans()
            elif self.state == State.CLOSE:
                self.reply_close()
    
    def reply_connect(self):
        while self.state == State.CONNECT:
            try:
                ack_seg, _ = self.sender_socket.recvfrom(self.bufsize)
            except:
                with self.cond:
                    self.cond.notify_all()  # notify main-thread to resend syn
            else:
                type, seq = struct.unpack('HH', ack_seg)
                assert type == Type.ACK.value
                t_inv = round(get_current_time() - self.t_start, 2)
                self.logger.info(f'rcv  {t_inv:<10}  ACK  {seq:<6}  {len(ack_seg)-4:<6}')
                self.data_seq = seq
                with self.cond:
                    self.state = State.READ_FILE
                    self.cond.notify_all()  # notify main-thread to read file and send data
        
    def reply_close(self):
        while self.state == State.CLOSE:
            try:
                ack_seg, _ = self.sender_socket.recvfrom(self.bufsize)
            except:
                with self.cond:
                    self.cond.notify_all()  # notify main-thread to resend fin
            else:
                type, seq = struct.unpack('HH', ack_seg)
                assert type == Type.ACK.value
                t_inv = round(get_current_time() - self.t_start, 2)
                self.logger.info(f'rcv  {t_inv:<10}  ACK  {seq:<6}  {len(ack_seg)-4:<6}')
                with self.cond:
                    self.state = State.END
                    self._is_active = False  # finish sub-thread
                    self.cond.notifyAll()  # notify main-thread
    
    def reply_data_trans(self):
        may_retrans_seq = (self.init_seq + 1) % (1<<16)
        redundancy_times = 0
        
        while self.state == State.DATA_TRANS:
            try:
                ack_seg, addr = self.sender_socket.recvfrom(self.bufsize)
            except:
                # out of time, retrans the latter segment
                seq_id = self.data_seq_to_id[may_retrans_seq]
                with self.cond:
                    self.retransmiss_id_list.append(seq_id)
                    self.cond.notify_all()
            else:
                # receive ack seg in time
                type, seq = struct.unpack('HH', ack_seg)
                t_inv = round(get_current_time() - self.t_start, 2)
                self.logger.info(f'rcv  {t_inv:<10}  ACK  {seq:<6}  {len(ack_seg)-4:<6}')
                # end data_trans
                if seq == self.data_seq:  
                    with self.cond:
                        self.state = State.CLOSE
                        self.cond.notifyAll()
                    break
                    
                # compute redundancy ack times
                if seq != may_retrans_seq:
                    ack_size = seq - may_retrans_seq
                    if ack_size < 0:
                        ack_size += 1<<16
                    may_retrans_seq = seq
                    redundancy_times = 1
                    # foward slide window
                    with self.cond:
                        self.win_size -= ack_size
                        for id in self.retransmiss_id_list:
                            if self.data_id_to_seq[id] < seq:
                                self.retransmiss_id_list.remove(id)  # move unneeded retransmiss segment
                            if seq < self.init_seq and self.data_id_to_seq[id] > self.init_seq:
                                self.retransmiss_id_list.remove(id)
                        self.cond.notifyAll()
                elif seq == may_retrans_seq:
                    redundancy_times += 1
                if redundancy_times == 3:  # three redundany ack
                    with self.cond:
                        self.retransmiss_id_list.append(self.data_seq_to_id[seq])
                        self.cond.notifyAll()
                    redundancy_times = 0
        
    def send_data(self):
        # Wait sub-thread receives SYN ACK
        with self.cond:
            while self.state != State.READ_FILE:
                self.cond.wait()
        self.readfile()
        with self.cond:
            self.state = State.DATA_TRANS
            self.cond.notify_all()
        
        send_id = 0
        while self.state == State.DATA_TRANS:
            # no need consider slide window for retransmiss segment part
            for retrans_id in self.retransmiss_id_list:  # retrasmiss segment
                seg = self.send_seg_list[retrans_id]
                self.sender_socket.sendto(seg, self.receiver_address)
                
                t_inv = round(get_current_time() - self.t_start, 2)
                self.logger.info(f'snd  {t_inv:<10}  DATA {self.data_id_to_seq[retrans_id]:<6}  {len(seg)-4:<6}')
                self.retransmiss_id_list.remove(retrans_id)
                
            if send_id < len(self.send_seg_list):  # send segment
                seg = self.send_seg_list[send_id]
                with self.cond:
                    if self.win_size + len(seg) - 4 > self.max_win:  # wait for slide window space
                        self.cond.wait()  
                if len(self.retransmiss_id_list) > 0:
                    continue  # go to retransmiss
                self.sender_socket.sendto(seg, self.receiver_address)
                self.send_time_list.append(get_current_time())
                t_inv = round(get_current_time() - self.t_start, 2)
                self.logger.info(f'snd  {t_inv:<10}  DATA {self.data_id_to_seq[send_id]:<6}  {len(seg)-4:<6}')
                send_id += 1
                self.win_size += len(seg) - 4

        print ("Finish sending the file.")
        
    def readfile(self):
        '''read file to send_seg_list, main thread executes
        '''
        print (f"Now begin to read the file: {self.file_path}.")
        file_offset = 0
        with open(self.file_path, 'rb') as file:
            info = os.lstat(self.file_path)
            self.file_size = info.st_size
            stream = file.read()
            while True:
                if (file_offset + self.max_data_size <= self.file_size):
                    # cur_win_size = min(self.max_win - self.win_size, self.max_data_size)
                    seg_size = self.max_data_size
                else:
                    # cur_win_size = min(self.max_win - self.win_size, fileSize - self.file_offset)
                    seg_size = self.file_size - file_offset
                if seg_size == 0:
                    break
                
                data = bytes(stream[file_offset:file_offset+seg_size])
                file_offset += seg_size
                    
                data_seg = build_segment_header(Type.DATA, self.data_seq) + data   
                # set send_seg_list, data_id_to_seq, data_seq_to_id                      
                self.send_seg_list.append(data_seg)
                self.data_seq_to_id[self.data_seq] = len(self.send_seg_list) - 1
                self.data_id_to_seq[len(self.send_seg_list) - 1] = self.data_seq
                self.data_seq += len(data)
                self.data_seq %= 1<<16
            
            print ("READFILE completed.")
        file.close()
        
    def close(self):
        self.cond.acquire()
        while self.state != State.CLOSE:
            self.cond.wait()
        self.fin_seq = self.data_seq
        fin_seg = build_segment_header(Type.FIN, self.fin_seq)
        while self.state == State.CLOSE:
            self.sender_socket.sendto(fin_seg, self.receiver_address)
            t_inv = round(get_current_time() - self.t_start, 2)
            self.logger.info(f'snd  {t_inv:<10}  FIN  {self.fin_seq:<6}  {0:<6}')
            
            with self.cond:
                self.cond.wait()

    def run(self):
        '''
        This function contain the main logic of the receiver
        '''
        
        # connected
        self.connect()
        if self.state == State.END:  # not make a connect
            return
        self.send_data()
        self.close()

if __name__ == '__main__':
    # logging is useful for the log part: https://docs.python.org/3/library/logging.html
    logging.basicConfig(
        # filename="Sender_log.txt",
        stream=sys.stderr,
        level=logging.DEBUG,
        format='%(asctime)s,%(msecs)03d %(levelname)-8s %(message)s',
        datefmt='%Y-%m-%d:%H:%M:%S')
    
    #if len(sys.argv) != 6:
    #    print(
    #        "\n===== Error usage, python3 sender.py sender_port receiver_port FileReceived.txt max_win rot ======\n")
    #    exit(0)

    sender = Sender(*sys.argv[1:])
    sender.run()
