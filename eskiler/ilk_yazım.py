import json
import redis
import threading
import time
import socket
import cv2
import numpy as np
import math
from redis_helper import RedisHelper
import logging
import time
from datetime import datetime
import os
import shutil
import select
#import atexit
#import struct
#import asyncio



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





#/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

class send_rocket:
    def __init__(self, ip, data_port, frame_port, redis_host, redis_port, target_fps):
        
        self.target_ip = ip
        self.data_port = data_port
        self.frame_port = frame_port
        self.max_length = 20000  # Maksimum veri boyutu
        self.target_fps = target_fps
        self.frame_interval = 1.0 / target_fps  # Kareler arası süre (saniye cinsinden)
        self.sending = False
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
        self.redis_helper = RedisHelper()  # RedisHelper sınıfı daha önce tanımlanmış olmalı

        self.frame_count = 0  # Frame sayacı
        self.data_count = 0  # Data sayacı
        self.frame_toplam_sure = 0  # Toplam süre
        self.frame_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 10000000) # wifi ile kullanmak için bant genişliği ayarı



        threading.Thread(target=self.send_frame_rocket).start()
        #threading.Thread(target=self.send_data_rocket).start()
   
   

    def send_frame_rocket(self):
        self.fps_timer = time.time()   
        while self.run_system:
            try:
                frame_strt_time = time.time()

                if self.sending:
                    time.sleep(0.01)
                    self.frame_toplam_sure += 0.01  #time.time() - frame_strt_time
                    continue

                self.sending = True

                self.frame_count += 1  # Frame sayacı
                #logger.debug(f"Frame sayısı: {self.frame_count} total fps: {self.frame_count / (time.time() - self.fps_timer)}")

                # Redis'ten frame al
                frame = self.redis_helper.from_redis('frame')
                if frame is None or frame.size == 0:
                    logger.debug('Received an empty frame from Redis.')
                    self.sending = False
                    continue
                
                # ekrana fps ve frame sayısını yazdır
                # frame_ = frame.copy()
                # cv2.putText(frame_, "Frame Count: " + str(self.frame_count), (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)
                # cv2.putText(frame_, "FPS: " + str(round(self.frame_count / (time.time() - self.fps_timer),2)), (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)


                ## Frame'i JPEG formatına çevir
                retval, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 50])            # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
                if not retval:
                    logger.debug("Encoding failed.")
                    self.sending = False
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

            except Exception as e:
                logger.debug(f"Error: {e} hatası oluştu veri gönderilemedi LOCATION:send_frame_rocket GENERAL")
                self.sending = False
                time.sleep(0.01)

            finally:
                self.sending = False
                time.sleep(0.005)
            



    def send_data_rocket(self):
        while self.run_system:
            try:
                if self.sending == True:
                    time.sleep(0.01)
                    #logger.debug("konum 1")
                    continue
                self.sending = True

                self.data_count += 1
                logger.debug(f"Data sayısı: {self.data_count}")

                #logger.debug("konum 2")
                data = self.get_data_from_redis() #redisten veri al
                #logger.debug("konum 3")
                if data is not None:
                    try:
                        self.data_sock.sendto(data.encode('utf-8'), (self.target_ip, self.data_port))            #veri gönder
                        logger.debug(f"Data: {data} gönderildi")
                        logger.debug("---"*10)
                    except socket.error as e:
                        logger.debug(f"Error: {e} hatasi oluştu veri gönderilemedi  LOCATION:send_data_rocket")
                else:
                    logger.debug("Data is None, continuing...")            


                #logger.debug(f"DData testi başladı")


                self.sending = False
                time.sleep(0.1)    
            except Exception as e:
                logger.debug(f"Error: {e} hatasi oluştu veri gönderilemedi  LOCATION:send_data_rocket")
                self.sending = False
                time.sleep(0.05)

    def get_data_from_redis(self):
        try:
            #logger.debug("konum A") # konum A

            kamikaze = self.r.get('kamikaze_buton') 
            guidance_konumlu = self.r.get('konumlu_buton') 
            goruntulu = self.r.get('goruntulu_buton') 
            enemy_id = self.r.get('selected_id') 
            black_list = self.r.get('blacklist') 
            av_modu = self.r.get('av_modu')

            kitlenme_data = self.r.get('kitlenme_paketi')
            kamikaze_data = self.r.get('kamikaze_packet')
            try:
                kitlenme_bilgisi = json.loads(kitlenme_data) if kitlenme_data else None 
                kamikaze_bilgisi = json.loads(kamikaze_data) if kamikaze_data else None
            except json.JSONDecodeError as e:
                logger.debug(f"Error: {e} hatasi oluştu veri alınamadı  LOCATION:get_data_from_redis")
                kitlenme_bilgisi = None
                kamikaze_bilgisi = None    
            #logger.debug("konum B") # konum B    

            """
            pipeline = self.r.pipeline()
            pipeline.get('kitlenme_paketi')
            pipeline.get('kamikaze_packet')
            kitlenme_data, kamikaze_data = pipeline.execute()

            kitlenme_bilgisi = json.loads(kitlenme_data) if kitlenme_data else None
            kamikaze_bilgisi = json.loads(kamikaze_data) if kamikaze_data else None
            """

            data_bbox = self.r.get('tracker_bbox') #tracker bbox

            if data_bbox:  # Eğer tracker bbox varsa
                try:
                    # JSON formatına dönüştür ve bbox formatına çevir
                    data_bbox = json.loads(data_bbox)  # data format: x1, y1, w, h
                    bbox = [int(data_bbox[0]), int(data_bbox[1]), int(data_bbox[2]), int(data_bbox[3])]
                except (json.JSONDecodeError, ValueError, KeyError, TypeError) as e:
                    logging.error(f"Geçersiz bbox verisi: {data_bbox}, Hata: {e}")
                    bbox = [0, 0, 0, 0]  # Hatalı durumda varsayılan bbox
            else:
                bbox = [0, 0, 0, 0]  # Eğer tracker bbox yoksa 0 yap

            #logger.debug("konum C") # konum C


            data = {
                "kamikaze": kamikaze, #kamikaze
                "konumlu": guidance_konumlu, #konumlu
                "goruntulu": goruntulu, #görüntülü
                "enemy_id": enemy_id, #enemy id
                "black_list":black_list, #blacklist
                "av_modu": av_modu, #av modu
                "kitlenme_bilgisi": kitlenme_bilgisi, #kitlenme bilgisi
                "kamikaze_bilgisi": kamikaze_bilgisi, #kamikaze bilgisi
                "tracker_bbox" : bbox #tracker bbox
            }

            logger.debug(f"Data: {data} alındı")
            #logger.debug("konum D") # konum D
            return json.dumps(data) #json formatında veri döndür


        except redis.RedisError as e:
            logger.debug(f"Error: {e} hatasi oluştu veri alınamadı  LOCATION:get_data_from_redis")
            #logger.debug("konum E") # konum E
            return None  



