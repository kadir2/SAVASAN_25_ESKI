import cv2
import redis
import struct
import numpy as np
import time
import logging
import os
import shutil
from datetime import datetime
import math
from redis_helper import RedisHelper
import json
import threading
import sys
import socket

class Loggerr:
    def __init__(self):
        # Logger oluştur
        self.logger = logging.Logger('UAV_Handler')
        self.logger.setLevel(logging.DEBUG)  # Log seviyesi DEBUG olarak ayarlanır
        
        # Handlers: Konsol ve Dosya
        c_handler = logging.StreamHandler()  # Konsol için handler
        log_file_path = 'UAV_Handler.log'  # Log dosyasının adı
        old_logs_dir = "old_logs_UAV_Handler"  # Eski log dosyalarının taşınacağı klasör

        # Eski log dosyalarını yedekle
        if not os.path.exists(old_logs_dir):  # Eğer klasör yoksa oluştur
            os.makedirs(old_logs_dir)
        if os.path.exists(log_file_path):  # Eğer log dosyası varsa
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")  # Zaman damgası oluştur
            new_log_file_name = f"UAV_Handler_{timestamp}.log"  # Yeni log dosyasının adı
            new_log_file_path = os.path.join(old_logs_dir, new_log_file_name)  # Yeni log dosyasının yolu
            shutil.move(log_file_path, new_log_file_path)  # Eski log dosyasını taşı
        
        f_handler = logging.FileHandler(log_file_path)  # Log dosyasına handler
        
        # Seviyeleri belirle
        c_handler.setLevel(logging.DEBUG)  # Konsola yazdırılacak log seviyesi
        f_handler.setLevel(logging.DEBUG)  # Dosyaya yazdırılacak log seviyesi
        
        # Formatlar
        c_format = logging.Formatter('%(name)s - %(levelname)s - %(message)s')  # Konsol formatı
        f_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s') # dosyaya yazdırılacak log formatı

        
        # Formatları handler'lara ekle
        c_handler.setFormatter(c_format)
        f_handler.setFormatter(f_format)
        
        # Handler'ları logger'a ekle
        self.logger.addHandler(c_handler)
        self.logger.addHandler(f_handler)
# Kullanım
logger_instance = Loggerr()  # Logger nesnesi oluştur
logger = logger_instance.logger   # Logger nesnesini al





