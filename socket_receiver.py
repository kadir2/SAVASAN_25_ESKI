import socket
import cv2
import numpy as np
from redis_helper import RedisHelper
from subprocess import run

r = RedisHelper()
receiver_ip = "0.0.0.0"
max_length = 45000
soket = 7101

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind((receiver_ip, soket))
sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 10000000)
buffer = {}
expected_packets = None
print(f"Listening on {receiver_ip}:{soket}")

# static ip değiştirme:
# run(["bash", "static_ip.sh"])

while True:
    packet, addr = sock.recvfrom(max_length)
    if expected_packets is None:
        # İlk 8 baytı çöz: toplam paket sayısı ve sıra numarası
        expected_packets = int.from_bytes(packet[:4], byteorder='big')
        packet_index = int.from_bytes(packet[4:8], byteorder='big')
        buffer[packet_index] = packet[8:]  # Header'dan sonra veri
        print(f"Receiving frame with {expected_packets} packets.")
    else:
        # Sadece paket sıra numarasını çöz
        packet_index = int.from_bytes(packet[4:8], byteorder='big')
        buffer[packet_index] = packet[8:]

    missing_packets = [i for i in range(expected_packets) if i not in buffer]
    if missing_packets:
        continue

    if len(buffer) == expected_packets:  # Tüm paketler alındı mı?
        print("All packets received.")
        frame_data = b"".join(buffer[i] for i in sorted(buffer.keys()))
        frame = np.frombuffer(frame_data, dtype=np.uint8)
        frame = cv2.imdecode(frame, cv2.IMREAD_COLOR)

        if frame is None or frame.size == 0:
            print("Frame decoding failed. Skipping this frame.")
            continue  # Bozuk çerçeveyi atla

        if frame is not None and frame.size > 0:
            _, img_encoded = cv2.imencode('.jpg', frame)
            r.r.set("frame", img_encoded.tobytes())
            cv2.imshow("Received Frame", frame)
            cv2.waitKey(1)
        else:
            print("Corrupted frame received.")

        buffer = {}
        expected_packets = None

