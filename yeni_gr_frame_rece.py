import socket
import cv2
import numpy as np
from redis_helper import RedisHelper
from subprocess import run

r = RedisHelper()
receiver_ip = "0.0.0.0"
max_length = 1300
soket = 7101

import time

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind((receiver_ip, soket))
sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 10000000)
buffer = {}
current_frame_id = None
expected_packets = None
frame_start_time = None
frame_timeout = 0.5  # 500 ms

print(f"Listening on {receiver_ip}:{soket}")

while True:
    packet, addr = sock.recvfrom(max_length + 12)
    frame_id = int.from_bytes(packet[:4], 'big')
    num_of_packs = int.from_bytes(packet[4:8], 'big')
    packet_index = int.from_bytes(packet[8:12], 'big')
    data = packet[12:]

    # Yeni frame başladıysa
    if current_frame_id != frame_id:
        buffer = {}
        current_frame_id = frame_id
        expected_packets = num_of_packs
        frame_start_time = time.time()
        print(f"Receiving new frame: id={frame_id}, packet_count={expected_packets}")

    buffer[packet_index] = data

    # Timeout kontrolü!
    if frame_start_time and (time.time() - frame_start_time) > frame_timeout:
        print("Frame timeout, clearing buffer.")
        buffer = {}
        current_frame_id = None
        expected_packets = None
        frame_start_time = None
        continue

    if expected_packets and len(buffer) == expected_packets:
        print("All packets received.")
        frame_data = b"".join(buffer[i] for i in sorted(buffer.keys()))
        frame = cv2.imdecode(np.frombuffer(frame_data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is not None and frame.size > 0:
            cv2.imshow("Received Frame", frame)
            cv2.waitKey(1)
        else:
            print("Frame decoding failed. Skipping this frame.")
        buffer = {}
        current_frame_id = None
        expected_packets = None
        frame_start_time = None
