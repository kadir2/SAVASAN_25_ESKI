import threading
import time
import json
import redis
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from sklearn.cluster import KMeans
import logging
import math
import geopy.distance

# Loglama Yönetimi
class LoggerManager:
    def __init__(self, log_file="log.log", error_file="error.log", location_file="locations.log", gudumlu_file="gudumlu_info.log"):
        logging.basicConfig(
            format='%(levelname)s %(asctime)s: %(message)s (Line: %(lineno)d), (File: %(filename)s)',
            level=logging.INFO,
            datefmt='%Y-%m-%d %H:%M:%S',
            handlers=[logging.FileHandler(log_file, mode="w"), logging.StreamHandler()]
        )
        
        self.error_logger = logging.getLogger("error_logger")
        self.error_logger.setLevel(logging.ERROR)
        error_handler = logging.FileHandler(error_file, mode="w")
        self.error_logger.addHandler(error_handler)
        
        self.location_logger = logging.getLogger("location_logger")
        self.location_logger.setLevel(logging.INFO)
        location_handler = logging.FileHandler(location_file, mode="w")
        self.location_logger.addHandler(location_handler)
        
        self.gudumlu_logger = logging.getLogger("gudumlu_logger")
        self.gudumlu_logger.setLevel(logging.INFO)
        gudumlu_handler = logging.FileHandler(gudumlu_file, mode="a")  # Append modunda aç
        self.gudumlu_logger.addHandler(gudumlu_handler)

    def log_info(self, message):
        logging.info(message)

    def log_error(self, message):
        self.error_logger.error(message)

    def log_location(self, message):
        self.location_logger.info(message)

    def log_gudumlu(self, message):
        self.gudumlu_logger.info(message)

logger = LoggerManager()

# Redis İşlemleri
class TelemetryRedisClient:
    def __init__(self, redis_client):
        self.redis_client = redis_client

    def get_telemetry_data(self):
        try:
            telemetry_data = self.redis_client.get('konum_bilgileri')
            return json.loads(telemetry_data) if telemetry_data else []
        except redis.exceptions.RedisError as e:
            logger.log_error(f"Redis error: {e}")
            return []

    def save_to_redis(self, key, data):
        try:
            self.redis_client.set(key, json.dumps(data))
            logger.log_info(f"{key} Redis'e kaydedildi.")
        except redis.exceptions.RedisError as e:
            logger.log_error(f"Redis kaydetme hatası: {e}")

