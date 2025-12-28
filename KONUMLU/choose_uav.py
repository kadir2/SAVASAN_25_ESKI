import tkinter as tk
from tkinter import ttk
import json
import threading
import time
from redis_helper import RedisHelper
import math
from dronekit import connect

GLOBAL_BLACKLIST = {}
GLOBAL_BLACKLIST_LOCK = threading.Lock()

class CheckUAV:
    def __init__(self):
        self.rh = RedisHelper().r
        self.telemetry_data = []
        self.vehicle = connect('127.0.0.1:14554', wait_ready=True)
        self.score_thread = threading.Thread(target=self.calculate_score, daemon=True)
        self.score_thread.start()
        self.puan_listesi = []
        self.roll_monitoring_state = {}

    def monitor_uav(self, team):
        previous_coords = None
        roll_check_interval = 1
        last_roll_check_time = 0

        while True:
            telemetry_raw = self.rh.get('konum_bilgileri')
            if telemetry_raw:
                try:
                    telemetry_str = telemetry_raw.decode('utf-8')
                    current_telemetry_data = json.loads(telemetry_str)
                except (UnicodeDecodeError, json.JSONDecodeError) as e:
                    print(f"Error decoding telemetry data: {e}")
                    current_telemetry_data = []
                    time.sleep(5)
                    continue
            else:
                current_telemetry_data = []

            current_uav = None
            for uav in current_telemetry_data:
                if uav.get('takim_numarasi') == team:
                    current_uav = uav
                    break

            current_time = time.time()

            if current_uav is not None:

                # TELEMETRİSİ SABİT Mİ KONTROL

                try:
                    coords = (current_uav['iha_enlem'], current_uav['iha_boylam'], current_uav['iha_irtifa'])

                    if previous_coords is not None:
                        is_stationary = (abs(coords[0] - previous_coords[0]) <= 1e-6 and
                                         abs(coords[1] - previous_coords[1]) <= 1e-6 and
                                         abs(coords[2] - previous_coords[2]) <= 0.3)
                    
                        with GLOBAL_BLACKLIST_LOCK:
                            if is_stationary:
                                if team not in GLOBAL_BLACKLIST or GLOBAL_BLACKLIST[team] != "Stationary":
                                    print(f"Blacklist ADD [Stationary]: Team {team}")
                                    GLOBAL_BLACKLIST[team] = "Stationary"

                            else:
                                if team in GLOBAL_BLACKLIST and GLOBAL_BLACKLIST[team] == "Stationary":
                                    print(f"Blacklist REMOVE [Stationary]: Team {team}")
                                    del GLOBAL_BLACKLIST[team]

                    previous_coords = coords

                except KeyError as e:
                    print(f"Stationary check error: Missing key {e} for Team {team}")

                # FULL YATIŞTA MI KONTROL

                if current_time - last_roll_check_time >= roll_check_interval:
                    last_roll_check_time = current_time
                    try:
                        roll_angle = current_uav.get('iha_yatis')

                        if roll_angle is not None:
                            abs_roll = abs(roll_angle)

                            if abs_roll > 20:
                                if team not in self.roll_monitoring_state:
                                    print(f"Roll Monitor START: Team {team} (Roll: {roll_angle:.1f})")
                                    self.roll_monitoring_state[team] = {'start_time': current_time}
                                else:
                                    duration = current_time - self.roll_monitoring_state[team]['start_time']
                                    if duration >= 10:
                                        with GLOBAL_BLACKLIST_LOCK:
                                            if team not in GLOBAL_BLACKLIST or GLOBAL_BLACKLIST[team] != "Abnormal Roll":
                                                print(f"Blacklist ADD [Abnormal Roll]: Team {team} (Roll: {roll_angle:.1f} for {duration:.1f}s)")
                                                GLOBAL_BLACKLIST[team] = "Abnormal Roll"
                            else:
                                if team in self.roll_monitoring_state:
                                    print(f"Roll Monitor RESET: Team {team} (Roll: {roll_angle:.1f})")
                                    del self.roll_monitoring_state[team]
                                    with GLOBAL_BLACKLIST_LOCK:
                                        if team in GLOBAL_BLACKLIST and GLOBAL_BLACKLIST[team] == "Abnormal Roll":
                                            print(f"Blacklist REMOVE [Abnormal Roll]: Team {team}")
                                            del GLOBAL_BLACKLIST[team]
                        else:
                             if team in self.roll_monitoring_state:
                                 print(f"Roll Monitor RESET (No Data): Team {team}")
                                 del self.roll_monitoring_state[team]
                                 with GLOBAL_BLACKLIST_LOCK:
                                     if team in GLOBAL_BLACKLIST and GLOBAL_BLACKLIST[team] == "Abnormal Roll":
                                         print(f"Blacklist REMOVE [Abnormal Roll - No Data]: Team {team}")
                                         del GLOBAL_BLACKLIST[team]

                    except KeyError as e:
                        print(f"Roll check error: Missing key {e} for Team {team}")
                    except TypeError as e:
                        print(f"Roll check error: Invalid type for roll angle for Team {team}: {e}")

            else:
                if team in self.roll_monitoring_state:
                    print(f"Roll Monitor RESET (UAV Not Found): Team {team}")
                    del self.roll_monitoring_state[team]
                    with GLOBAL_BLACKLIST_LOCK:
                        if team in GLOBAL_BLACKLIST and GLOBAL_BLACKLIST[team] == "Abnormal Roll":
                            print(f"Blacklist REMOVE [Abnormal Roll - UAV Not Found]: Team {team}")
                            del GLOBAL_BLACKLIST[team]
                previous_coords = None

            time.sleep(1)

    def calculate_distance(self, lat1, lon1, alt1, lat2, lon2, alt2):
        R = 6371000 # Radius of Earth in meters
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = math.sin(delta_phi / 2.0) ** 2 + \
            math.cos(phi1) * math.cos(phi2) * \
            math.sin(delta_lambda / 2.0) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        horizontal_distance = R * c
        vertical_distance = abs(alt1 - alt2)

        total_distance = math.sqrt(horizontal_distance**2 + vertical_distance**2)
        return total_distance

    def is_distance_in_range(self, other_lat, other_lon, other_alt):
        if not self.vehicle or not hasattr(self.vehicle, 'location') or not self.vehicle.location.global_relative_frame:
            print("Vehicle connection lost or location not available for distance check.")
            return None, None

        my_location = self.vehicle.location.global_relative_frame
        if not hasattr(my_location, 'lat') or not hasattr(my_location, 'lon') or not hasattr(my_location, 'alt') or \
           my_location.lat is None or my_location.lon is None or my_location.alt is None:
            print("Vehicle location details not available for distance check.")
            return None, None

        if other_lat is None or other_lon is None or other_alt is None:
            print("Other UAV location details not available for distance check.")
            return None, None

        try:
            distance = self.calculate_distance(my_location.lat, my_location.lon, my_location.alt,
                                               other_lat, other_lon, other_alt)
            in_range = 5 <= distance <= 500
            return in_range, distance
        except Exception as e:
            print(f"Error calculating distance: {e}")
            return None, None

    def calculate_angle(self, x_heading, x_position, y_position):
        lat1 = math.radians(x_position[0])
        lon1 = math.radians(x_position[1])
        lat2 = math.radians(y_position[0])
        lon2 = math.radians(y_position[1])
        dlon = lon2 - lon1
        x_comp = math.sin(dlon) * math.cos(lat2)
        y_comp = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
        bearing = math.degrees(math.atan2(x_comp, y_comp))
        bearing = (bearing + 360) % 360
        diff = abs(x_heading - bearing)
        if diff > 180:
            diff = 360 - diff
        diff = round(diff)
        return diff

    def is_heading_within_90_degrees(self, other_heading):
        my_heading = self.vehicle.heading
        if my_heading is None or other_heading is None:
            print("Cannot compare headings: Own or other heading is None.")
            return None, None

        diff = abs(my_heading - other_heading)
        shortest_diff = diff
        if diff > 180:
            shortest_diff = 360 - diff

        return shortest_diff < 45, shortest_diff

    def calculate_score(self):
        while True:
            try:
                excluded_teams_redis_raw = self.rh.lrange('kilitlenme_bilgisi', 0, -1)
                excluded_teams_redis = set()
                if excluded_teams_redis_raw:
                    try:
                        excluded_teams_redis = set(int(team.decode('utf-8')) for team in excluded_teams_redis_raw)
                    except (ValueError, TypeError) as parse_error:
                        print(f"Error parsing Redis excluded teams list: {parse_error}")

                with GLOBAL_BLACKLIST_LOCK:
                    excluded_teams_monitor = set(GLOBAL_BLACKLIST.keys())

                excluded_teams = excluded_teams_redis.union(excluded_teams_monitor)

                telemetry_raw = self.rh.get('konum_bilgileri')
                if telemetry_raw:
                    try:
                        telemetry_str = telemetry_raw.decode('utf-8')
                        current_telemetry_data = json.loads(telemetry_str)
                    except (UnicodeDecodeError, json.JSONDecodeError) as e:
                         print(f"Error decoding telemetry data in calculate_score: {e}")
                         current_telemetry_data = []
                else:
                    current_telemetry_data = []

                if not self.vehicle or not hasattr(self.vehicle, 'location') or not self.vehicle.location.global_frame:
                    print("Vehicle connection lost or location not available, skipping score calculation.")
                    time.sleep(1)
                    continue
                my_heading = self.vehicle.heading
                if my_heading is None:
                    print("Vehicle heading not available for angle calculation, skipping score calculation.")
                    time.sleep(1)
                    continue
                my_location = self.vehicle.location.global_frame
                if not hasattr(my_location, 'lat') or not hasattr(my_location, 'lon') or my_location.lat is None or my_location.lon is None:
                     print("Vehicle location details not available, skipping score calculation.")
                     time.sleep(1)
                     continue
                my_lat_lon = [my_location.lat, my_location.lon]

                new_puan_listesi = []
                for uav in current_telemetry_data:
                    team_num = uav.get("takim_numarasi")
                    if team_num is None or team_num in excluded_teams:
                        continue

                    try:
                        rakip_lat = uav.get("iha_enlem")
                        rakip_lon = uav.get("iha_boylam")
                        rakip_alt = uav.get("iha_irtifa")
                        rakip_location = [rakip_lat, rakip_lon]

                        error = self.calculate_angle(my_heading, my_lat_lon, rakip_location)
                        angle_score = max(0, 5 - (error / 22.5))


                        other_heading = uav.get("iha_yonelme")
                        heading_ok = None
                        heading_diff = None
                        if other_heading is not None:
                            heading_ok, heading_diff = self.is_heading_within_90_degrees(other_heading)

                        heading_score = max(0, 3 - (heading_diff / 180))
                        dist_ok, distance = self.is_distance_in_range(rakip_lat, rakip_lon, rakip_alt)
                        distance_score = max(0, 2 - (distance / 500))
                        score = angle_score + heading_score + distance_score

                        new_puan_listesi.append({
                            "takim_numarasi": team_num,
                            "score": score,
                            "iha_enlem": rakip_lat,
                            "iha_boylam": rakip_lon,
                            "iha_irtifa": rakip_alt,
                            "heading_ok": heading_ok,
                            "heading_diff": heading_diff,
                            "distance_ok": dist_ok,
                            "distance": distance
                        })
                    except KeyError as e:
                         print(f"Score calc error: Missing key {e} for Team {team_num}")
                    except Exception as e:
                         print(f"Unexpected error during score calc for Team {team_num}: {e}")

                self.puan_listesi = new_puan_listesi

            except AttributeError as ae:
                 print(f"Attribute error during score calculation: {ae}")
                 time.sleep(1)
            except Exception as e:
                print(f"Error in calculate_score loop: {e}")

            time.sleep(1)

    def thread_uav(self):
        telemetry_raw = self.rh.get('konum_bilgileri')
        teams = set()
        if telemetry_raw:
            try:
                telemetry_str = telemetry_raw.decode('utf-8')
                telemetry_data = json.loads(telemetry_str)
                for uav in telemetry_data:
                    if 'takim_numarasi' in uav:
                        teams.add(uav['takim_numarasi'])
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                print(f"Error reading initial teams for monitoring threads: {e}")
        else:
            print("No initial telemetry data found to start monitoring threads.")

        if not teams:
            print("Warning: No teams found to monitor.")

        # 1) Kendi uçağınızı (team 1) listeden atıyoruz
        own_team = 1
        if own_team in teams:
            teams.remove(own_team)

        # artık liste doğrudan tüm diğer takımlar
        teams_list = sorted(teams)
        for team in teams_list:
            threading.Thread(target=self.monitor_uav, args=(team,), daemon=True).start()
            print(f"Monitoring thread started for Team {team}")

    def suggest_uav(self):
        excluded_teams_redis_raw = self.rh.lrange('kilitlenme_bilgisi', 0, -1)
        excluded_teams_redis = set()
        if excluded_teams_redis_raw:
            try:
                excluded_teams_redis = set(int(team.decode('utf-8')) for team in excluded_teams_redis_raw)
            except (ValueError, TypeError) as parse_error:
                print(f"Error parsing Redis excluded teams list in suggest_uav: {parse_error}")

        with GLOBAL_BLACKLIST_LOCK:
            excluded_teams_monitor = set(GLOBAL_BLACKLIST.keys())

        excluded_teams = excluded_teams_redis.union(excluded_teams_monitor)

        # 2) Kendi uçağınızı öneri listesinden atıyoruz
        excluded_teams.add(1)

        suggestions = []
        for uav_data in self.puan_listesi:
            team_num = uav_data.get("takim_numarasi")
            if team_num is None or team_num in excluded_teams:
                continue
            suggestions.append(uav_data)

        # Sort by score descending, then by distance ascending if scores are equal
        suggestions_sorted = sorted(suggestions, key=lambda x: (-x.get('score', 0), x.get('distance', float('inf'))))

        # Publish suggestions to Redis
        try:
            suggestions_json = json.dumps(suggestions_sorted)
            self.rh.set('uav_suggestions', suggestions_json)
        except Exception as e:
            print(f"Error publishing suggestions to Redis: {e}")

        return suggestions_sorted

