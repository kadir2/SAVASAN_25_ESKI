from ultralytics import YOLO
from redis_helper import RedisHelper
import json
import cv2
import time
import ast  # Redis'ten gelen string'i listeye çevirmek için
import threading
import logging
import os
import shutil
from datetime import datetime
import numpy as np

class Detection:
    def __init__(self):
        self.init_logger()
        self.model = YOLO("/home/cello/v10son.pt").to("cuda")
        self.rh = RedisHelper()
        self.r = self.rh.r
        with open('config.json') as f:
            data = json.load(f)
        self.threshold = data["yolo"]["threshold"]
        self.yolo_timeout_system_switch = data['yolo']['yolo_timeout_system_switch']
        logging.info(self.threshold)
        self.time_without_detection = 0

        self.is_local = data["uav_handler"]["is_local"]
        
    def init_logger(self):
        # Customcustom logger in order to log to both console and file
        self.logger = logging.Logger('GOAT')
        # Set the log level
        self.logger.setLevel(logging.DEBUG)
        # Create handlers
        c_handler = logging.StreamHandler()
        
        log_file_path = 'seq_system.log'
        old_logs_dir = "logs"
        
        if not os.path.exists(old_logs_dir):
            os.makedirs(old_logs_dir)
            
        if os.path.exists(log_file_path):
            # Generate a unique name for the log file in the old logs directory
            timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
            new_log_file_name = f"GOAT_guidance_{timestamp}.log"

            new_log_file_path = os.path.join(old_logs_dir, new_log_file_name)
            # Move the log file to the old logs directory
            shutil.move(log_file_path, new_log_file_path)
            
        f_handler = logging.FileHandler(log_file_path)
        # Set levels for handlers
        c_handler.setLevel(logging.DEBUG)
        f_handler.setLevel(logging.DEBUG)

        # Create formatters and add it to handlers
        c_format = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
        f_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(process)d - %(threadName)s - %(filename)s:%(lineno)d - %(funcName)s - %(message)s')
        c_handler.setFormatter(c_format)
        f_handler.setFormatter(f_format)

        # Add handlers to the self.logger
        self.logger.addHandler(c_handler)
        self.logger.addHandler(f_handler)

    def detect(self):
        while True:
            start_fps = datetime.now()
            if self.is_local:
                frame = self.rh.from_redis('frame')
            else:
                frame_data = self.rh.r.get("frame")
                np_img = np.frombuffer(frame_data, dtype=np.uint8)
                frame = cv2.imdecode(np_img, cv2.IMREAD_COLOR)

            if frame is None:
                logging.error("Frame Redis'ten alınamadı, tekrar deniyor...")
                time.sleep(0.1)
                continue
            results = self.model(frame)
            detections = results[0].boxes.data.cpu().numpy()
            filitrelenmiş = []
            last_detection = None
            if len(detections) > 0:
                max_conf = 0
                for detection in detections:
                    x1, y1, x2, y2, conf, cls = detection
                    target_width = x2-x1
                    horizontal_coverage = (target_width / frame.shape[1]) * 100
                    if horizontal_coverage > 60:
                        self.logger.debug('horizontal coverage more than %60: '+str(horizontal_coverage))
                        continue

                    self.logger.debug(f"Güven skoru: {conf}")
                    if conf >= self.threshold:
                        b_box = [int(x1), int(y1), int(x2), int(y2), int(conf)]
                        filitrelenmiş.append(b_box)


                if len(filitrelenmiş) > 0:
                    max_conf = max([box[4] for box in filitrelenmiş])  
                    for box in filitrelenmiş:
                        if box[4] == max_conf:  
                            last_detection = box[:4]  
                            break  

                    self.r.set("b_box", json.dumps(last_detection),px=250) #x1,y1,x2,y2
                    print(f"LAST_YOLO_BOX === {last_detection}")
                    self.r.set("güven_skoru", max_conf)
                    self.time_without_detection = 0
                    self.r.set("ensesindeyim", "True")
                    logging.info(f"Tespit edildi ve Redis'e gönderildi: {last_detection}")

                else:
                    # Increment the time without detection
                    self.time_without_detection += (datetime.now() - start_fps).total_seconds()

                self.logger.debug('time without detection: '+str(self.time_without_detection))

                # Check if the maximum time without detection is reached
                if self.time_without_detection >= self.yolo_timeout_system_switch:
                    self.logger.debug('yolo timeout')
                    self.time_without_detection = 0
                    self.r.set("ensesindeyim", "False")

                    # cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)  # Yeşil kutu çiz
            else:
                logging.error("Nesne bulunamadı, aramaya devam ediliyor...")

            # Görüntüyü göster
            # cv2.imshow("YOLO Tespit", frame)
            # if cv2.waitKey(1) & 0xFF == ord('q'):  # 'q' tuşuna basınca çık
            #     break

            time.sleep(0.1)  # Gereksiz yüklenmeyi önlemek için kısa bir bekleme süresi

        # cv2.destroyAllWindows()

def run_detection():
    det = Detection()
    det.detect()

if __name__ == '__main__':
    detection_thread = threading.Thread(target=run_detection)
    detection_thread.start()
    detection_thread.join()
