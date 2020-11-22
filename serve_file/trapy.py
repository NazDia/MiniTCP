import socket
import threading
import time
from utils import *
import logging
import os


logger = logging.getLogger('serve-file')


class Admin:
    def __init__(self):
        self.mutex = threading.Lock()
        self.binded = []
        self.net_fd = [] # The current user goes first



class Sender_Receiver:
    def __init__(self):
        self.conns = []
        self.sender = threading.Thread(target=self.send, args=[])
        self.rcv = threading.Thread(target=self.receive, args=[])
        self.dic = {}
        self.rlist = []
        self.wlist = []
        self.check = threading.main_thread()
        self.my_mutex = threading.Lock()
        self.sender.start()
        self.rcv.start()


    def add_conn(self, conn):
        self.my_mutex.acquire()
        self.dic[conn.send_socket] = conn
        self.dic[conn.rcv_socket] = conn
        self.rlist.append(conn.rcv_socket)
        self.wlist.append(conn.send_socket)
        self.conns.append(conn)
        self.my_mutex.release()


    def send(self):
        while self.check.is_alive():
            self.my_mutex.acquire()
            ready = socket.selectors.select.select([], self.wlist,[], 0.05)
            self.my_mutex.release()
            for i in ready[1]:
                self.my_mutex.acquire()
                conn = self.dic[i]
                self.my_mutex.release()
                conn.mutex.acquire()
                if conn.resetted:
                    conn.mutex.release()
                    continue
                prev = conn.send_buff_current
                change = False
                to_increase = 0
                for j in range(conn.send_buff_current, min(conn.send_buff_current + conn.window_size, len(conn.send_buff))):
                    current = conn.send_buff[j]
                    if conn.ack_rcvd == conn.send_buff[j][1]:
                        change = True
                        prev = j
                    elif conn.ack_rcvd > conn.send_buff[j][1]:
                        Sample_RRT = time.perf_counter() - conn.send_buff[j][3]
                        conn.timer_setting = 0.875 * conn.timer_setting + 0.125 * (Sample_RRT)
                        conn.timer_diff = 0.75 * conn.timer_diff + 0.25 * abs(Sample_RRT - conn.timer_setting)
                        to_increase += 1
                if not change and conn.send_buff_current < len(conn.send_buff):
                    conn.send_buff_current = min(conn.send_buff_current + conn.window_size, len(conn.send_buff))
                    conn.window_size_increase(conn.window_size)
                else:
                    conn.send_buff_current = prev
                    conn.window_size_increase(to_increase)
                to_decrease = 0
                for j in range(conn.send_buff_current, min(conn.send_buff_current + conn.window_size, len(conn.send_buff))):
                    if conn.send_buff[j][4] == 0:
                        i.sendto(conn.send_buff[j][0], (conn.ext_ip, 0))
                        temp = conn.send_buff[j]
                        conn.send_buff[j] = (temp[0], temp[1], time.perf_counter() + min(conn.timer_setting + conn.timer_diff, 3), time.perf_counter(), 1)
                    elif conn.send_buff[j][2] < time.perf_counter() and not conn.send_socket is None:    
                        to_decrease += 1
                        i.sendto(conn.send_buff[j][0], (conn.ext_ip, 0))
                        temp = conn.send_buff[j]
                        conn.send_buff[j] = (temp[0], temp[1], time.perf_counter() + min(conn.timer_setting + conn.timer_diff, 3), temp[3], temp[4] + 1)
                conn.window_size_decrease(to_decrease)
                conn.mutex.release()
        

    def receive(self):
        while self.check.is_alive():
            self.my_mutex.acquire()
            ready = socket.selectors.select.select(self.rlist, [], [], 0.05)
            self.my_mutex.release()
            for i in ready[0]:
                self.my_mutex.acquire()
                conn = self.dic[i]
                self.my_mutex.release()
                conn.mutex.acquire()
                if conn.resetted:
                    continue
                data, addr = i.recvfrom(conn.to_receive)
                conn.mutex.release()
                conn.update_upon_receive(data, addr)

    