# UAV Takip Sistemi
class UAVTracker:
    def __init__(self, redis_host='localhost', redis_port=6379, delta_t=7, update_interval=5, k_clusters=1):
        self.redis_client = TelemetryRedisClient(redis.Redis(host=redis_host, port=redis_port, db=0, decode_responses=True))
        self.delta_t = delta_t
        self.update_interval = update_interval
        self.k_clusters = k_clusters
        self.predicted_positions = []
        self.predicted_density = np.array([])
        self.uav_density = np.array([])
        self.lock = threading.Lock()
        self.run_system = True
        self.team_data = []
        self.last_saved_data = {"team_data": None, "predicted_positions": None, "uav_density": None, "predicted_density": None}

        # Ana uçağımızın takım numarası
        self.main_uav_team_number = 1  # Takım numarası 5 olan UAV ana uçağımız

        # UAV'nin mevcut irtifası
        self.alt = 50  # Varsayılan irtifa değeri

        self.start_threads()

    def start_threads(self):
        threads = [
            threading.Thread(target=self.update_telemetry_thread, daemon=True),
            threading.Thread(target=self.calculate_predicted_positions, daemon=True),
            threading.Thread(target=self.analyze_uav_density, daemon=True),
            threading.Thread(target=self.analyze_predicted_density, daemon=True),
            threading.Thread(target=self.save_data_to_redis, daemon=True),
            threading.Thread(target=self.check_collision_risk, daemon=True)  # Çarpışma riskini kontrol eden thread
        ]
        for thread in threads:
            thread.start()
        logger.log_info(" Tüm thread'ler başlatıldı!")

    def update_telemetry_thread(self):
        while self.run_system:
            time.sleep(0.5)
            telemetry_data = self.redis_client.get_telemetry_data()
            if telemetry_data:
                with self.lock:
                    self.team_data = [
                        data for data in telemetry_data
                        if isinstance(data, dict) and isinstance(data.get("iha_enlem"), (int, float)) and isinstance(data.get("iha_boylam"), (int, float))
                    ]
                    logger.log_location(f"Anlık Konumlar: {self.team_data}")
                    print(f"Redis'ten alınan veriler: {self.team_data}")  # Debug için

    def calculate_predicted_positions(self):
        while self.run_system:
            with self.lock:
                if not self.team_data:
                    time.sleep(self.update_interval)
                    continue
                temp_positions = []
                for data in self.team_data:
                    try:
                        # Ana uçağımızı hesaplamalara dahil etme
                        if data.get("takim_numarasi") == self.main_uav_team_number:
                            continue

                        current_position = (data.get("iha_enlem", 0.0), data.get("iha_boylam", 0.0))
                        speed_m_s = data.get("iha_hizi", 0.0)
                        heading = math.radians(data.get("iha_yonelme", 0.0))

                        if not isinstance(speed_m_s, (int, float)) or not isinstance(heading, (int, float)):
                            continue

                        delta_distance = speed_m_s * self.delta_t
                        delta_lat = (delta_distance * math.cos(heading)) / 111320
                        delta_lon = (delta_distance * math.sin(heading)) / (111320 * math.cos(math.radians(current_position[0])))

                        new_lat = current_position[0] + delta_lat
                        new_lon = current_position[1] + delta_lon

                        temp_positions.append({"lat": new_lat, "lon": new_lon, "heading": math.degrees(heading)})
                    except Exception as e:
                        logger.log_error(f" Tahmini konum hesaplama hatası: {e}")

                self.predicted_positions = temp_positions
                logger.log_location(f"Tahmini Konumlar: {self.predicted_positions}")
                logger.log_gudumlu("Test log mesajı")
            time.sleep(self.update_interval)

    def analyze_uav_density(self):
        while self.run_system:
            with self.lock:
                # Ana uçağımızı yoğunluk hesaplamalarına dahil etme
                filtered_data = [data for data in self.team_data if data.get("takim_numarasi") != self.main_uav_team_number]
                if len(filtered_data) < self.k_clusters:
                    logger.log_info("Yeterli UAV verisi yok, yoğunluk hesaplanamıyor.")
                    self.uav_density = np.array([])
                    continue  # Hata almamak için işlem yapmadan devam et
                if len(filtered_data) >= self.k_clusters:
                    coordinates = np.array([(d.get("iha_enlem", 0.0), d.get("iha_boylam", 0.0)) for d in filtered_data])
                    kmeans = KMeans(n_clusters=self.k_clusters, random_state=np.random.randint(1, 10000), n_init=10)  # n_init parametresi eklendi
                    kmeans.fit(coordinates)
                    self.uav_density = kmeans.cluster_centers_
                    logger.log_location(f"Anlık Yoğunluk Merkezleri: {self.uav_density.tolist()}")
                else:
                    self.uav_density = np.array([])
            time.sleep(2)

    def analyze_predicted_density(self):
        while self.run_system:
            with self.lock:
                if len(self.predicted_positions) >= self.k_clusters:
                    coordinates = np.array([(p.get("lat", 0.0), p.get("lon", 0.0)) for p in self.predicted_positions])
                    kmeans = KMeans(n_clusters=self.k_clusters, random_state=np.random.randint(1, 10000), n_init=10)  # n_init parametresi eklendi
                    kmeans.fit(coordinates)
                    self.predicted_density = kmeans.cluster_centers_
                    logger.log_location(f"Tahmini Yoğunluk Merkezleri: {self.predicted_density.tolist()}")
                else:
                    self.predicted_density = np.array([])
            time.sleep(2)

    

    def save_data_to_redis(self):
        while self.run_system:
            with self.lock:
                if self.team_data != self.last_saved_data["team_data"]:
                    self.redis_client.save_to_redis("anlik_konumlar", self.team_data)
                    self.last_saved_data["team_data"] = self.team_data.copy()

                if self.predicted_positions != self.last_saved_data["predicted_positions"]:
                    self.redis_client.save_to_redis("tahmini_konumlar", self.predicted_positions)
                    self.last_saved_data["predicted_positions"] = self.predicted_positions.copy()

                if not np.array_equal(self.uav_density, self.last_saved_data["uav_density"]):
                    self.redis_client.save_to_redis("anlik_yogunluk_merkezleri", self.uav_density.tolist())
                    self.last_saved_data["uav_density"] = self.uav_density.copy()

                if not np.array_equal(self.predicted_density, self.last_saved_data["predicted_density"]):
                    self.redis_client.save_to_redis("tahmini_yogunluk_merkezleri", self.predicted_density.tolist())
                    self.last_saved_data["predicted_density"] = self.predicted_density.copy()

            time.sleep(2)  # Güncelleme sıklığını biraz düşürdük


    def check_collision_risk(self):
        while self.run_system:
            with self.lock:
                print(f"Team Data: {self.team_data}")  # Debug için
                if not main_uav:
                    time.sleep(0.5)  # Biraz bekleyip tekrar dene
                    main_uav = next(
                        (uav for uav in self.team_data 
                        if isinstance(uav, dict) and uav.get("takim_numarasi") == self.main_uav_team_number), None)

                if main_uav:
                    print(f"Ana UAV bulundu: {main_uav}")  # Debug için
                    self.vehicle_lat = main_uav.get("iha_enlem", 0.0)
                    self.vehicle_lon = main_uav.get("iha_boylam", 0.0)
                    self.alt = main_uav.get("iha_irtifa", self.alt)  # Mevcut irtifayı güncelle
                    main_heading = math.radians(main_uav.get("iha_yonelme", 0.0))  # Ana uçağın yönü

                    for uav in self.team_data:
                        if isinstance(uav, dict):  # uav'nin bir sözlük olduğundan emin ol
                            uav_team_number = uav.get("takim_numarasi", None)
                            if uav_team_number is not None and uav_team_number != self.main_uav_team_number:
                                print(f"Diğer UAV: {uav}")  # Debug için
                                distance = geopy.distance.distance(
                                    (self.vehicle_lat, self.vehicle_lon),
                                    (uav.get("iha_enlem", 0.0), uav.get("iha_boylam", 0.0))
                                ).meters

                                # Ana uçağın gidiş yönünde mi kontrolü
                                uav_heading = math.radians(uav.get("iha_yonelme", 0.0))
                                heading_diff = abs(main_heading - uav_heading)

                                print(f"Ana UAV Yönü: {math.degrees(main_heading)} derece, Diğer UAV Yönü: {math.degrees(uav_heading)} derece, Yön Farkı: {math.degrees(heading_diff)} derece")  # Debug için
                                print(f"Mesafe: {distance} metre")  # Debug için

                                if distance < 150 and heading_diff < math.radians(45):
                                    uav_id = uav.get("takim_numarasi", "Bilinmeyen ID")
                                    if uav_id not in self.detected_uavs:
                                            self.detected_uavs.add(uav_id)
                                            logger.log_gudumlu(f"YAKALAMAK ÜZEREYİZ! Mesafe: {distance} metre, Diğer UAV ID: {uav_id}")
                                            print(f"YAKALAMAK ÜZEREYİZ! Mesafe: {distance} metre, Diğer UAV ID: {uav_id}")

                                else:
                                    print(f"Mesafe veya yön farkı koşulu sağlanmadı.")  # Debug için
                    else:
                        print("Ana UAV bulunamadı!")  # Debug için
                time.sleep(1)

