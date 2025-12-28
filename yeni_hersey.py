import socket
import numpy as np
import cv2
import redis
import time
from datetime import datetime
import math
import struct
import os
import json
import threading
import shutil
import logging
import requests
from mavlinkHandler import MAVLinkHandlerDronekit as mavlinkHandler



class Loggerr:
    def __init__(self):
        # Logger oluştur
        self.logger = logging.Logger('ground_log')
                    # logging.getLogger('ground_log') yeni versiyon
        self.logger.setLevel(logging.DEBUG)  # Log seviyesi DEBUG olarak ayarlanır
        
        # Handlers: Konsol ve Dosya
        c_handler = logging.StreamHandler()  # Konsol için handler
        log_file_path = 'ground.log'  # Log dosyasının adı
        old_logs_dir = "old_logs_gnd"  # Eski log dosyalarının taşınacağı klasör

        # Eski log dosyalarını yedekle
        if not os.path.exists(old_logs_dir):  # Eğer klasör yoksa oluştur
            os.makedirs(old_logs_dir)
        if os.path.exists(log_file_path):  # Eğer log dosyası varsa
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")  # Zaman damgası oluştur
            new_log_file_name = f"ground_log{timestamp}.log"  # Yeni log dosyasının adı
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

logger_instance = Loggerr()  # Logger nesnesi oluştur
logger = logger_instance.logger   # Logger nesnesini al