#/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////


class DataHandler:

    def __init__(self, ip, telemetry_port, control_port, redis_host, redis_port):
        # Portlar ve Redis bağlantısı
        self.telemetry_port = telemetry_port
        self.control_port = control_port
        self.r = redis.StrictRedis(host=redis_host, port=redis_port, decode_responses=True)
        
        # Telemetry port için socket
        self.telemetry_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.telemetry_sock.bind((ip, self.telemetry_port))
        self.telemetry_sock.setblocking(False)  # Non-blocking
        
        # Control port için socket
        self.control_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.control_sock.bind((ip, self.control_port))
        self.control_sock.setblocking(False)  # Non-blocking
        
        # Redis temizleme (Dikkatli kullanın!)
        os.system('redis-cli flushall')
        
        self.receiving = False  # Veri gönderme bayrağı
        self.time_without_detection = 0  # En son alınan veriden bu yana geçen süre
        self.time_without_detection_2 = 0
        self.run_system = True  # Sistem çalıştırma bayrağı
        self.time_count = 0  # Zaman sayacı


        threading.Thread(target=self.update_telemetry_thread).start()
        threading.Thread(target=self.update_control_data_thread).start()




    def update_telemetry_thread(self):
        
        self.time_without_detection = 0

        while self.run_system:

            start_= datetime.now()
            time.sleep(0.05)

            if self.receiving == True:
                    time.sleep(0.001)
                    self.time_count += 0.001
                    continue            
            self.receiving = True

           

            try:
                telemetry_data = self.get_telemetry_data()
            except Exception as e:
                logger.debug(f"Error: {e} hatasi oluştu veri alınamadı  LOCATION:update_telemetry_thread")
                telemetry_data = None
            self.receiving = False    

            if telemetry_data:
                self.time_without_detection = 0 # en son alına veriden bu yana geçen süreyi sıfırla

                try:
                    self.save_to_redis(json.loads(telemetry_data))
                    logger.debug(f"Telemetry data saved to Redis: {telemetry_data}")
                except json.JSONDecodeError as e:
                    logger.debug(f"JSON Decode Error: {e} - Data: {telemetry_data} ") # logları yazdır
            else:
                elapsed_time = (datetime.now() - start_).total_seconds()
                elapsed_time += self.time_count
                self.time_without_detection += elapsed_time 
                logger.debug(f"time_count: {self.time_count}")
                self.time_count = 0

                logger.debug(f"No telemetry data received, continuing... total time without detection: {self.time_without_detection}")

                if self.time_without_detection >= 15:
                    self.r.set('konumlu_buton', 'False') # konumlu butonunu false yap
                    self.r.set('kamikaze_buton', 'False') # kamikaze butonunu false yap
                    self.r.set('run_tracker', 'False') # trackerı durdur
                    self.r.set('run_yolo', 'False') # yoloyu durdur
                    self.r.set('goruntulu_buton', 'False') # görüntülü butonu false yap
                    self.r.set('av_modu', 'False') # av modunu false yap
                    logger.debug('Telemetry receiving timeout') # logları yazdır
                    self.time_without_detection = 0 # algılanmayan süreyi sıfırla





        


    # def get_telemetry_data(self):
    #     try:
    #         telemetry_data, _ = self.telemetry_sock.recvfrom(8192) #telemetry verilerini al
    #         telemetry_data = telemetry_data.decode('utf-8') #telemetry verilerini utf-8 formatına çevir
    #         logger.debug(f"Received telemetry data: {telemetry_data}") #logları yazdır
    #         return telemetry_data #telemetry verilerini döndür
    #     except socket.error as e: 
    #         logger.debug(f"Socket error: {e}") #logları yazdır
    #         return None

    def get_telemetry_data(self):
        try:
            ready = select.select([self.telemetry_sock], [], [], 0.5)  # 0.5 saniye bekle
            if ready[0]:  # Eğer veri geldiyse
                telemetry_data, _ = self.telemetry_sock.recvfrom(8192)
                telemetry_data = telemetry_data.decode('utf-8')
                logger.debug(f"Received telemetry data: {telemetry_data}")
                return telemetry_data
            else:
                return None  # Veri yok, beklemeye devam et
        except socket.error as e:
            logger.debug(f"Socket error: {e}")
            return None


   



    def save_to_redis(self, data):
        try: 
            konum_bilgileri = data.get("konumBilgileri") # konum bilgilerini al
            sunucu_saati = data.get("sunucusaati")  # sunucu saati al
            qr_konumu = data.get("qr_koordinati") # qr konumunu al
            hss = data.get("hss_koordinatlari") #hss koordinatlarını al

            if konum_bilgileri:
                self.r.set('konum_bilgileri', json.dumps(konum_bilgileri)) #konum bilgilerini redise kaydet
                logger.debug(f"Set konum_bilgileri in Redis: {konum_bilgileri}") 
            else: 
                logger.debug("konumBilgileri not found in telemetry data.")

            if sunucu_saati: #eğer sunucu saati varsa
                print(f"Sunucu saati: {sunucu_saati}")
                self.r.set('sunucu_saati', json.dumps(sunucu_saati), ex=2) #sunucu saati redise kaydet
                logger.debug(f"Set sunucu_saati in Redis: {sunucu_saati}")
            else:
                logger.debug("sunucuSaati not found in telemetry data.") 

            if qr_konumu:
                self.r.set('qr_konumu', json.dumps(qr_konumu))  #qr konumunu redise kaydet
                logger.debug(f"Set qr_konumu in Redis: {qr_konumu}") 
            else:
                logger.debug("qrKonumu not found in telemetry data.") 

            if hss:
                self.r.set('hss', json.dumps(hss)) #hss koordinatlarını redise kaydet

            else:
                logger.debug("hss not found in telemetry data.")

        except Exception as e:
            logger.debug(f"Error saving to Redis: {e}") 


    # def get_control_data(self):
    #     try:
    #         control_data, _ = self.control_sock.recvfrom(8192) #control verilerini al
    #         control_data = control_data.decode('utf-8') #control verilerini utf-8 formatına çevir
    #         logger.debug(f"Received control data: {control_data}") #logları yazdır
    #         return control_data #control verilerini döndür
    #     except socket.error as e: 
    #         logger.debug(f"Socket error: {e}")
    #         return None

    def get_control_data(self):
        try:
            ready = select.select([self.control_sock], [], [], 0.5)  # 0.5 saniye bekle
            if ready[0]:  # Eğer veri geldiyse
                control_data, _ = self.control_sock.recvfrom(8192)
                control_data = control_data.decode('utf-8')
                logger.debug(f"Received control data: {control_data}")
                return control_data
            else:
                logger.debug("No control data received.")
                return None
        except socket.error as e:
            logger.debug(f"Socket error: {e}")
            return None 




    """ Control verilerini alır ve redise kaydeder """

    def update_control_data_thread(self):
        self.time_without_detection_2 = 0

        while self.run_system:
            
            start_ = datetime.now()
            time.sleep(0.15)

            if self.receiving == True:
                    time.sleep(0.001)
                    continue            
            self.receiving = True

            start_ = datetime.now()

            try:
                control_data = self.get_control_data()
            except Exception as e:
                logger.debug(f"Error: {e} hatasi oluştu veri alınamadı  LOCATION:update_control_data_thread")
                control_data = None
            self.receiving = False

            if control_data:
                try:
                    self.time_without_detection_2 = 0
                    self.save_to_redis_data(json.loads(control_data)) #control verilerini redise kaydet
                except json.JSONDecodeError as e: #json decode hatası varsa
                    logger.debug(f"JSON Decode Error: {e} - Data: {control_data}") #logları yazdır
            else:
                logger.debug("No control data received, continuing...") #logları yazdır
                elapsed_time = (datetime.now() - start_).total_seconds()
                self.time_without_detection_2 += elapsed_time
                logger.debug(f"-"*5)
                logger.debug(f"total time without detection: {self.time_without_detection_2}")

                if self.time_without_detection_2 >= 15:
                    logger.debug('Control receiving timeout') #logları yazdır
                    self.time_without_detection_2 = 0

    def get_control_data(self):
        try:
            control_data, _ = self.control_sock.recvfrom(8192) #control verilerini al
            control_data = control_data.decode('utf-8') #control verilerini utf-8 formatına çevir
            logger.debug(f"Received control data: {control_data}") #logları yazdır
            return control_data #control verilerini döndür
        except socket.error as e: 
            logger.debug(f"Socket error: {e}")
            return None    

    def save_to_redis_data(self, data):
        try:
            kamikaze = data.get("kamikaze") 
            konumlu = data.get("guidance_konumlu")
            goruntulu = data.get("goruntulu") 
            rakip_id = data.get("enemyId") 
            blacklist = data.get("black_list")
            av_modu = data.get("av_modu")

            if kamikaze is not None:
                self.r.set('kamikaze_buton', 'True' if kamikaze else 'False')
                logger.debug(f"Kamikaze mode set to {'True' if kamikaze else 'False'}") #logları yazdır


            if konumlu is not None:
                self.r.set('konumlu_buton', 'True' if konumlu else 'False')
                logger.debug(f"Guidance mode set to {'True' if konumlu else 'False'}")


            if goruntulu is not None:
                if goruntulu==False:
                    self.r.set('run_tracker', 'False')
                    self.r.set('run_yolo', 'False')

                self.r.set('goruntulu_buton', 'True' if goruntulu else 'False')
                logger.debug(f"Tracker and YOLO mode set to {'True' if goruntulu else 'False'}")


            if rakip_id is not None: 
                # Ensure rakip_id is stored as a string
                if rakip_id == 'n': #eğer rakip id n ise
                    rakip_id = '' #rakip id yi boş yap
                self.r.set('rakip_id', str(rakip_id) if rakip_id else '')
                logger.debug(f"rakip_id set to {rakip_id}")

            if blacklist is not None: 
                # Convert the black_list to a JSON string and store it
                black_list_json = json.dumps(blacklist) #blacklisti json formatına çevir
                self.r.set('blacklist', black_list_json) 
                logger.debug(f"Blacklist set to {black_list_json}") 
            else:
                self.r.set('blacklist', json.dumps([])) #eğer blacklist yoksa boş bir json formatında redise kaydet

            if av_modu is not None: 
                self.r.set('av_modu', 'True' if av_modu else 'False') 
                logger.debug(f"Av mode set to {'True' if av_modu else 'False'}") 

        except Exception as e:
            logger.debug(f"Error saving to Redis: {e}")       




