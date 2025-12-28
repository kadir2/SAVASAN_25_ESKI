from mavlinkHandler import MAVLinkHandlerDronekit as MAVLinkHandler
import logging
import os
import shutil
import datetime
from enum import Enum
import threading
import time
import math
import geopy.distance
import redis
import json
import cv2
import struct
import numpy as np
import atexit
from geopy.distance import distance as dist_calc, lonlat


class MissionState(Enum):
    NEUTRAL = 0
    GOING_TO_TARGET = 1
    DIVING_IN = 2
    DIVING_OUT = 3
    REAPPROACH = 4


class Logger:
    def init_logger(self):
        # create main logs folder
        base_logs_dir = 'kamikaze_logs'
        if not os.path.exists(base_logs_dir):
            os.makedirs(base_logs_dir)
        self.logs_dir = base_logs_dir

        self.logger = logging.Logger('GOAT')
        self.logger_disance = logging.Logger('GOAT - Distance')
        self.logger.setLevel(logging.DEBUG)
        self.logger_disance.setLevel(logging.DEBUG)

        c_handler = logging.StreamHandler()

        # all log files live under kamikaze_logs/
        log_file_path = os.path.join(base_logs_dir, 'GOAT_kamikaze.log')
        log_file_path_distance = os.path.join(base_logs_dir, 'GOAT_kamikaze_distance.log')
        old_logs_dir = os.path.join(base_logs_dir, "old_logs_kamikaze")

        if not os.path.exists(old_logs_dir):
            os.makedirs(old_logs_dir)

        if os.path.exists(log_file_path):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            new_log_file_name = f"GOAT_kamikaze_{timestamp}.log"
            new_log_file_path = os.path.join(old_logs_dir, new_log_file_name)
            shutil.move(log_file_path, new_log_file_path)

        f_handler = logging.FileHandler(log_file_path)
        f_handler_distance = logging.FileHandler(log_file_path_distance)
        c_handler.setLevel(logging.DEBUG)
        f_handler.setLevel(logging.DEBUG)
        f_handler_distance.setLevel(logging.DEBUG)

        c_format = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
        f_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        c_handler.setFormatter(c_format)
        f_handler.setFormatter(f_format)
        f_handler_distance.setFormatter(f_format)

        self.logger.addHandler(c_handler)
        self.logger.addHandler(f_handler)
        self.logger_disance.addHandler(f_handler_distance)


