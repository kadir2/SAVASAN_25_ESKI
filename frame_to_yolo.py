import redis
import cv2
import numpy as np
import time
from ultralytics import YOLO
import logging
import os
import datetime
import shutil

class Logger:
    def __init__(self):
        self.init_logger()

    def init_logger(self):
        # create main logs folder
        base_logs_dir = 'kamikaze_logs'
        if not os.path.exists(base_logs_dir):
            os.makedirs(base_logs_dir)
        self.logs_dir = base_logs_dir

        self.logger = logging.Logger('GOAT')
        self.logger.setLevel(logging.DEBUG)

        c_handler = logging.StreamHandler()

        # all log files live under kamikaze_logs/
        log_file_path = os.path.join(base_logs_dir, 'frame_to_yolo.log')
        # eski logları saklamak için klasör (uzantısız)
        old_logs_dir = os.path.join(base_logs_dir, "old_logs_frame_to_yolo")

        if not os.path.exists(old_logs_dir):
            os.makedirs(old_logs_dir)

        if os.path.exists(log_file_path):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            new_log_file_name = f"GOAT_frame_to_yolo_{timestamp}.log"
            new_log_file_path = os.path.join(old_logs_dir, new_log_file_name)
            shutil.move(log_file_path, new_log_file_path)

        f_handler = logging.FileHandler(log_file_path)
        c_handler.setLevel(logging.DEBUG)
        f_handler.setLevel(logging.DEBUG)

        c_format = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
        f_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        c_handler.setFormatter(c_format)
        f_handler.setFormatter(f_format)

        self.logger.addHandler(c_handler)
        self.logger.addHandler(f_handler)

# initialize logger immediately
logger = Logger().logger  # Artık hem konsola hem de frame_to_yolo.log'a yazar

# YOLO ile QR tespiti
yolo = YOLO('QR.pt')

# Redis’e bağlan
r = redis.Redis(host="localhost", port=6379, db=0)

# QR kodu çözümleyici
qr_decoder = cv2.QRCodeDetector()

# cap = cv2.VideoCapture(0)  

while True:
    raw = r.get("frame")  # JPEG byte verisi
    if raw is None:
        time.sleep(0.1)
        continue

    # Redis bytes → NumPy array → BGR frame
    np_arr = np.frombuffer(raw, dtype=np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    
    # ret, frame = cap.read()
    if frame is None:
        logger.debug("Görüntü decode edilemedi")
        continue

    # YOLO ile tespit
    results = yolo.predict(frame)
    for result in results:
        for box in result.boxes:
            # Kutu koordinatları
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = box.conf[0]
            cls = int(box.cls[0])
            label = f"{result.names[cls]} {conf:.2f}"

            # Kutu çizimi
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
            cv2.putText(frame, label, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)

            # ROI’yi kırp ve decode et
            roi = frame[y1:y2, x1:x2]
            data, points, _ = qr_decoder.detectAndDecode(roi)
            if data:
                logger.info(f'QR OKUNDU BAŞARILI === {data}')
                break
            else:
                logger.info("QR Kodu bulunamadı")

    # Ekrana göster
    cv2.imshow("Redis Frame + QR OKUMA", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cv2.destroyAllWindows()