if __name__ == "__main__":


    with open('config.json', 'r') as json_file: #config.json dosyasını oku
        config = json.load(json_file) #config değişkenine yükle

    uav_ip = config['uav_handler']['uav_ip'] #uav ip
    ground_ip = config['uav_handler']['ground_ip'] #ground ip
    telemetry_port = config['uav_handler']['telemetry_port'] #telemetry port
    control_port = config['uav_handler']['control_port'] #control port
    target_port = config['uav_handler']['target_port'] #target port
    frame_port = config['uav_handler']['frame_port']  #frame port


    # for i in range(3):
    #     timee = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    #     logger.debug(f"Deneme {i} , {timee}")
    #     time.sleep(1)


    print(uav_ip, ground_ip, telemetry_port, control_port, target_port, frame_port)



    data_sender = send_rocket(ground_ip, target_port, frame_port, redis_host='localhost', redis_port=6379, target_fps=30) #data sender oluştur
    #asyncio.run(data_sender.send_frame_rocket())
    #data_handler = DataHandler(uav_ip, telemetry_port, control_port, redis_host='localhost', redis_port=6379) #data handler oluştur



  
    # time.sleep(30)
    #data_sender.run_system = False
    # #data_handler.run_system = False
    # data_handler.telemetry_sock.close()
    # data_handler.control_sock.close()
    # data_sender.data_sock.close()
    # data_sender.frame_sock.close()
    # logger.debug("Sistem kapatıldı.")