class IntiharPilotu(Logger):
    def __init__(self):
        self.init_logger()
        self.control_valve = False
        self.state = MissionState.NEUTRAL
        self.logger.debug('Mission state is NEUTRAL.')
        self.r = redis.Redis(host='localhost', port=6379, db=0)
        self.state_event = threading.Event()

        self.qr_detector_open = False
        self.frame_count = 0
        self.threads_started = False  # Threadlerin başlatılıp başlatılmadığını kontrol etmek için

        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        path = os.path.join(self.logs_dir, f'diving_{timestamp}')
        self.path = path
        if not os.path.exists(path):
            os.makedirs(path)

        # while True:
        #     try:
        #         time.sleep(0.4)
        #         qr_konumu = self.r.get('qr_konumu')

        #         if qr_konumu:
        #             # Parse the JSON string
        #             qr_konumu_data = json.loads(qr_konumu.decode('utf-8'))
                    
        #             # Extract latitude and longitude
        #             qr_lat = qr_konumu_data.get('qrEnlem')
        #             qr_lon = qr_konumu_data.get('qrBoylam')
        #             print(qr_lat, qr_lon, ' , serverdan geldi')
        #             # Update the target latitude and longitude
        #             self.target_lat = qr_lat
        #             self.target_lon = qr_lon
        #             break
        #         else:
        #             self.logger.debug('QR konumu alınamadı.')
                    
        #     except json.JSONDecodeError as e:
        #         self.logger.error(f'JSON parsing error: {e}')
        #     except AttributeError as e:
        #         self.logger.error(f'Attribute error: {e}')
        #     except Exception as e:
        #         self.logger.error(f'An unexpected error occurred: {e}')



        #GAZEBO KOOORDINATLARI
        self.target_lat = 41.102904
        self.target_lon = 28.5456026
        self.approach_lat=41.0996076
        self.approach_lon = 28.550591

        # HEZARFEN SAĞ TARAF
        # self.approach_lat = 41.09995
        # self.approach_lon = 28.55048



        # IMUK
        # self.target_lat = 40.9673981
        # self.target_lon = 29.3367329


        # SIMULATION NX
        # self.target_lat = 41.03523462
        # self.target_lon = 28.57060082
        # self.approach_lat = 41.03288358
        # self.approach_lon = 28.56506474

        self.logger.debug(f"target_lat: {self.target_lat}, target_lon: {self.target_lon}")


        self.start_altitude = 90
        self.target_altitude = 30
        self.stable_altitude = 100

        self.diving_degree = 50
        self.pitch_up = 10
        bias = -25
        #self.diving_distance = 160
        self.diving_distance = self.start_altitude/math.tan(math.radians(self.diving_degree+bias))
        self.logger.debug(f"start_altitude: {self.start_altitude}" + f"target_altitude: {self.target_altitude}" + f"stable_altitude: {self.stable_altitude}")
        self.logger.debug(f"diving_distance: {self.diving_distance}")

        self.mavlink_handler = MAVLinkHandler('127.0.0.1:14553', do_log=True)
        self.logger.debug('Connected to the aircraft.')

        threading.Thread(target=self.update_pos_thread).start()

        self.reapproach = True
        self.reapproach_number = 1
        self.approach_counter = 0
        self.r.set('kamikaze_buton', 'False')
        self.r.set('sunucu_saati', 'sunucu saati yok')

        # Exit handler
        atexit.register(self.exit_handler)

    def exit_handler(self):
        self.mavlink_handler.master.close()
        self.logger.debug('Connection closed.')

    def from_redis(self, n):
        encoded = self.r.get(n)
        if encoded is None:
            return None
        frame = self.convert_to_frame(encoded)
        return frame

    def exit_auto(self):
        self.mavlink_handler.set_mode('AUTO')

    def convert_to_frame(self, frame_data):
        h, w = struct.unpack('>II', frame_data[:8])
        frame = np.frombuffer(frame_data, dtype=np.uint8, offset=8).reshape(h, w, 3).copy()
        return frame
    
    def publish_kamikaze_packet(self, server_time_start, server_time_finish, qr_data):
        redis_host = "localhost"
        redis_port = 6379
        r = redis.StrictRedis(host=redis_host, port=redis_port, decode_responses=True)
        
        # Convert server time data to kamikaze packet format
        kamikaze_packet = {
            "kamikazeBaslangicZamani": server_time_start,
            "kamikazeBitisZamani": server_time_finish,
            "qrMetni": qr_data
        }
        
        try:
            # JSON formatına dönüştür
            message = json.dumps(kamikaze_packet)
            self.logger.debug(f'Server message: {message}')
            
            # Mesajı kamikaze_paketi kanalına gönder
            r.set('kamikaze_packet', message, ex=3)
            print(f"Published kamikaze packet to 'kamikaze_packet' channel: {message}")
        except redis.RedisError as e:
            print(f"Redis error: {e}")

    def redis_listener(self):
        while True:
            time.sleep(0.4)
            try:
                message = self.r.get('kamikaze_buton').decode('utf-8')
            except Exception as e:
                self.logger.error(f'Error while getting kamikaze_buton: {e}')
                continue
            # print('control valve: ',self.control_valve)
            # print('message: ',message)
            if message:
                command = message
                if command == 'True' and not self.control_valve:
                    self.logger.debug('Received start command from Redis.')

                    self.start_mission()

                elif command == 'False' and self.control_valve:
                    self.logger.debug('Received stop command from Redis.')

                    self.stop_mission()

    def stop_mission(self):
        self.control_valve = False
        self.state = MissionState.NEUTRAL
        self.logger.debug('Görev durduruldu.')

        
        current_thread = threading.current_thread()

       
        if hasattr(self, 'go_to_target_thread') and self.go_to_target_thread.is_alive() and self.go_to_target_thread != current_thread:
            self.logger.debug('go_to_target_thread durduruluyor.')
            self.go_to_target_thread.join()
            self.logger.debug('go_to_target_thread durduruldu.')

        if hasattr(self, 'reapproach_thread') and self.reapproach_thread.is_alive() and self.reapproach_thread != current_thread:
            self.logger.debug('reapproach_thread durduruluyor.')
            self.reapproach_thread.join()
            self.logger.debug('reapproach_thread durduruldu.')

        if hasattr(self, 'qr_detector_thread') and self.qr_detector_thread.is_alive() and self.qr_detector_thread != current_thread:
            self.logger.debug('qr_detector_thread durduruluyor.')
            self.qr_detector_thread.join()
            self.logger.debug('qr_detector_thread durduruldu.')

        self.threads_started = False 



    def start_mission(self):
        self.control_valve = True
        print("start mission")
        self.approach_counter = 0
        self.mavlink_handler.set_parameter_value('WP_LOITER_RAD', 20)
        self.logger.debug(f'Loiter radius set to {20} for kamikaze mission.')
        self.state = MissionState.GOING_TO_TARGET

        
        self.go_to_target_thread = threading.Thread(target=self.go_to_target)
        self.go_to_target_thread.start()
        self.dive_in_thread =  threading.Thread(target=self.dive_in)
        self.dive_in_thread.start()
        
        self.dive_out_thread = threading.Thread(target=self.dive_out)
        self.dive_out_thread.start()
        # self.reapproach_thread = threading.Thread(target=self.reapproach_process)
        # self.reapproach_thread.start()
        self.qr_detector_thread = threading.Thread(target=self.qr_detector)
        self.qr_detector_thread.start()
        self.threads_started = True  # Threadler başlatıldı olarak işaretle

    def update_pos_thread(self):
        while True:
            time.sleep(0.01)
            self.vehicle_lat, self.vehicle_lon, alt = self.mavlink_handler.get_location()
            if alt == 0.0:
                self.logger.debug('ALTITUDE LOG ZERO !!!')
            else:
                self.alt = alt
            self.heading = self.mavlink_handler.get_heading()
            self.distance_to_target = geopy.distance.geodesic((self.target_lat, self.target_lon), (self.vehicle_lat, self.vehicle_lon)).meters
            self.logger_disance.debug('distance to target (vehicle)' + str(self.distance_to_target))

    # def qr_detector(self):
    #     while self.control_valve:
    #         time.sleep(0.1)
    #         if self.control_valve:
    #             vehicle = (self.vehicle_lat, self.vehicle_lon)
    #             target = (self.target_lat, self.target_lon)

    #             distance = geopy.distance.geodesic(target, vehicle).meters
    #             if distance <= 500:
    #                 if not self.qr_detector_open:
    #                     pass
    #             else:
    #                 if self.qr_detector_open:
    #                     pass

    def calculate_heading(self, lat1, lon1, lat2, lon2):
        try:
            delta_lon = math.radians(lon2 - lon1)
            lat1 = math.radians(lat1)
            lat2 = math.radians(lat2)
            x = math.sin(delta_lon) * math.cos(lat2)
            y = math.cos(lat1) * math.sin(lat2) - (math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon))
            initial_heading = math.atan2(x, y)
            initial_heading = math.degrees(initial_heading)
            compass_heading = (initial_heading + 360) % 360
            self.logger.info(f'Heading to target: {compass_heading}')
            return compass_heading
        except Exception as e:
            self.logger.error(f'Error in calculate_heading: {e}')


    def calculate_new_coordinate(self, lat, lon, heading, distance_m):
        start_point = lonlat(lon, lat)
        new_point = dist_calc(meters=distance_m).destination(start_point, heading)
        new_lat, new_lon = new_point.latitude, new_point.longitude

        distance = geopy.distance.geodesic((self.target_lat, self.target_lon), (lat, lon)).meters
        self.logger.debug('distance new coordinate: ' + str(distance))
        self.logger.debug(f"coord_from_a_point: {new_point}")
        return new_lat, new_lon                

    def go_to_target(self):
        while self.control_valve:
            time.sleep(0.1)
            if self.state == MissionState.GOING_TO_TARGET:
                if self.mavlink_handler.get_mode() != 'GUIDED':
                    self.logger.debug('Mode is not GUIDED.')
                    continue

                                
                self.vehicle_lat, self.vehicle_lon, _ = self.mavlink_handler.get_location()
                distance_to_target = geopy.distance.geodesic((self.target_lat, self.target_lon), (self.vehicle_lat, self.vehicle_lon)).meters

                self.logger.debug("going to approach destination")
                self.mavlink_handler.simple_go_to(self.approach_lat,self.approach_lon,self.start_altitude ,block=False, distance_radius=50)

                while True:
                    time.sleep(0.1)
                    if not self.control_valve:
                        self.logger.debug('Mission stopped while going to approach destination.')
                        self.stop_mission()
                        return

                    vehicle_lat, vehicle_lon, _ = self.mavlink_handler.get_location()
                    point1 = (vehicle_lat, vehicle_lon)
                    target = (self.approach_lat, self.approach_lon)
                    distance = geopy.distance.geodesic(target, point1).meters

                    if distance <= 50:
                        self.logger.debug('Reached approach destination.')
                        break

                self.logger.debug("going to target destination")
                self.mavlink_handler.simple_go_to(self.target_lat, self.target_lon, self.start_altitude, block=False, distance_radius=self.diving_distance)
                while True:
                    time.sleep(0.1)
                    if not self.control_valve:
                        self.logger.debug('Mission stopped while going to target destination.')
                        self.stop_mission()
                        return

                    vehicle_lat, vehicle_lon, _ = self.mavlink_handler.get_location()
                    point1 = (vehicle_lat, vehicle_lon)
                    target = (self.target_lat, self.target_lon)
                    distance = geopy.distance.geodesic(target, point1).meters

                    if distance <= self.diving_distance:
                        self.logger.debug('Reached target destination.')
                        break    
                self.logger.debug('Target reached, diving in.')
                self.state = MissionState.DIVING_IN
                self.logger.debug(f'state == {self.state}')
        print("Go to target thread stopped")   

    def get_current_time_in_custom_format(self):
        now = datetime.now()
        return {
            'gun': now.day,
            'saat': now.hour,
            'dakika': now.minute,
            'saniye': now.second,
            'milisaniye': now.microsecond // 1000  # Mikrodan milisaniyeye çeviriyoruz
        }

    def dive_in(self):
        while True  :
            time.sleep(1)
            self.logger.debug(f'self.state: {self.state}')
            if self.state == MissionState.DIVING_IN:
                self.logger.debug("Diving in")
                try:
                    start_time = self.get_current_time_in_custom_format()
                    # start = self.r.get('sunucu_saati')
                    # start_time = '' if start is None else json.loads(start.decode('utf-8'))
                except Exception as e:
                    print(f'Sunucu saati alınamadı: {e}')

                if round(self.alt) >= self.target_altitude:
                    frame = self.from_redis('frame')
                    frame_name = "frame_" + str(self.frame_count) + ".jpg"
                    self.frame_count += 1
                    self.logger.debug(f' RADİAN PITCH == {math.radians(self.diving_degree)}')
                    self.mavlink_handler.set_target_attitude(roll=0, pitch=-self.diving_degree, yaw=0, thrust=0.2)
                    try:
                        cv2.imwrite(os.path.join(self.path, frame_name), frame)
                    except Exception as e:
                        self.logger.error(f'Error while saving frame: {e}')

                    self.logger.debug(f'altitude: {self.alt}')
                else:
                    self.state = MissionState.DIVING_OUT
                    self.logger.debug(f'Altitude is less than {self.target_altitude} meters')
                    self.logger.debug(f'altitude: {self.alt}')

                    # is_qr_read = self.r.get('didRead').decode('utf-8')
                    # self.logger.debug(f"is_qr_read: {is_qr_read}")
                    # try:
                    #     a =self.r.get('qr_data').decode('utf-8')
                    #     print(a)
                    # except Exception as e:
                    #     print(f'qr_data alınamadı: {e}')    

                    # if is_qr_read == "True":
                    #     try:
                    #         self.logger.debug("QR Code detected")
                    #         self.reapproach = True
                    #         qr_info = self.r.get('qr_data').decode('utf-8')
                    #         try:
                    #             end_time = self.get_current_time_in_custom_format()
                    #             # end = self.r.get('sunucu_saati')
                    #             # end_time = '' if end is None else json.loads(end.decode('utf-8'))
                    #         except Exception as e:
                    #             print(f'Sunucu saati alınamadı: {e}')

                    #         print('start', start_time)
                    #         print('end:', end_time)
                    #         print('qr_info', qr_info)

                    #         self.publish_kamikaze_packet(start_time, end_time, qr_info)
                    #     except Exception as e:
                    #         print(f'Paket yollarken sıkıntı çıktı: {e}')                  

    def dive_out(self):
        while True:   
            time.sleep(0.1)
            if self.state == MissionState.DIVING_OUT:
                print("Diving out1")
                if round(self.alt) <= self.stable_altitude:
                    self.mavlink_handler.set_target_attitude(roll=0, pitch=self.pitch_up, yaw=0, thrust=0.8)
                    self.logger.debug("Diving out")
                    self.logger.debug(f'self.alt: {self.alt}')
                else:
                    self.logger.debug(f'Dive out complete.')
                    if self.reapproach and self.approach_counter < self.reapproach_number:
                        self.state = MissionState.GOING_TO_TARGET
                        self.approach_counter += 1
                        print(self.approach_counter)
                    else:
                        self.logger.debug(f'Mission complete.')
                        self.stop_mission()
                        
    # def reapproach_process(self):
    #     while self.control_valve:
    #         time.sleep(0.1)
    #         if self.state == MissionState.REAPPROACH:
    #             self.logger.debug("Reapproaching target")
    #             self.mavlink_handler.simple_go_to(self.approach_lat, self.approach_lon, self.start_altitude, block=False, distance_radius=50)
    #             while True:
    #                 time.sleep(0.1)
    #                 if not self.control_valve:
    #                     self.logger.debug('Mission stopped while reapproaching target.')
    #                     self.stop_mission()
    #                     return

    #                 vehicle_lat, vehicle_lon, _ = self.mavlink_handler.get_location()
    #                 point1 = (vehicle_lat, vehicle_lon)
    #                 target = (self.approach_lat, self.approach_lon)
    #                 distance = geopy.distance.geodesic(target, point1).meters

    #                 if distance <= 50:
    #                     self.logger.debug('Reached approach destination.')
    #                     break
    #             distance = geopy.distance.geodesic((self.target_lat, self.target_lon), (self.vehicle_lat, self.vehicle_lon)).meters
    #             self.logger_disance.debug('distance to target reapproach: ' + str(distance))

    #             self.state = MissionState.GOING_TO_TARGET 
    #     print("Reapproach thread stopped")        


if __name__ == '__main__':
    intihar_pilotu = IntiharPilotu()

    threading.Thread(target=intihar_pilotu.redis_listener).start()
    while True:
        time.sleep(0.3)
        if intihar_pilotu.mavlink_handler.get_mode() == 'GUIDED':
            print("GUIDED")
            break
        else:
            print("NOT GUIDED")