class UAVControlPanel:
    def __init__(self):
        self.rh = RedisHelper().r
        self.checker = CheckUAV()
        self.checker.thread_uav()

        self.root = tk.Tk()
        self.root.title("UAV Kontrol Paneli")
        self.root.geometry("900x600") # Increased width slightly

        self.setup_panels()

        self.update_blacklist_panel()
        self.update_suggestions_panel()

        self.root.mainloop()

    def setup_panels(self):
        self.paned_window = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.paned_window.pack(fill=tk.BOTH, expand=True)

        self.left_frame = ttk.Frame(self.paned_window, width=500, relief=tk.SUNKEN) # Increased width
        self.paned_window.add(self.left_frame, weight=1)
        self.left_title = ttk.Label(self.left_frame, text="UAV Seçme Önerileri", font=("Arial", 16))
        self.left_title.pack(pady=10)
        self.left_text = tk.Text(self.left_frame, wrap=tk.WORD)
        self.left_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.left_text.insert(tk.END, "Sistem tarafından hesaplanan UAV seçim önerileri:\n")
        self.left_text.config(state=tk.DISABLED)

        self.right_frame = ttk.Frame(self.paned_window, width=400, relief=tk.SUNKEN)
        self.paned_window.add(self.right_frame, weight=1)
        self.right_title = ttk.Label(self.right_frame, text="Blacklist UAV", font=("Arial", 16))
        self.right_title.pack(pady=10)
        self.right_text = tk.Text(self.right_frame, wrap=tk.WORD)
        self.right_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.right_text.insert(tk.END, "Sistem tarafından oluşturulan blacklist listesi:\n")
        self.right_text.config(state=tk.DISABLED)

        self.left_text.tag_configure("heading_ok", foreground="green")
        self.left_text.tag_configure("heading_nok", foreground="red")
        self.left_text.tag_configure("heading_unknown", foreground="gray")
        self.left_text.tag_configure("score_positive", foreground="green")
        self.left_text.tag_configure("score_zero", foreground="red")
        self.left_text.tag_configure("distance_ok", foreground="green")
        self.left_text.tag_configure("distance_nok", foreground="red")
        self.left_text.tag_configure("distance_unknown", foreground="gray")
        self.left_text.tag_configure("follow_recommendation", foreground="blue") # Add this line


    def update_blacklist_panel(self):
        global GLOBAL_BLACKLIST
        self.right_text.config(state=tk.NORMAL)
        self.right_text.delete("1.0", tk.END)
        self.right_text.insert(tk.END, "Sistem tarafından oluşturulan blacklist listesi:\n")

        blacklisted_teams_for_redis = []
        with GLOBAL_BLACKLIST_LOCK:
            for team, reason in sorted(GLOBAL_BLACKLIST.items()):
                self.right_text.insert(tk.END, f"Team {team} - Reason: {reason}\n")
                blacklisted_teams_for_redis.append(team)

        self.right_text.config(state=tk.DISABLED)

        try:
            self.rh.set("blacklist", json.dumps(blacklisted_teams_for_redis))
        except Exception as e:
            print(f"Error updating Redis blacklist key: {e}")

        self.root.after(5000, self.update_blacklist_panel)

    def update_suggestions_panel(self):
        suggestions = self.checker.suggest_uav()

        self.left_text.config(state=tk.NORMAL)
        self.left_text.delete("1.0", tk.END)
        self.left_text.insert(tk.END, "Sistem tarafından hesaplanan UAV seçim önerileri:\n")

        if not suggestions:
             self.left_text.insert(tk.END, "(No suitable UAVs found or all are excluded)")

        for uav in suggestions:
            lat = uav.get('iha_enlem', 0.0)
            lon = uav.get('iha_boylam', 0.0)
            alt = uav.get('iha_irtifa', 0.0)
            score = uav.get('score', 0.0)
            team_num = uav.get('takim_numarasi', 'N/A')
            heading_ok = uav.get('heading_ok', None)
            heading_diff = uav.get('heading_diff', None)
            dist_ok = uav.get('distance_ok', None)
            distance = uav.get('distance', None)


            line_part1 = (f"Team {team_num} - "
                          f"Coords: ({lat:.5f}, {lon:.5f}, {alt:.1f}) - ")
            self.left_text.insert(tk.END, line_part1)

            score_text = f"Score: {score:.3f}"
            score_tag = "score_positive" if score > 0 else "score_zero"
            self.left_text.insert(tk.END, score_text, (score_tag,))

            line_part2 = " - "
            self.left_text.insert(tk.END, line_part2)


            if heading_ok is True and heading_diff is not None:
                heading_text = f"Heading OK ({heading_diff:.1f}°)"
                heading_tag = "heading_ok"
            elif heading_ok is False and heading_diff is not None:
                 heading_text = f"Heading NOT OK ({heading_diff:.1f}°)"
                 heading_tag = "heading_nok"
            else:
                heading_text = "Heading N/A"
                heading_tag = "heading_unknown"

            self.left_text.insert(tk.END, heading_text, (heading_tag,))
            self.left_text.insert(tk.END, " - ")


            if dist_ok is True and distance is not None:
                dist_text = f"Dist OK ({distance:.1f}m)"
                dist_tag = "distance_ok"
            elif dist_ok is False and distance is not None:
                dist_text = f"Dist NOT OK ({distance:.1f}m)"
                dist_tag = "distance_nok"
            else:
                dist_text = "Dist N/A"
                dist_tag = "distance_unknown"

            self.left_text.insert(tk.END, dist_text, (dist_tag,))

            # Add the "Takip edilir" text if conditions are met
            if score != 0 and heading_ok is True and dist_ok is True:
                self.left_text.insert(tk.END, " - Takip edilir", ("follow_recommendation",))

            self.left_text.insert(tk.END, "\n")

        self.left_text.config(state=tk.DISABLED)
        self.root.after(1000, self.update_suggestions_panel)

if __name__ == "__main__":
    panel = UAVControlPanel()