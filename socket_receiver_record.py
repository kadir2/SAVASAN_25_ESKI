import socket
import cv2
import numpy as np
from redis_helper import RedisHelper
from subprocess import run
import sys

r = RedisHelper()
receiver_ip = "0.0.0.0"
max_length = 42000
soket = 7101

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind((receiver_ip, soket))
sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 10000000)

buffer = {}
expected_packets = None
writer = None
print(f"Listening on {receiver_ip}:{soket}")

# static ip değiştirme:
# run(["bash", "static_ip.sh"])

while True:
    packet, addr = sock.recvfrom(max_length)
    if expected_packets is None:
        expected_packets = int.from_bytes(packet[:4], byteorder='big')
        packet_index = int.from_bytes(packet[4:8], byteorder='big')
        buffer[packet_index] = packet[8:]
        print(f"Receiving frame with {expected_packets} packets.")
    else:
        packet_index = int.from_bytes(packet[4:8], byteorder='big')
        buffer[packet_index] = packet[8:]

    missing_packets = [i for i in range(expected_packets) if i not in buffer]
    if missing_packets:
        continue

    if len(buffer) == expected_packets:
        print("All packets received.")
        frame_data = b"".join(buffer[i] for i in sorted(buffer.keys()))
        frame = np.frombuffer(frame_data, dtype=np.uint8)
        frame = cv2.imdecode(frame, cv2.IMREAD_COLOR)

        if frame is None or frame.size == 0:
            print("Frame decoding failed. Skipping this frame.")
            buffer = {}
            expected_packets = None
            continue

        # --- start recording logic ---
        if writer is None:
            h, w = frame.shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter('output.mp4', fourcc, 20.0, (w, h))
            if not writer.isOpened():
                print("Error: could not open video writer.")
                sys.exit(1)
        writer.write(frame)

        cv2.imshow("Received Frame", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            print("Stopping recording.")
            writer.release()
            cv2.destroyAllWindows()
            break
        # --- end recording logic ---

        # push to Redis as before
        _, img_encoded = cv2.imencode('.jpg', frame)
        r.r.set("frame", img_encoded.tobytes())

        buffer = {}
        expected_packets = None

# cleanup if loop exits in other way
if writer:
    writer.release()
cv2.destroyAllWindows()

