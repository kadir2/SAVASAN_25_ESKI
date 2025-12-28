import numpy as np
import heapq
import json
import time
from scipy.interpolate import splprep, splev
from scipy.spatial.distance import euclidean
from rdp import rdp  
import redis
import logging
from mavlinkHandler import MAVLinkHandlerDronekit as MAVLinkHandler

# Redis bağlantısı
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Logging yapılandırması
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# MAVLink bağlantısı
with open('/home/cello/VISUAL-GUIDANCE/iha_destroyer/config.json') as f:
    config_data = json.load(f)

MAX_SPEED = config_data["guidance"]["MAX_SPEED"]  
MAX_ALTITUDE = config_data["guidance"]["MAX_ALTITUDE"]  
mavlink_handler = MAVLinkHandler('127.0.0.1:14555')

# Mevcut hedefi global olarak tut
current_goal = None

def get_redis_data():
    anlik_konum = r.get('konum_bilgileri')
    tahmini_yogunluk_merkezi = r.get('target_uav_predicted_location')
    anlik_konum = json.loads(anlik_konum) if anlik_konum else []
    tahmini_yogunluk_merkezi = json.loads(tahmini_yogunluk_merkezi) if tahmini_yogunluk_merkezi else []
    return anlik_konum, tahmini_yogunluk_merkezi

def get_team_start_point(anlik_konum, team_number=5):
    for drone in anlik_konum:
        if drone.get("takim_numarasi") == team_number:
            return (drone["iha_enlem"], drone["iha_boylam"])
    return None

def load_hss_data(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)["hss_koordinat_bilgileri"]

def calculate_scaled_radius(latitude, radius_m):
    scale_lat = (radius_m / 1000.0) / 111.0
    scale_lon = (radius_m / 1000.0) / (111.0 * np.cos(np.radians(latitude)))
    return scale_lat, scale_lon

def is_collision_free(node1, node2, hss_data, step_size=0.00002, safety_margin=0.0005):
    print(f"Kontrol ediliyor: {node1} -> {node2}")
    line_vector = np.array(node2) - np.array(node1)
    num_steps = int(np.linalg.norm(line_vector) / step_size)
    step_vector = line_vector / num_steps
    
    for step in range(num_steps + 1):
        check_point = np.array(node1) + step * step_vector
        for hss in hss_data:
            scale_lat, scale_lon = calculate_scaled_radius(hss["hssEnlem"], hss["hssYaricap"] + safety_margin * 111000)
            hss_center = np.array([hss["hssEnlem"], hss["hssBoylam"]])
            if np.linalg.norm(check_point - hss_center) < scale_lat:
                return False

    for hss in hss_data:
        scale_lat, scale_lon = calculate_scaled_radius(hss["hssEnlem"], hss["hssYaricap"] + safety_margin * 111000)
        hss_center = np.array([hss["hssEnlem"], hss["hssBoylam"]])
        line_start = np.array(node1)
        line_end = np.array(node2)
        d = np.linalg.norm(np.cross(line_end - line_start, line_start - hss_center)) / np.linalg.norm(line_end - line_start)
        if d <= scale_lat:
            proj = np.dot(hss_center - line_start, line_end - line_start) / np.linalg.norm(line_end - line_start)**2
            closest_point = line_start + proj * (line_end - line_start)
            if np.linalg.norm(closest_point - hss_center) < scale_lat and 0 <= proj <= 1:
                return False
    return True

def heuristic(a, b):
    return euclidean(a, b)

def astar(start, goal, bounds, hss_data, step_size=0.0002):
    if is_collision_free(start, goal, hss_data):
        return [start, goal]

    open_set = []
    heapq.heappush(open_set, (0, start))
    came_from = {start: None}
    g_score = {start: 0}
    f_score = {start: heuristic(start, goal)}
    directions = [
        (step_size, 0), (-step_size, 0), (0, step_size), (0, -step_size),
        (step_size, step_size), (-step_size, -step_size),
        (step_size, -step_size), (-step_size, step_size)
    ]
    
    while open_set:
        _, current = heapq.heappop(open_set)
        if heuristic(current, goal) < step_size:
            path = []
            while current is not None:
                path.append(current)
                current = came_from[current]
            return path[::-1]

        for direction in directions:
            neighbor = (round(current[0] + direction[0], 6), round(current[1] + direction[1], 6))
            if bounds is None or (bounds[0] <= neighbor[0] <= bounds[1] and bounds[2] <= neighbor[1] <= bounds[3]):
                if is_collision_free(current, neighbor, hss_data):
                    tentative_g_score = g_score[current] + heuristic(current, neighbor)
                    if neighbor not in g_score or tentative_g_score < g_score[neighbor]:
                        came_from[neighbor] = current
                        g_score[neighbor] = tentative_g_score
                        f_score[neighbor] = g_score[neighbor] + heuristic(neighbor, goal)
                        heapq.heappush(open_set, (f_score[neighbor], neighbor))
    return []

