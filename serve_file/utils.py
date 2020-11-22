def parse_address(address):
    host, port = address.split(':')

    if host == '':
        host = 'localhost'

    return host, int(port)

def create_pack(source_ip, dest_ip, lenght, source_port, dest_port, flags, seq_no=0, ack=0, window=65535, offs=5, urgent=0, body=b''):
    ip = create_ip_header(source_ip, dest_ip, lenght)
    a = len(ip)
    tcp = create_tcp_header(source_port, dest_port, flags, window, seq_no, ack, offs, urgent, body)
    return ip + tcp + body

def create_tcp_header(source, dest, flags, window, seq_no, ack, offs, urgent, body):
    res = word_to_bytes(source)                         # Source Port 
    res += word_to_bytes(dest)                          # Destination Port
    res += int_to_bytes(seq_no)                         # Sequence Number
    res += int_to_bytes(ack)                            # Acknowledgement Number
    res += bytes([offs << 4])                           # Data Offset, Reserved, Nonce
    res += flags_to_byte(flags)                         # Flags
    res += word_to_bytes(window)                        # Window Size
    res += word_to_bytes(~(checksum(0, body) & 65535))  # Checksum
    res += word_to_bytes(urgent)                        # Urgent Pointer
    return res


def create_ip_header(source, dest, lenght):
    ip_header = b'\x45\x00'  # Version, IHL, Type of Service
    ip_header += word_to_bytes(lenght)  # Total Length
    ip_header += b'\xab\xcd\x00\x00'  # Identification | Flags, Fragment Offset
    ip_header += b'\x40\x06\xa6\xec'  # TTL, Protocol | Header Checksum

    s_arr = source.split('.')
    s_b_arr = bytes([int(i) for i in s_arr])  # Source Address

    d_arr = dest.split('.')
    d_b_arr = bytes([int(i) for i in d_arr])  # Destination Address

    return ip_header + s_b_arr + d_b_arr


def word_to_bytes(n):
    n %= (2 ** 16)
    n_0 = n % 256
    n_1 = n >> 8
    return bytes([n_1, n_0])


def int_to_bytes(n):
    n %= (2 ** 32)
    n_0 = n % 256
    n >>= 8
    n_1 = n % 256
    n >>= 8
    n_2 = n % 256
    n_3 = n >> 8
    return bytes([n_3, n_2, n_1, n_0])

def analize_header(body):
    if len(body) < 40: return None
    dcr_body = []
    for i in body:
        dcr_body.append(int(i))
    
    res = {}
    res['src_ip'] = bytes_to_ip(dcr_body, 12)
    res['dest_ip'] = bytes_to_ip(dcr_body, 16)
    res['src_port'] = bytes_to_word(dcr_body, 20)
    res['dest_port'] = bytes_to_word(dcr_body, 22)
    res['seq_no'] = bytes_to_int(dcr_body, 24)
    res['ack_no'] = bytes_to_int(dcr_body, 28)
    res['offset'] = dcr_body[32] >> 4
    flags = dcr_body[33]
    bytes_to_flags(flags, res)
    res['window_size'] = bytes_to_word(dcr_body, 34)
    res['checksum'] = bytes_to_word(dcr_body, 36)
    res['urgent'] = bytes_to_word(dcr_body, 38)
    res['body'] = [dcr_body[i] for i in range(40, len(dcr_body))]
    if checksum(res['checksum'], res['body']) != 65535:
        return None
    return res


def flags_to_byte(flags):
    res = 0
    for i in range(len(flags)):
        res += int(flags[i]) << i

    return bytes([res])


def create_flags(FIN=False, SYN=False, RST=False, PSH=False, ACK=False, URG=False, ECE=False, CWR=False):
    return (FIN, SYN, RST, PSH, ACK, URG, ECE, CWR)


def bytes_to_word(arr, offs):
    return (arr[offs] << 8) + arr[offs + 1]


def bytes_to_int(arr, offs):
    return (arr[offs] << 24) + (arr[offs + 1] << 16) + (arr[offs + 2] << 8) + arr[offs + 3]


def bytes_to_flags(flags, dic):
    dic['FIN'] = 1 & flags == 1
    dic['SYN'] = 2 & flags == 2
    dic['RST'] = 4 & flags == 4
    dic['PSH'] = 8 & flags == 8
    dic['ACK'] = 16 & flags == 16
    dic['URG'] = 32 & flags == 32
    dic['ECE'] = 64 & flags == 64
    dic['CWR'] = 128 & flags == 128


def bytes_to_ip(arr, offs):
    semi = []
    for i in range(4):
        semi.append(int(arr[i + offs]))
    ret = str(semi[0])
    for i in range(1, len(semi)):
        ret += '.' + str(semi[i])
    return ret

def checksum(checksum, body):
    count = 0
    while len(body) > count:
        if len(body) - count >= 2:
            checksum ^= bytes_to_word(body, count)
            count += 2
        elif len(body) - count ==1:
            checksum ^= body[count]
            count += 1
    return checksum

def divide_packet(data):
    ret = []
    for i in range(0, len(data), 512):
        ret.append(bytes([data[j] for j in range(i, min(i + 512, len(data)))]))
    return ret