# Görselleştirme
class UAVTrackerVisualizer:
    def __init__(self, tracker, update_interval=1000):
        self.tracker = tracker
        self.update_interval = update_interval
        self.fig, self.ax = plt.subplots(figsize=(8, 6))
        self.ani = FuncAnimation(self.fig, self.update_plot, interval=self.update_interval, blit=False, cache_frame_data=False)

    def update_plot(self, _):  # frame parametresini opsiyonel yap
        self.ax.clear()
        drones = self.tracker.team_data
        predicted_positions = self.tracker.predicted_positions
        uav_density = self.tracker.uav_density
        predicted_density = self.tracker.predicted_density

        if drones:
            drone_x = [d.get("iha_boylam", 0.0) for d in drones]
            drone_y = [d.get("iha_enlem", 0.0) for d in drones]
            self.ax.scatter(drone_x, drone_y, c='blue', label="Anlık Konumlar", alpha=0.7, edgecolors='black')

        if predicted_positions:
            pred_x = [p.get("lon", 0.0) for p in predicted_positions]
            pred_y = [p.get("lat", 0.0) for p in predicted_positions]
            self.ax.scatter(pred_x, pred_y, c='orange', label="Tahmini Konumlar", alpha=0.6, edgecolors='black')

        if uav_density.size > 0:
            self.ax.scatter(uav_density[:, 1], uav_density[:, 0], c='red', marker='x', s=100, label="Anlık Yoğunluk")

        if predicted_density.size > 0:
            self.ax.scatter(predicted_density[:, 1], predicted_density[:, 0], c='green', marker='D', s=100, label="Tahmini Yoğunluk")

        self.ax.set_xlabel("Boylam")
        self.ax.set_ylabel("Enlem")
        self.ax.set_title("Drone Hareketleri ve Yoğunluk Analizi")
        self.ax.grid()
        self.ax.legend()

    def start(self):
        plt.show()

# Ana Program
if __name__ == "__main__":
    tracker = UAVTracker()
    visualizer = UAVTrackerVisualizer(tracker)
    visualizer.start()