class Server:
    def __init__(self, base_url, team_id, username, password, vehicle):
        try:
            self.mavlink_handler = mavlinkHandler(vehicle)  # MAVLink handler'ı başlat
        except Exception as e:
            logger.debug(f"Error while creating MAVLink handler: {e}")
            self.mavlink_handler = None

        self.run_system = True
        self.server_time = None
        self.base_url = base_url
        self.team_id = team_id
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.logged_in = False
        self.telemetry_resp = None
        self.telemetry_json ={}
        self.tracker_bbox = [0, 0, 0, 0, 0]

        self.login()

        self.r = redis.Redis(host='localhost', port=6379, db=0)

        threading.Thread(target=self.updt_srvr_time).start() #server saatini al
        threading.Thread(target=self.get_telemetry_mavlink).start() #telemetri al
        # threading.Thread(target=self.get_data_from_redis).start() #redis'ten veri al
        # threading.Thread(target=self.get_tracker_bbox).start() #tracker bbox al
        threading.Thread(target=self.send_server_data).start()






    def login(self):
        url = f"{self.base_url}/api/giris"
        data = {
            "kadi": self.username,
            "sifre": self.password
        }
        response = self.session.post(url, json=data)
        if response.status_code == 200:
            self.logged_in = True
            logger.debug(f"successfully logged in. team-id: {self.team_id}")
        else:
            logger.debug(f"Login failed with status code: {response.status_code}")
            time.sleep(15)
            self.logged_in = False
            return response

    def updt_srvr_time(self):
        while self.run_system:
            try:
                url = f"{self.base_url}/api/sunucusaati"
                response = self.session.get(url)
                if response.status_code == 200:
                    self.server_time = response.json()
                    #logger.debug(f"Server time: {self.server_time}")
                else:
                    logger.debug(f"Error while updating server time: {response.status_code}")
            except Exception as e:
                logger.debug(f"Error while updating server time: {e}")
            time.sleep(0.1)


    def get_telemetry_mavlink(self):
        while self.run_system:
            try:
                if self.mavlink_handler is not None:
                    roll, pitch, _ = self.mavlink_handler.get_attitude()
                    lat, lon, alt = self.mavlink_handler.get_location()
                    mode = self.mavlink_handler.get_mode()
                    gps_time = datetime.now()
                    gps_time = [gps_time.hour, gps_time.minute, gps_time.second, gps_time.microsecond // 1000]
                    iha_yonlenme = self.mavlink_handler.get_heading()
                    iha_hiz = self.mavlink_handler.get_air_speed()
                    iha_batarya = self.mavlink_handler.get_battery()

                    self.telemetry_json = {
                        "takim_numarasi": self.team_id,
                        "iha_enlem": lat,
                        "iha_boylam": lon,
                        "iha_irtifa": alt,
                        "iha_dikilme": pitch,
                        "iha_yonelme": iha_yonlenme,
                        "iha_yatis": roll,
                        "iha_hiz": iha_hiz,
                        "iha_batarya": iha_batarya,
                        "iha_otonom": 0 if mode == "FBWA" else 1,
                        "iha_kilitlenme": self.tracker_bbox[4],
                        "hedef_merkez_X": self.tracker_bbox[0],
                        "hedef_merkez_Y": self.tracker_bbox[1],
                        "hedef_genislik": self.tracker_bbox[2],
                        "hedef_yukseklik": self.tracker_bbox[3],
                        "gps_saati": {
                            "saat": gps_time[0],
                            "dakika": gps_time[1],
                            "saniye": gps_time[2],
                            "milisaniye": gps_time[3]
                        }
                    }
                    logger.debug(f"Telemetry data: {self.telemetry_json}")

                    logger.debug(f"Telemetry data: {self.telemetry_json}")
                    self.r.set("telemetry_data", json.dumps(self.telemetry_json))
                    
            except Exception as e:
                logger.debug(f"Error while getting telemetry data: {e}")
            finally:
                time.sleep(1)

    # def get_data_from_redis(self):
    #     while self.run_system:
    #         try:
    #             self.kamikaze_data = self.r.get("kamikaze_data")
    #             #self.kamikaze_data = json.loads(self.kamikaze_data) if self.kamikaze_data else None
    #             if self.kamikaze_data is not None:
    #                 self.send_kamikaze_data(self.base_url, self.session)
    #                 logger.debug(f"Kamikaze data: {self.kamikaze_data}")
    #         except Exception as e:
    #             logger.debug(f"Error while getting kamikaze data from Redis: {e}")

    #         try:
    #             self.lock_data = self.r.get("lock_data")
    #             if self.lock_data is not None:
    #                 self.send_lock_data(self.base_url, self.session)
    #                 logger.debug(f"Lock data: {self.lock_data}")
    #         except Exception as e:
    #             logger.debug(f"Error while getting lock data from Redis: {e}")
    #         time.sleep(1)


    def send_server_data(self):
        while self.run_system:
            try:
                start_time = time.time()
                try:
                    self.telemetry_resp = self.send_telemetry()
                    if self.telemetry_resp is not None:
                        logger.debug(f"Telemetry response: {self.telemetry_resp}")
                        self.r.set("telemetry_response", json.dumps(self.telemetry_resp))
                    else:
                        logger.debug("Telemetry response is None.")
                except Exception as e:
                    logger.debug(f"Error while sending telemetry data: {e}")
                
                end_time = time.time()
                elapsed_time = end_time - start_time
                wait_time = max(0, 1 - elapsed_time)
                time.sleep(wait_time)
                
            except Exception as e:
                logger.debug(f"Error in send_server_data loop: {e}")
                time.sleep(1)



    def send_telemetry(self):
        url = f"{self.base_url}/api/telemetri_gonder"
        response = self.session.post(url, json=self.telemetry_json)
        if response.status_code == 200:
            logger.debug(f"Telemetry data sent successfully. tema-id: {self.team_id}")
        else:
            logger.debug(f"Error while sending telemetry data: {response.status_code} - {response.text}")
        return json.dumps(self.process_response(response.json()), indent=4)


    def process_response(self, response):
        response["konumBilgileri"] = [data for data in response["konumBilgileri"] if data["takim_numarasi"] != self.team_id]
        return response

    def get_qr_cordinates(self):
        url = f"{self.base_url}/api/qr_koordinati"
        response = self.session.get(url)
        if response.status_code == 200:
            return response.json()
        else:
            logger.debug(f"Error while getting QR coordinates: {response.status_code} - {response.text}")
            return None

    def get_hss_cordinates(self): #hava savunma sistemi
        url = f"{self.base_url}/api/hss_koordinatlari"
        response = self.session.get(url)
        if response.status_code == 200:
            return response.json()
        else:
            logger.debug(f"Error while getting HSS coordinates: {response.status_code} - {response.text}")
            return None
        


    def get_tracker_bbox(self):
        try:
            pubsub = self.r.pubsub()
            pubsub.subscribe('self.tracker_bbox')
            for message in pubsub.listen():
                if message['type'] == 'message':
                    self.tracker_bbox = json.loads(message['data'])
                    if self.tracker_bbox is not None:
                        logger.debug(f"Tracker bbox: {self.tracker_bbox}")
                    else:
                        logger.debug("Tracker bbox is None.")
                        self.tracker_bbox = [0, 0, 0, 0, 0]
                    # logger.debug(f"Tracker bbox: {self.tracker_bbox}")
                    # if self.tracker_bbox != [0, 0, 0, 0] and self.tracker_bbox != [0, 0, 0, 0, 0]:
                    #     self.tracker_bbox.append(1)
                    # else:
                    #     self.tracker_bbox = [0, 0, 0, 0, 0]
        except Exception as e:
            logger.debug(f"Error while getting tracker bbox: {e}")
            self.tracker_bbox = [0, 0, 0, 0, 0]
            


    def send_lock_data(self, base_url, session, lock_data):
        try:
            url = f"{base_url}/api/kilitlenme_bilgisi"
            response = session.post(url, json=lock_data)
            if response.status_code == 200:
                self.r.delete("lock_data")
                logger.debug(f"Lock data sent successfully.")
            else:
                logger.debug(f"Error while sending lock data: {response.status_code} - {response.text}")
            return json.dumps(response.json(), indent=4)    #kontrol et
        except Exception as e:
            logger.debug(f"Error while sending lock data: {e}")
            return None



    def send_kamikaze_data(self, base_url, session, kamikaze_data):
        try:
            url = f"{base_url}/api/kamikaze_bilgisi"

            response = session.post(url, json=kamikaze_data)
            if response.status_code == 200:
                self.r.delete("kamikaze_data")
                logger.debug(f"Kamikaze data sent successfully.")
            else:
                logger.debug(f"Error while sending kamikaze data: {response.status_code} - {response.text}")
            return json.dumps(response.json(), indent=4)  # kontrol et
        except Exception as e:
            logger.debug(f"Error while sending kamikaze data: {e}")
            return None
    
    def stop(self):
        self.run_system = False
        if self.mavlink_handler is not None:
            self.mavlink_handler.close()







                
class DataHandler:
    """
    serverdan alınan verileri arayüze ve rockete gönderir, 
    """

    def __init__(self, itunom_class, team_number, rocket_ip, rocket_port, vehicle, base_url):
        self.rocket_ip = rocket_ip
        self.rocket_port = rocket_port
        self.team_number = team_number
        self.base_url = base_url
        self.vehicle = vehicle
        self.itunom = itunom_class
        self.run_system = True
        self.logged_in = False
        self.opponent_data = None
        self.r = redis.Redis(host='localhost', port=6379, db=0)
        logger.debug(f"DataHandler initialized with team number: {self.team_number}, rocket IP: {self.rocket_ip}, rocket port: {self.rocket_port}, vehicle: {self.vehicle}, base URL: {self.base_url}")

        
        # try:
        #     self.sock_interface = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # except socket.error as e:
        #     logger.debug(f"Error while creating interface socket: {e}")
        #     self.sock_interface = None

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            logger.debug(f"Socket created for rocket at {self.rocket_ip}:{self.rocket_port}")
        except socket.error as e:
            logger.debug(f"Error while creating socket: {e}")
            self.sock = None

        logger.debug(f"durum : {itunom.logged_in}")
        if itunom.logged_in:
            self.logged_in = True
            logger.debug("girdiiik")
            threading.Thread(target=self.update_data_thread).start()
            threading.Thread(target=self.check_states).start()
        else:
            logger.debug("Login failed, cannot start data handling.")


    def process_data(self, telemetry_response, qr_coordinate, hss, sunucusaati):
        try:
            if isinstance(telemetry_response, str):
                #self.r.set(telemetry_response)  #kontrol edilmeli
                telemetry_response = json.loads(telemetry_response)
            if isinstance(qr_coordinate, str):
                qr_coordinate = json.loads(qr_coordinate)
            if isinstance(hss, str):
                hss = json.loads(hss)
            if isinstance(sunucusaati, str):
                sunucusaati = json.loads(sunucusaati)
            
            self.opponent_data = {
                    "konumBilgileri": telemetry_response,
                    "sunucusaati": sunucusaati,
                    "qr_koordinati": qr_coordinate,
                    "hss_koordinatlari": hss
                }
            return self.opponent_data
        except json.JSONDecodeError as e:
            logger.debug(f"Error while processing data: {e}")
            return None


    # def send_data_to_rocket(self, data):
    #     try:
    #         data_json = json.dumps(data)
    #         self.sock_interface.settimeout(0.2)
    #         self.sock.sendto(data_json.encode('utf-8'), (self.rocket_ip, self.rocket_port)) #kontrol et
    #     except socket.error as e:
    #         logger.debug(f"Error while sending data to rocket: {e}")
    
    # def send_data_to_interface(self, data):
    #     try:
    #         data_json = json.dumps(data)
    #         self.sock_interface.settimeout(0.2) #kontrol et
    #         self.sock_interface.sendto(data_json.encode('utf-8'), (self.interface_ip, self.interface_port))
    #     except socket.error as e:
    #         logger.debug(f"Error while sending data to interface: {e}")
    
    def update_data_thread(self):
        while self.run_system:
            # telemetri verisi çekme
            try:
                telemetry_response = itunom.telemetry_resp
                
                self.r.set("telemetry_response", json.dumps(telemetry_response))

                #logger.debug(f"Telemetry response: {json.dumps(telemetry_response)}")
            except Exception as e:
                logger.debug(f"Error while getting telemetry response: {e}")
                telemetry_response = None
            # qr koordinatları çekme
            try:
                qr_coordinate = itunom.get_qr_cordinates()
                logger.debug(f"QR coordinates: {qr_coordinate}")
            except Exception as e:
                logger.debug(f"Error while getting QR coordinates: {e}")
                qr_coordinate = None
            # hss koordinatları çekme
            try:
                hss = itunom.get_hss_cordinates()
                logger.debug(f"HSS coordinates: {hss}")
            except Exception as e:
                logger.debug(f"Error while getting HSS coordinates: {e}")
                hss = None
            # sunucu saati çekme
            try:
                sunucusaati = itunom.server_time
                logger.debug(f"Server time: {sunucusaati}")
            except Exception as e:
                logger.debug(f"Error while getting server time: {e}")
                sunucusaati = None
            time.sleep(0.1)
            if telemetry_response is not None:
                try:
                    self.process_data(telemetry_response, qr_coordinate, hss, sunucusaati)

                except Exception as e:
                    logger.debug(f"Error while processing data: {e}")

            else:
                logger.debug("Telemetry response is None.")


    def check_states(self):
            """Redis'teki ana veriyi periyodik olarak kontrol eder, işler ve ilgili anahtarları günceller."""
            old_hss_data = {}
            self.takim_numaralari = []
            while True:
                try:
                    # data_str = self.r.get("process_data")
                    opponent_data = self.opponent_data
                    self.r.set("process_data", json.dumps(opponent_data))
                    #print(f"Opponent Data: {opponent_data}")

                    if not opponent_data:
                        time.sleep(1)
                        logger.debug("rediste 'process_data' anahtarı bulunamadı, 1 saniye bekleniyor...")
                        continue


                    # QR Verilerini İşle
                    try:
                        qr_koordinati = opponent_data.get("qr_koordinati", {})
                        yeni_qr_enlem = qr_koordinati.get("qrEnlem")
                        yeni_qr_boylam = qr_koordinati.get("qrBoylam")
                        
                        # Eski enlem veya boylamdan herhangi biri farklıysa güncelle
                        if yeni_qr_enlem is not None and yeni_qr_boylam is not None:
                            self.r.set("qr_enlem", yeni_qr_enlem)
                            self.r.set("qr_boylam", yeni_qr_boylam)
                            logger.debug(f"QR koordinatları güncellendi: {yeni_qr_enlem}, {yeni_qr_boylam}")

                            logging.debug(f"QR koordinatları güncellendi: {yeni_qr_enlem}, {yeni_qr_boylam}")


                    except (KeyError, AttributeError) as e:
                        logger.debug(f"QR koordinatları işlenirken hata oluştu: {e}")

                    # Uçak Sayısını Hesapla
                    try:
                        konum_bilgileri_list = opponent_data.get("konumBilgileri", {}).get("konumBilgileri", [])
                        ucak_sayisi = len(konum_bilgileri_list) 
                        self.r.set("ucak_sayisi", ucak_sayisi)
                        logger.debug(f"Uçak sayısı güncellendi: {ucak_sayisi}")
                    except (KeyError, AttributeError) as e:
                        logger.debug(f"Uçak sayısı hesaplanırken hata oluştu: {e}")
                        self.r.set("ucak_sayisi", 0)

                    # HSS Verilerini İşle
                    try:
                        hss_listesi = opponent_data.get("hss_koordinatlari", {}).get("hss_koordinat_bilgileri", [])
                        
                        for hss in hss_listesi:
                            hss_id = hss.get('id')
                            yeni_hss_enlem = hss.get('hssEnlem')
                            yeni_hss_boylam = hss.get('hssBoylam')
                            hss_radius = hss.get('"hssYaricap')
                            
                            if hss_id is None or yeni_hss_enlem is None:
                                continue
                            
                            eski_hss = old_hss_data.get(hss_id, {})
                            
                            if yeni_hss_enlem != eski_hss.get("enlem") or yeni_hss_boylam != eski_hss.get("boylam"):
                                self.r.set(f"hss_{hss_id}_enlem", yeni_hss_enlem)
                                self.r.set(f"hss_{hss_id}_boylam", yeni_hss_boylam)
                                self.r.set(f"hss_{hss_id}_hss_radius", hss_radius)
                                old_hss_data[hss_id] = {"enlem": yeni_hss_enlem, "boylam": yeni_hss_boylam}
                                logger.debug(f"HSS ID {hss_id} koordinatları güncellendi.")
                    except (KeyError, AttributeError) as e:
                        logger.debug(f"HSS listesi işlenirken hata oluştu: {e}")

                    # Telemetri Verilerini İşle
                    try:
                        takım_telemetri = []
                        self.r.delete("takim_telemetri")
                        takımlar = opponent_data.get("konumBilgileri", {}).get("konumBilgileri", [])
                        self.takim_numaralari = []
                        for takım in takımlar:
                            
                            self.takim_numaralari.append(takım.get("takim_numarasi", 0))
                            enlem = takım.get("iha_enlem", 0)
                            boylam = takım.get("iha_boylam", 0)
                            irtifa = takım.get("iha_irtifa", 0)
                            dikilme = takım.get("iha_dikilme", 0)
                            yonelme = takım.get("iha_yonelme", 0)
                            yatis = takım.get("iha_yatis", 0)
                            hiz = takım.get("iha_hiz", 0)
                            zaman_farki = takım.get("zaman_farki", 0)
                            liste = [
                                takım.get("takim_numarasi", 0),
                                enlem,
                                boylam,
                                irtifa,
                                dikilme,
                                yonelme,
                                yatis,
                                hiz,
                                zaman_farki
                            ]
                            takım_telemetri.append(json.dumps(liste))
                            print(f"Takım Telemetri: {liste}")

                        self.r.rpush("takim_telemetri", *takım_telemetri)  # Redis'e takım telemetri verilerini gönder
                        print("veriler gönderildi")


                        print(f"Takım Numarası: {self.takim_numaralari}")
                        self.r.rpush("takim_numaralari", *self.takim_numaralari)  # Redis e takım numaralarını gönder

                    except (KeyError, AttributeError) as e:
                        logger.debug(f"Takım numaraları işlenirken hata oluştu: {e}")


                except json.JSONDecodeError as e:
                    logger.debug(f"Redis'teki 'process_data' anahtarı geçerli bir JSON değil: {e}")
                except Exception as e:
                    logger.debug(f"Beklenmedik bir hata oluştu: {e}", exc_info=True)
                
                time.sleep(1)




    def send_data_to_redis(self, data):
        try:
            if isinstance(data, dict):
                self.r.set("process_data", json.dumps(data))
                logger.debug(f"Data sent to Redis: {data}")
            else:
                logger.debug("Data is not a dictionary.")
        except Exception as e:
            logger.debug(f"Error while sending data to Redis: {e}")


    def stop(self):
        self.run_system = False
        self.sock.close()





class Frame_Emici:

    """
    Rocket'dan gelen frame'leri alır ve işler
    """

    def __init__(self, ip, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((ip, port))
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 10000000)
        self.r = redis.Redis(host='localhost', port=6379, db=0)
        self.buffer = {}
        self.current_frame_id = None
        self.expected_packets = None
        self.frame_start_time = None
        self.frame_timeout = 0.5  # 500 ms
        self.max_length = 1300
        self.run_system = True

        logger.debug(f"Listening on {ip}:{port}")
        threading.Thread(target=self.em).start() 

    def em(self):
        while self.run_system:
            try:
                packet, addr = self.sock.recvfrom(self.max_length + 12)
                frame_id = int.from_bytes(packet[:4], 'big')
                num_of_packs = int.from_bytes(packet[4:8], 'big')
                packet_index = int.from_bytes(packet[8:12], 'big')
                data = packet[12:]

                # Yeni frame başladıysa
                if self.current_frame_id != frame_id:
                    self.buffer = {}
                    self.current_frame_id = frame_id
                    self.expected_packets = num_of_packs
                    self.frame_start_time = time.time()
                    logger.debug(f"Receiving new frame: id={frame_id}, packet_count={self.expected_packets}")

                self.buffer[packet_index] = data

                # Timeout kontrolü!
                if self.frame_start_time and (time.time() - self.frame_start_time) > self.frame_timeout:
                    logger.debug("Frame timeout, clearing buffer.")
                    self.buffer = {}
                    self.current_frame_id = None
                    self.expected_packets = None
                    self.frame_start_time = None
                    continue

                if self.expected_packets and len(self.buffer) == self.expected_packets:
                    logger.debug("All packets received.")
                    frame_data = b"".join(self.buffer[i] for i in sorted(self.buffer.keys()))
                    frame = cv2.imdecode(np.frombuffer(frame_data, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if frame is not None and frame.size > 0:
                        _, img_encoded = cv2.imencode('.jpg', frame)
                        self.r.set("frame", img_encoded.tobytes())
                        # cv2.imshow("Received Frame", frame)
                        # cv2.waitKey(1)
                    else:
                        logger.debug("Frame decoding failed. Skipping this frame.")
                    self.buffer = {}
                    self.current_frame_id = None
                    self.expected_packets = None
                    self.frame_start_time = None
            except Exception as e:
                logger.debug(f"Error while receiving frame: {e}")
                continue
        
    def stop(self):
        self.run_system = False
        self.sock.close()
        logger.debug("Frame receiver stopped.")






class get_rocket:
    def __init__(self, ip, data_port, redis_host, redis_port, base_url, session):
        self.data_ip = ip
        self.data_port = data_port
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.base_url = base_url
        self.session = session
        
        # UDP soketi oluştur ve ayarla
        self.data_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.data_sock.bind((self.data_ip, self.data_port))
        
        # Non-blocking moda al
        self.data_sock.setblocking(False)

        # Redis bağlantısını oluştur
        self.r = redis.Redis(host=self.redis_host, port=self.redis_port)

        self.run_system = True

        threading.Thread(target=self.update_data).start()

    def receive_data_rocket(self):
        try:
            data, _ = self.data_sock.recvfrom(1024)
            data = data.decode('utf-8')
            logger.debug(f"-"*5)
            logger.debug(f"Received data: {data}")
            return data
        except json.JSONDecodeError as e:
            logger.debug(f"JSON decode error: {e}")
            return None
        except socket.error as e:
            logger.debug(f"Socket error: {e}")
            return None
            


    def update_data(self):
        self.last_data_time = datetime.now()
        while self.run_system:
            try:
                deyta = self.receive_data_rocket()
                if deyta:
                    self.last_data_time = 0
                    self.save_data_to_redis(json.loads(deyta))

                else:
                    logger.debug("No data received, retrying...")
                    if (datetime.now() - self.last_data_time).total_seconds() > 5:
                        logger.debug("No data received for 5 seconds, trying again...")
                        self.last_data_time = datetime.now()
         
                time.sleep(0.1)

            except Exception as e:
                logger.debug(f"Error: {e} hatası oluştu veri alınamadı  LOCATION:update_data")



    def save_data_to_redis(self, data):
        try:
            data = data.decode('utf-8')

            kamikaze = data.get("kamikaze")
            kilitlenme = data.get("kilitlenme")
            bbox = data.get("tracker_bbox")

            if kamikaze is not None:
                # self.r.set("kamikaze_paket", json.dumps(kamikaze))
                itunom.send_kamikaze_data(self.base_url, self.session, kamikaze)
                logger.debug(f"Kamikaze pakedi Redis'e kaydedildi: {kamikaze}")
            if kilitlenme is not None:
                # self.r.set("konumlu_paket", json.dumps(kilitlenme))
                itunom.send_lock_data(self.base_url, self.session, kilitlenme)
                logger.debug(f"kilitlenme pakedi Redis'e kaydedildi: {kilitlenme}")

            if bbox is not None:
                # self.r.set("tracker_bbox", json.dumps(bbox))
                itunom.tracker_bbox = bbox
                
                logger.debug(f"Tracker bbox verisi Redis'e kaydedildi: {bbox}")

        except json.JSONDecodeError as e:
            logger.debug(f"JSON decode error: {e} hatası oluştu veri redis'e kaydedilemedi  LOCATION:save_data_to_redis")
            return None
        except Exception as e:
            logger.debug(f"Error: {e} hatası oluştu veri redis'e kaydedilemedi  LOCATION:save_data_to_redis")
            return None


    def stop(self):
        self.run_system = False
        self.data_sock.close()
        logger.debug("Data receiver stopped.")



if __name__ == "__main__":

    try:
        with open('ground.json', 'r') as json_veri:
            config = json.load(json_veri)
        
        #JSON'dan verileri değişkenlere atama
        username = config['credentials']['username']
        password = config['credentials']['password']
        team_number = config['credentials']['team_number']
        vehicle = config['network']['vehicle']
        base_url = config['network']['base_url']
        yer_ip = config['network']['yer_ip']

        yer_goruntu_port = config['network']['yer_goruntu_port']
        server_frame_port = config['network']['server_frame_port']


        itunom = Server(base_url=base_url, team_id=team_number, username=username, password=password, vehicle=vehicle)
        frame_rec = Frame_Emici(ip=yer_ip, port=7101)
        dataci = get_rocket(ip=yer_ip, data_port=5555, redis_host='localhost', redis_port=6379, base_url=base_url, session=itunom.session)
        data_handler = DataHandler(itunom_class=itunom, team_number=team_number, rocket_ip=yer_ip, rocket_port=yer_goruntu_port, vehicle=vehicle, base_url=base_url)

    except KeyboardInterrupt:
        logger.debug("Program durduruluyor...")
        #dataci.stop()
        #frame_rec.stop()
        itunom.stop()
        