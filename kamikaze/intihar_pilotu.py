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

        self.threads_started = False  # Threadlerin başlatılıp başlatılmadığını kontrol etmek için

        #GAZEBO KOOORDINATLARI
        self.target_lat = 41.102904
        self.target_lon = 28.5456026
        self.approach_lat=41.0996076
        self.approach_lon = 28.550591

        # self.target_lat = 41.1015841
        # self.target_lon = 28.5525204
        # self.approach_lat = 41.1004099
        # self.approach_lon = 28.5511681

        self.reapproach = True
        self.reapproach_number = 3
        self.approach_counter = 0

        self.logger.debug(f"target_lat: {self.target_lat}, target_lon: {self.target_lon}")

        self.start_altitude = 105
        self.target_altitude = 25
        self.stable_altitude = 80
        
        self.diving_velocity = 15

        self.diving_degree = 40
        self.pitch_up = 10
        # bias = -20

        ####### DALIŞ MESAFESİ RADIUS PARAMETRESİNDEN HER TÜRLÜ BÜYÜK OLMALI (BASE OLARAK MİN 100) ######

        self.diving_distance = 175
        # self.diving_distance = self.start_altitude/math.tan(math.radians(self.diving_degree+bias))
        #self.diving_distance = self.dive_distance(self.diving_degree, self.diving_velocity, self.start_altitude, self.target_altitude)

        self.r.set('kamikaze_buton', 'False')
        self.logger.debug(f"start_altitude: {self.start_altitude}" + f"target_altitude: {self.target_altitude}" + f"stable_altitude: {self.stable_altitude}")
        self.logger.debug(f"diving_distance: {self.diving_distance}")

        self.mavlink_handler = MAVLinkHandler('127.0.0.1:14552', do_log=True)

        self.logger.debug('Connected to the aircraft.')

        threading.Thread(target=self.update_pos_thread).start()


        self.location_thread = threading.Thread(target=self.get_location_thread)
        self.location_thread.start()

        # Exit handler
        atexit.register(self.exit_handler)

    def get_location_thread(self):
        while True:
            lat = self.mavlink_handler.get_location()[0]
            lon = self.mavlink_handler.get_location()[1]
            alt = self.mavlink_handler.get_location()[2]
            ground_speed = self.mavlink_handler.get_ground_speed()
            air_speed = self.mavlink_handler.get_air_speed()
            #self.logger.debug(f'Location: lat={lat}, lon={lon}, alt={alt}, ground_speed={ground_speed}, air_speed={air_speed}')
            self.r.set('lat', lat)
            self.r.set('lon', lon)
            self.r.set('alt', alt)
            self.r.set('ground', ground_speed)
            self.r.set('air', air_speed)
            time.sleep(0.4)

    def dive_distance(self, pitch_deg: float, speed: float, h_start: float, h_end: float) -> float:
        """
        Dalış yapan uçağın bitiş irtifasına kadar yatayda kat ettiği mesafe.

        :param pitch_deg: Dalış pitch açısı (pozitif, derece cinsinden)
        :param speed:      Sabit uçuş hızı (m/s)
        :param h_start:    Dalışın başladığı irtifa (m)
        :param h_end:      Dalışın biteceği irtifa (m)
        :return:           Yatay mesafe (m)
        """
        delta_h = h_start - h_end
        if delta_h <= 0:
            return 0.0

        # Dereceyi radyana çevir
        pitch_rad = math.radians(pitch_deg)
        # Dikey hız bileşeni
        v_vert = speed * math.sin(pitch_rad)
        if v_vert <= 0:
            raise ValueError("Pitch açısı ve hız kombinasyonuyla pozitif dikey hız elde edilemedi.")

        # Dalış süresi
        t = delta_h / v_vert
        # Yatay hız bileşeni
        v_horiz = speed * math.cos(pitch_rad)
        # Yatay mesafe
        distance = v_horiz * t
        distance = max(100, distance)
        return distance

    def exit_handler(self):
        self.mavlink_handler.master.close()
        self.logger.debug('Connection closed.')

    def exit_auto(self):
        self.mavlink_handler.set_mode('AUTO')

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
        self.logger.debug("start mission")
        self.approach_counter = 0
        self.state = MissionState.GOING_TO_TARGET

        self.go_to_target_thread = threading.Thread(target=self.go_to_target)
        self.go_to_target_thread.start()
        self.dive_in_thread =  threading.Thread(target=self.dive_in)
        self.dive_in_thread.start()

        self.dive_out_thread = threading.Thread(target=self.dive_out)
        self.dive_out_thread.start()
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
                self.mavlink_handler.simple_go_to(self.approach_lat,self.approach_lon,self.start_altitude ,block=False, distance_radius=20)

                while True:
                    self.logger.debug('Waiting to reach approach destination...')
                    time.sleep(0.1)
                    if not self.control_valve:
                        self.logger.debug('Mission stopped while going to approach destination.')
                        self.stop_mission()
                        return

                    vehicle_lat, vehicle_lon, _ = self.mavlink_handler.get_location()
                    point1 = (vehicle_lat, vehicle_lon)
                    target = (self.approach_lat, self.approach_lon)
                    self.logger.debug(f"point1: {point1}, target: {target}")
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
        print("Go to target thread stopped")   

    def dive_in(self):
        while True  :
            time.sleep(1)
            self.logger.debug(f'self.state: {self.state}')
            if self.state == MissionState.DIVING_IN:
                self.logger.debug("Diving in")

                if round(self.alt) >= self.target_altitude:
                    self.logger.debug(f' RADİAN PITCH == {math.radians(self.diving_degree)}')
                    self.mavlink_handler.set_target_attitude(roll=0, pitch=-self.diving_degree, yaw=0, thrust=0.2)
                    self.logger.debug(f'altitude: {self.alt}')
                else:
                    self.state = MissionState.DIVING_OUT
                    self.logger.debug(f'Altitude is less than {self.target_altitude} meters')
                    self.logger.debug(f'altitude: {self.alt}')                

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
                        self.logger.debug(f'approach_counter: {self.approach_counter}')
                    else:
                        self.logger.debug(f'Mission complete.')
                        self.stop_mission()

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
