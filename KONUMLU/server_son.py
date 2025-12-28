from flask import Flask
import threading
import time
import dronekit
import json
import redis
import math

class FlaskAppWithBackgroundThread:
    def __init__(self):
        self.app = Flask(__name__)
        self.latest_value = None
        self.setup_routes()
        self.background_thread = threading.Thread(target=self.update_values, daemon=True)
        try:
            self.redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)
            self.redis_client.ping()
            print("Connected to Redis.")
        except redis.exceptions.ConnectionError as e:
            print(f"Redis connection error: {e}")
            self.redis_client = None

        ip = "127.0.0.1"
        connection_string1 = f"{ip}:14552"
        connection_string2 = f"{ip}:14561"
        connection_string3 = f"{ip}:14571"
        connection_string4 = f"{ip}:14581"
        connection_string5 = f"{ip}:14591"

        print('Connecting to vehicles...')
        self.vehicle1 = self._connect_vehicle(connection_string1, 1)
        self.vehicle2 = self._connect_vehicle(connection_string2, 2)
        self.vehicle3 = self._connect_vehicle(connection_string3, 3)
        self.vehicle4 = self._connect_vehicle(connection_string4, 4)
        self.vehicle5 = self._connect_vehicle(connection_string5, 5)
        print('Finished connection attempts.')

    def _connect_vehicle(self, connection_string, vehicle_id):
        try:
            vehicle = dronekit.connect(connection_string, wait_ready=False, timeout=30, rate=20)
            print(f"Attempted connection to Vehicle {vehicle_id} ({connection_string}).")
            time.sleep(0.1)
            if vehicle:
                 print(f"Vehicle {vehicle_id} object created.")
            else:
                 print(f"Vehicle {vehicle_id} connection returned None.")
            return vehicle
        except Exception as e:
            print(f"Error connecting to Vehicle {vehicle_id} ({connection_string}): {e}")
            return None

    def get_telemetry_data(self, vehicle, vehicle_id):
        try:
            if not vehicle:
                return None
            if not vehicle.location or not vehicle.location.global_relative_frame or not vehicle.attitude or not vehicle.heading:
                 return None

            altitude = vehicle.location.global_relative_frame.alt
            latitude = vehicle.location.global_relative_frame.lat
            longitude = vehicle.location.global_relative_frame.lon
            heading = vehicle.heading
            airspeed = vehicle.airspeed if vehicle.airspeed is not None else 0.0
            groundspeed = vehicle.groundspeed if vehicle.groundspeed is not None else 0.0
            roll_rad = vehicle.attitude.roll if vehicle.attitude.roll is not None else 0.0
            roll_deg = math.degrees(roll_rad)

            return latitude, longitude, altitude, heading, airspeed, groundspeed, roll_deg
        except Exception as e:
            print(f"Error getting telemetry data for Vehicle {vehicle_id}: {e}")
            return None

    def setup_routes(self):
        @self.app.route('/')
        def get_latest_value():
            if isinstance(self.latest_value, str):
                 return self.app.response_class(
                    response=self.latest_value,
                    status=200,
                    mimetype='application/json'
                )
            return json.dumps([])

    def update_values(self):
        previous_vehicle_data = {}
        print(f"[{time.strftime('%H:%M:%S')}] Starting update_values loop...")

        while True:
            print(f"[{time.strftime('%H:%M:%S')}] --- Loop Iteration Start ---")
            current_data_tuples = {}
            current_data_dicts = []
            vehicles = {
                1: self.vehicle1, 2: self.vehicle2, 3: self.vehicle3,
                4: self.vehicle4, 5: self.vehicle5
            }

            for team_num, vehicle_obj in vehicles.items():
                vehicle_data_tuple = self.get_telemetry_data(vehicle_obj, team_num)
                if vehicle_data_tuple:
                    current_data_tuples[team_num] = vehicle_data_tuple
                    vehicle_data_dict = self.create_vehicle_data_dict(
                        vehicle_data_tuple,
                        team_num,
                        previous_vehicle_data.get(team_num, None)
                    )
                    if vehicle_data_dict:
                        current_data_dicts.append(vehicle_data_dict)

            print(f"[{time.strftime('%H:%M:%S')}] Data fetch complete. {len(current_data_dicts)} valid dicts created.")

            if current_data_dicts:
                data_changed = self.has_data_changed(previous_vehicle_data, current_data_tuples)
                print(f"[{time.strftime('%H:%M:%S')}] Checking for data changes... Changed: {data_changed}")

                if data_changed:
                    print(f"[{time.strftime('%H:%M:%S')}] Data changed, preparing JSON...")
                    all_vehicles_data = json.dumps(current_data_dicts)
                    self.latest_value = all_vehicles_data
                    print(self.latest_value)
                    if self.redis_client:
                        try:
                            self.redis_client.set('konum_bilgileri', self.latest_value)
                            print(f"[{time.strftime('%H:%M:%S')}] Updated Redis 'konum_bilgileri'.")
                        except redis.exceptions.RedisError as e:
                            print(f"[{time.strftime('%H:%M:%S')}] Redis Error: {e}")
                    else:
                        print(f"[{time.strftime('%H:%M:%S')}] Redis client not available.")

                    previous_vehicle_data = current_data_tuples.copy()

            else:
                 print(f"[{time.strftime('%H:%M:%S')}] No valid data dictionaries created in this iteration. Skipping Redis update.")

            print(f"[{time.strftime('%H:%M:%S')}] --- Loop Iteration End ---")
            time.sleep(1)

    def create_vehicle_data_dict(self, vehicle_data, takim_numarasi, previous_data_tuple):
        try:
            latitude, longitude, altitude, heading, airspeed, groundspeed, roll_deg = vehicle_data
            
            time_difference = 0

            vehicle_data_dict = {
                "takim_numarasi": takim_numarasi,
                "iha_enlem": latitude,
                "iha_boylam": longitude,
                "iha_irtifa": altitude,
                "iha_dikilme": 0,
                "iha_yonelme": heading if heading is not None else 0,
                "iha_yatis": round(roll_deg),
                "iha_hizi": airspeed,
                "zaman_farki": time_difference,
                "yasaklı_alan_durumu": 0
            }
            return vehicle_data_dict
        except Exception as e:
             print(f"Error creating vehicle data dict for Team {takim_numarasi}: {e}")
             return None


    def has_data_changed(self, previous_data_tuples, current_data_tuples):
        if set(previous_data_tuples.keys()) != set(current_data_tuples.keys()):
            return True
        for key, current_tuple in current_data_tuples.items():
            previous_tuple = previous_data_tuples.get(key)
            if previous_tuple != current_tuple:
                return True
        return False


    def run(self, debug=True):
        self.background_thread.start()
        self.app.run(debug=debug, host='0.0.0.0', port=5000, use_reloader=False)

if __name__ == '__main__':
    my_app = FlaskAppWithBackgroundThread()
    my_app.run()