class send_rocket:
    def __init__(self, ip, data_port, frame_port, redis_host, redis_port, target_fps):
        
        self.target_ip = ip
        self.data_port = data_port
        self.frame_port = frame_port
        self.max_length = 20000  # Maksimum veri boyutu
        self.target_fps = target_fps
        self.frame_interval = 1.0 / target_fps  # Kareler arası süre (saniye cinsinden)
        self.run_system = True
        self.fps_timer = 0

        # UDP soketi oluştur ve ayarla
        self.data_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.frame_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Bağlantı için IP ve portları bağla
        #self.data_sock.bind((self.target_ip, self.data_port))
        #self.frame_sock.bind((self.target_ip, self.frame_port))

        # Non-blocking moda al
        self.data_sock.setblocking(False)
        self.frame_sock.setblocking(False)

        # Redis bağlantısını oluştur
        self.r = redis.StrictRedis(host=redis_host, port=redis_port, decode_responses=True)

        # Redis helper
        #self.redis_helper = RedisHelper()  # RedisHelper sınıfı daha önce tanımlanmış olmalı

        self.frame_count = 0  # Frame sayacı
        self.data_count = 0  # Data sayacı
        self.frame_toplam_sure = 0  # Toplam süre
        self.frame_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 10000000) #bant genişliği ayarı



        threading.Thread(target=self.send_frame_rocket).start()
        #threading.Thread(target=self.send_data_rocket).start()
   
   
    def gstreamer_pipeline(self,
        sensor_id=0,
        capture_width=1920,
        capture_height=1080,
        framerate=30,
        flip_method=0,
        awb_mode=0,
        exp_comp=0,
        aelock=False,
        awblock=False,
        sensor_mode=0,
        exposure=0

    ):
        """
        Return GStreamer pipeline string for nvarguscamerasrc
        """
        return (
            f"nvarguscamerasrc sensor-id={sensor_id} aelock=false awblock=true wbmode=0 exposurecompensation={exposure} ! "
            f"video/x-raw(memory:NVMM), width=(int){capture_width}, height=(int){capture_height}, framerate=(fraction){framerate}/1 ! "
            f"nvvidconv flip-method={flip_method} ! "
            f"video/x-raw, format=(string)BGRx ! "
            f"videoconvert ! "
            f"video/x-raw, format=(string)BGR ! appsink"
        )
    
    def send_frame_rocket(self):
        while True:
            exposure = self.r.get('exposure')
            old_exposure = exposure
            pipeline = self.gstreamer_pipeline(exposure=exposure/10)
            print(cv2.getBuildInformation())
            print(f"Opening camera with pipeline:\n{pipeline}")
            cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
            if not cap.isOpened():
                print("Error: Unable to open camera for live preview.")
                return
            self.fps_timer = time.time()

            while old_exposure == exposure:
                try:
                    exposure = self.r.get('exposure')
                    frame_strt_time = time.time()


                    self.frame_count += 1  # Frame sayacı
                    #logger.debug(f"Frame sayısı: {self.frame_count} total fps: {self.frame_count / (time.time() - self.fps_timer)}")

                    # Redis'ten frame al
                    # frame = self.redis_helper.from_redis('frame')
                    ret, frame = cap.read()
                    cv2.imshow('Live Preview', frame)
                    if frame is None or frame.size == 0 or not ret:
                        logger.debug(f'frame İ== {frame} frame boyutu 0')
                        logger.debug('Received an empty frame from Redis.')
                        continue
                    
                    # ekrana fps ve frame sayısını yazdır
                    # frame_ = frame.copy()
                    # cv2.putText(frame_, "Frame Count: " + str(self.frame_count), (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)
                    # cv2.putText(frame_, "FPS: " + str(round(self.frame_count / (time.time() - self.fps_timer),2)), (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)


                    ## Frame'i JPEG formatına çevir
                    retval, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 50])            # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
                    if not retval:
                        logger.debug("Encoding failed.")
                        continue
                    
                    

                    ss = buffer.tobytes()
                    ss_size = len(ss)
                    num_of_packs = math.ceil(ss_size / self.max_length)

                    logger.debug(f"Frame boyutu: {ss_size}, Paket sayısı: {num_of_packs} ")

                    left = 0
                    #header = struct.pack("!I", num_of_packs)  # Toplam paket sayısı
                    header = num_of_packs.to_bytes(4, byteorder='big') #paket sayısını karşıya bildirmek için byte a çevir

                    for i in range(num_of_packs):
                        sequence = i.to_bytes(4, byteorder='big') 
                        #sequence = struct.pack("!I", i)  # Paket sıra numarası
                        packet = header + sequence + ss[left:left + self.max_length]  # Header + Sıra No + Veri
                        self.frame_sock.sendto(packet, (self.target_ip, self.frame_port))
                        left += self.max_length

                    
                    elapsed_time = time.time() - frame_strt_time + self.frame_toplam_sure
                    self.frame_toplam_sure = 0
                    uyuma_suresi = max(0, self.frame_interval - elapsed_time)
                    #logger.debug(f"Frame gönderildi, uyuma süresi: {uyuma_suresi}, geçen süre: {elapsed_time}, max_fps: {1 / (time.time() - frame_strt_time)}")
                    if elapsed_time < self.frame_interval:
                        time.sleep(uyuma_suresi)


                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        cv2.imwrite("frame10.jpg", frame)
                        break

                except Exception as e:
                    logger.debug(f"Error: {e} hatası oluştu veri gönderilemedi LOCATION:send_frame_rocket GENERAL")
                    time.sleep(0.01)

                finally:
                    cap.release()
                    time.sleep(0.005)
        
        

if __name__ == "__main__":
    
    ground_ip = "10.42.0.3"
    target_port = 6001
    frame_port = 7101 
    data_sender = send_rocket(ground_ip, target_port, frame_port, redis_host='localhost', redis_port=6379, target_fps=30) #data sender oluştur