def smooth_path(path):
    if not path or len(path) < 3:
        return path
    simplified_path = rdp(np.array(path), epsilon=0.0001)
    if len(simplified_path) < 3:
        return simplified_path.tolist()
    try:
        tck, u = splprep([simplified_path[:, 0], simplified_path[:, 1]], s=0.00001, k=min(3, len(simplified_path)-1))
        u_new = np.linspace(0, 1, 100)
        smooth_x, smooth_y = splev(u_new, tck)
        return list(zip(smooth_x, smooth_y))
    except TypeError as e:
        logging.error(f"Spline oluşturulamadı! Hata: {e}")
        print("Uyarı: Spline oluşturulamadı, hareketli ortalama uygulanıyor.")
        def moving_average_smooth(path, window_size=3):
            if len(path) < window_size:
                return path
            smoothed_path = []
            for i in range(len(path)):
                start = max(0, i - window_size // 2)
                end = min(len(path), i + window_size // 2 + 1)
                avg_point = np.mean(path[start:end], axis=0)
                smoothed_path.append(avg_point)
            return smoothed_path
        return moving_average_smooth(simplified_path)

def generate_waypoints(smoothed_path, distance_interval=0.002):
    if not smoothed_path or len(smoothed_path) < 2:
        return []
    waypoints = [smoothed_path[0]]
    for i in range(1, len(smoothed_path)):
        prev_wp = waypoints[-1]
        current_point = smoothed_path[i]
        dist = euclidean(prev_wp, current_point)
        if dist >= distance_interval:
            waypoints.append(current_point)
    return waypoints

def run_waypoint_mission(start, goal, hss_data):
    """Drone’u hedefe dinamik olarak yönlendirir, her adımda yeni hedefi kontrol eder."""
    global current_goal
    mavlink_handler.set_parameter_value('TRIM_ARSPD_CM', MAX_SPEED)
    while True:
        guid = r.get('guid')  
        if guid == "2":
            # Mevcut konumu al
            current_lat, current_lon, _ = mavlink_handler.get_location()
            current_position = (current_lat, current_lon)

            # Redis’ten yeni hedefi kontrol et
            anlik_konum, tahmini_yogunluk_merkezi = get_redis_data()
            new_goal = tahmini_yogunluk_merkezi

            # Hedef değiştiyse yeni yol planla
            if new_goal != current_goal:
                logging.info(f"Yeni hedef alındı: {new_goal}, eski hedef: {current_goal}")
                current_goal = new_goal
                goal = (new_goal['predicted_lat'], new_goal['predicted_lon'])
                start = current_position  # Yeni başlangıç noktası mevcut konum

            # Yeni yol planla
            path = astar(start, goal, bounds=None, hss_data=hss_data)
            if not path:
                logging.error("Yol bulunamadı!")
                time.sleep(0.5)
                continue

            smoothed_path = smooth_path(path)
            waypoints = generate_waypoints(smoothed_path, distance_interval=0.002)

            # Redis’e kaydet
            r.set('start_point', json.dumps(start))
            r.set('goal_point', json.dumps(goal))
            r.set('smoothed_path', json.dumps(smoothed_path))

            # Waypoint’lere git
            for index, (lat, lon) in enumerate(waypoints):
                logging.info(f"[{index+1}/{len(waypoints)}] Hedefe gidiliyor: Lat: {lat}, Lon: {lon}")
                mavlink_handler.simple_go_to(lat, lon, 35)

                # Her adımda hedefe ulaşıp ulaşmadığını kontrol et
                while True:
                    current_lat, current_lon, _ = mavlink_handler.get_location()
                    distance = euclidean((current_lat, current_lon), (lat, lon))
                    if distance < 0.001:  # 100m hata payı
                        logging.info(f"Hedefe ulaşıldı: {lat}, {lon}")
                        break

                    # Yeni hedef kontrolü
                    anlik_konum, tahmini_yogunluk_merkezi = get_redis_data()
                    new_goal = tahmini_yogunluk_merkezi
                    if new_goal != current_goal:
                        logging.info("Hedef değişti, yeni yola geçiliyor.")
                        start = (current_lat, current_lon)  # Yeni başlangıç mevcut konum
                        goal = (new_goal['predicted_lat'], new_goal['predicted_lon'])
                        current_goal = new_goal
                        break  # İç döngüden çık, yeni yol planla

                    time.sleep(3)  # Daha hızlı tepki için kısa bekleme

            # Hedefe tamamen ulaşıldıysa döngüyü baştan başlat
            if euclidean((current_lat, current_lon), goal) < 0.00001:
                logging.info("Ana hedefe ulaşıldı, yeni hedef bekleniyor.")
                time.sleep(0.5)
        else:
            logging.info("Drone GUID 2 değil, bekleniyor...")
            time.sleep(0.5)

def is_in_hss_area(point, hss_data):
    lat, lon = point
    for hss in hss_data:
        hss_lat = hss["hssEnlem"]
        hss_lon = hss["hssBoylam"]
        hss_radius = hss["hssYaricap"] / 111000
        distance = euclidean((lat, lon), (hss_lat, hss_lon))
        if distance < hss_radius:
            return True
    return False

def main():
    hss_file_path = "hss_data.json"
    hss_data = load_hss_data(hss_file_path)

    # İlk başlangıç noktasını al
    while True:
        anlik_konum, tahmini_yogunluk_merkezi = get_redis_data()
        tahmini_yogunluk_merkezi = [[tahmini_yogunluk_merkezi["predicted_lat"], tahmini_yogunluk_merkezi["predicted_lon"]]]
        start = get_team_start_point(anlik_konum, team_number=1)
        print(start, tahmini_yogunluk_merkezi)
        if start and tahmini_yogunluk_merkezi:
            goal = tahmini_yogunluk_merkezi
            if goal:
                global current_goal
                current_goal = goal
                break
        logging.warning("Başlangıç veya hedef alınamadı, tekrar deneniyor...")
        time.sleep(1)

    # Waypoint görevini başlat
    run_waypoint_mission(start, goal, hss_data)

if __name__ == "__main__":
    main()