class Conn:
    def __init__(self):
        self.send_socket = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW)
        self.rcv_socket = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_TCP)
        self.resetted = False
        self.is_host = False
        self.is_client = False
        self.closing = False
        self.rcv_closing = False
        self.seq_no_to_send = 0
        self.ack_to_send = 0
        self.seq_no_rcvd = 0
        self.ack_rcvd = 0
        self.send_buff = []
        self.send_buff_current = 0
        self.timer_setting = 1
        self.timer_diff = 0
        self.to_receive = 65535
        self.window_size = 4
        self.acked = True
        self.rcv_syn = False
        self.rcv_synack = False
        self.rcvd_current = 0
        self.rcv_buffer = []
        self.mutex = threading.Lock()


    def __str__(self):
        out = 'Host\n' if self.is_host else 'Not a host\n'
        out += 'Seq no to send : ' + str(self.seq_no_to_send)
        out += 'Ack no to send : ' + str(self.ack_to_send)
        out += 'Ack received : ' + str(self.ack_rcvd)
        out += 'Send buffer : ' + str(self.send_buff)
        out += 'Buffer current : ' + str(self.send_buff_current)
        out += 'My addres : ' + str((self.my_ip, self.my_port))
        return out


    def listen(self, num):
        if self.is_client:
            raise ConnException('A client can\'t listen')
        if self.is_host:
            raise ConnException('Listen is already set in this connection')
        self._listen = num
        self.is_host = True


    def bind(self, address):
        global admin
        if address in admin.binded:
            raise ConnException('Address is being used')
        return self.inner_bind(address)

    
    def inner_bind(self, address):
        self.my_ip, self.my_port = address
        admin.binded.append(address)
        self.resetted = False


    def reset(self):
        self.mutex.acquire()
        self.is_host = False
        self.is_client = False
        self.send_socket = None
        self.rcv_socket = None
        self.rcv_syn = False
        self.rcv_synack = False
        self.rcvd_current = 0
        self.rcv_buffer = []
        self._listen = 0
        self.ack_to_send = 0
        self.ack_rcvd = 0
        self.my_ip = ''
        self.my_port = 0
        self.ext_ip = ''
        self.ext_port = 0
        self.seq_no_to_send = 0
        self.seq_no_rcvd = 0
        self.timer_setting = 1
        self.timer_diff = 0
        self.to_receive = 65535
        self.send_buff = []
        self.send_buff_current = 0
        self.resetted = True
        self.acked = False
        self.mutex.release()


    def window_size_increase(self, n):
        self.window_size += n

    
    def window_size_decrease(self, n):
        self.window_size -= n
        if self.window_size < 4:
            self.window_size = 4


    def send(self, data):
        self.mutex.acquire()
        splitted = divide_packet(data)
        for i in splitted:
            flags = create_flags(ACK=True)
            self.acked = True
            packet = create_pack(self.my_ip, self.ext_ip
            , 40 + len(i)
            , self.my_port, self.ext_port, flags
            , self.seq_no_to_send, self.ack_to_send, body=i)
            self.send_buff.append((packet, self.seq_no_to_send
            , 0, 0, 0))
            self.seq_no_to_send = (len(i) + self.seq_no_to_send) % 2 ** 32
        self.mutex.release()
        return len(packet)


    def receive(self, lenght):
        global admin
        global sender
        self.mutex.acquire()
        prev = self.to_receive
        self.to_receive = lenght + 40
        self.mutex.release()
        if not self.acked and not self.closing:
            self.mutex.acquire()
            flags = create_flags(ACK=True)
            pack = create_pack(self.my_ip, self.ext_ip, 40
            , self.my_port, self.ext_port, flags, self.seq_no_to_send, self.ack_to_send)
            self.send_buff.append((pack, self.seq_no_to_send
            , 0, 0, 0))
            self.mutex.release()
        while True:
            self.mutex.acquire()
            if self.rcv_closing and not self.closing:
                self.mutex.release()
                self.close_rcvd()
                while self.send_buff_current != len(self.send_buff):
                    pass
                admin.net_fd.remove(((self.my_ip, self.my_port), (self.ext_ip, self.ext_port)))
                sender.conns.remove(self)
                self.reset()
                return b''
            try:
                ret = self.rcv_buffer[self.rcvd_current]
                self.rcvd_current += 1
                self.to_receive = prev
                self.mutex.release()
                return ret
            except:
                self.mutex.release()


    def update_upon_receive(self, data, sender_addr):
        global admin
        analisis = analize_header(data)
        if analisis is None:
            return
        try:
            if (analisis['dest_ip'] != self.my_ip and self.my_ip != '0.0.0.0') or analisis['dest_port'] != self.my_port or sender_addr[0] != self.ext_ip or self.ext_port != analisis['src_port']:
                return
        except:
            if analisis['dest_port'] != self.my_port or (analisis['dest_ip'] != self.my_ip and self.my_ip != '0.0.0.0'):
                return
        self.mutex.acquire()
        ack_to_send_changed = False
        if analisis['seq_no'] == self.ack_to_send:
            ack_to_send_changed = True
            self.seq_no_rcvd = analisis['seq_no']
            self.acked = False
            ret = analisis['body']
            self.ack_to_send = self.seq_no_rcvd + len(ret)
            self.rcv_buffer.append(bytes(ret))
        if (((self.is_host and not self.rcv_syn) and analisis['SYN']) and not analisis['ACK']):# or analisis['FIN']:
            ack_to_send_changed = True
            self.seq_no_rcvd = analisis['seq_no']
            self.acked = False
            ret = analisis['body']
            self.ack_to_send = self.seq_no_rcvd + 1
        if not ack_to_send_changed:
            self.mutex.release()
            return
        if analisis['FIN']:
            ack_to_send_changed = True
            self.seq_no_rcvd = analisis['seq_no']
            self.acked = False
            ret = analisis['body']
            self.ack_to_send = self.seq_no_rcvd + 1
            self.rcv_closing = True
        if analisis['ACK'] and ack_to_send_changed:
            self.ack_rcvd = analisis['ack_no']
        if analisis['ACK'] and analisis['SYN'] and ack_to_send_changed and not ((self.my_ip, self.my_port), (sender_addr[0], analisis['src_port'])) in admin.net_fd:
            self.rcv_synack = True
            self.seq_no_rcvd = analisis['seq_no']
            self.ack_to_send = self.seq_no_rcvd + 1
            self.ext_ip = sender_addr[0]
            self.ext_port = analisis['src_port']
        elif analisis['SYN'] and not ((self.my_ip, self.my_port), (sender_addr[0], analisis['src_port'])) in admin.net_fd:
            self.rcv_syn = True
            self.ext_ip = sender_addr[0]
            self.ext_port = analisis['src_port']
        self.mutex.release()


    def close(self):
        global admin
        global sender
        self.mutex.acquire()
        self.closing = True
        fin = create_flags(FIN=True, ACK=True)
        self.acked = True
        pack = create_pack(self.my_ip, self.ext_ip, 40, self.my_port, self.ext_port, fin, self.seq_no_to_send, self.ack_to_send)
        self.send_buff.append((pack, self.seq_no_to_send
        , 0, 0, 0))
        self.seq_no_to_send = (1 + self.seq_no_to_send) % 2 ** 32 
        self.mutex.release()
        while not self.rcv_closing:
            pass
        self.mutex.acquire()
        self.rcvd_current += 1
        flags = create_flags(ACK=True)
        pack = create_pack(self.my_ip, self.ext_ip, 40, self.my_port, self.ext_port, flags, self.seq_no_to_send, self.ack_to_send)
        self.send_buff.append((pack, self.seq_no_to_send
        , 0, 0, 0))
        self.mutex.release()
        time.sleep((self.timer_setting + self.timer_diff) * 2)
        admin.net_fd.remove(((self.my_ip, self.my_port), (self.ext_ip, self.ext_port)))
        sender.conns.remove(self)
        self.reset()


    def close_rcvd(self):
        self.closing = True
        flags = create_flags(FIN=True, ACK=True)
        self.acked = True
        self.mutex.acquire()
        pack = create_pack(self.my_ip, self.ext_ip, 40, self.my_port, self.ext_port
        , flags, self.seq_no_to_send, self.ack_to_send)
        self.send_buff.append((pack, self.seq_no_to_send, 0, 0, 0))
        self.seq_no_to_send = (1 + self.seq_no_to_send) % 2 ** 32
        self.rcvd_current += 1
        self.mutex.release()
        while self.seq_no_to_send != self.ack_rcvd:
            pass


    def accept(self):
        new_conn = Conn()
        new_conn.inner_bind((self.my_ip, self.my_port))
        if self.is_client:
            raise ConnException('A client can\'t accept')
        return new_conn.inner_accept()


    def inner_accept(self):
        global sender
        global admin
        admin.mutex.acquire()
        sender.add_conn(self)
        self.is_host = True
        while not self.rcv_syn:
            pass
        synack = create_flags(SYN=True, ACK=True)
        self.mutex.acquire()
        pack = create_pack(self.my_ip, self.ext_ip, 40, self.my_port, self.ext_port
        , synack, self.seq_no_to_send, self.ack_to_send)
        self.send_buff.append((pack, self.seq_no_to_send
        , 0, 0, 0))
        self.seq_no_to_send = (1 + self.seq_no_to_send) % 2 ** 32
        self.acked = False
        admin.net_fd.append(((self.my_ip, self.my_port), (self.ext_ip, self.ext_port)))
        logger.info(f'Connection request received from {self.ext_ip} : {self.ext_port}')
        self.mutex.release()
        while True:
            self.mutex.acquire()
            if not self.ack_rcvd == self.seq_no_to_send:
                self.mutex.release()
                continue
            logger.info('Third handshake confirmed')
            self.rcvd_current += 1
            self.mutex.release()
            admin.mutex.release()
            return self


    def dial(self, addr):
        new_conn = Conn()
        if self.is_host:
            raise ConnException('A host can\'t dial')
        if ((self.my_ip, self.my_port), addr) in admin.net_fd:
            raise ConnException('Transport endpoint already connected.')
        self.is_client = True
        new_conn.inner_bind((self.my_ip, self.my_port))
        return new_conn.inner_dial(addr)


    def inner_dial(self, addr):
        global admin
        global sender
        admin.mutex.acquire()
        if self.is_host:
            raise ConnException('A host can\'t dial')
        if ((self.my_ip, self.my_port), addr) in admin.net_fd:
            raise ConnException('Transport endpoint already connected.')
        self.is_client = True
        sender.add_conn(self)
        flags = create_flags(SYN=True)
        self.ext_ip, self.ext_port = addr
        self.mutex.acquire()
        pack = create_pack(self.my_ip, self.ext_ip, 40, self.my_port, self.ext_port
        , flags, self.seq_no_to_send, self.ack_to_send)
        self.send_buff.append((pack, self.seq_no_to_send
        , 0, 0, 0))
        self.seq_no_to_send = (1 + self.seq_no_to_send) % 2 ** 32
        logger.info(f'Sending connection request to {self.ext_ip} : {self.ext_port}')
        self.mutex.release()
        while not self.rcv_synack:
            pass
        logger.info('Connection request accepted')
        self.mutex.acquire()
        self.rcvd_current += 1
        admin.net_fd.append(((self.my_ip, self.my_port), addr))
        self.mutex.release()
        admin.mutex.release()
        return self



class ConnException(Exception):
    pass



sender = Sender_Receiver()
admin = Admin()


def listen(address: str) -> Conn:
    connection = Conn()
    
    host, port = parse_address(address)
    connection.bind((host, port))
    connection.listen(1)
    return connection


def accept(conn) -> Conn:
    return conn.accept()


def dial(address) -> Conn:
    conn = Conn()
    conn.bind(conn.rcv_socket.getsockname())
    host, port = parse_address(address)
    return conn.dial((host, port))


def send(conn: Conn, data: bytes) -> int:
    return conn.send(data)


def recv(conn: Conn, lenght: int) -> bytes:
    return conn.receive(lenght)

def close(conn: Conn):
    conn.close()

