from redis_helper import RedisHelper
import json
import time
import math
import logging

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

class TargetPredictor:
    SUGGESTIONS_KEY = 'uav_suggestions'
    TELEMETRY_KEY = 'konum_bilgileri'
    PREDICTION_KEY = 'target_uav_predicted_location'
    DELTA_T = 3  # Prediction time horizon in seconds
    LOOP_INTERVAL = 1 # How often to check for new suggestions and update prediction

    def __init__(self):
        self.r = RedisHelper().r

    def calculate_predicted_location(self, lat, lon, speed_m_s, heading_deg, delta_t):
        """Calculates the predicted location based on current state and time delta."""
        try:
            heading_rad = math.radians(heading_deg)
            delta_distance = speed_m_s * delta_t

            # Using standard approximations for meters per degree latitude/longitude
            delta_lat = (delta_distance * math.cos(heading_rad)) / 111320.0
            # Adjust meters per degree longitude based on latitude
            delta_lon = (delta_distance * math.sin(heading_rad)) / (111320.0 * math.cos(math.radians(lat)))

            predicted_lat = lat + delta_lat
            predicted_lon = lon + delta_lon
            return predicted_lat, predicted_lon
        except (TypeError, ValueError) as e:
            logging.error(f"Error in prediction calculation input: lat={lat}, lon={lon}, speed={speed_m_s}, heading={heading_deg}. Error: {e}")
            return None, None
        except Exception as e:
            logging.error(f"Unexpected error during prediction calculation: {e}")
            return None, None

    def _get_redis_data(self, key):
        """Safely gets data from Redis."""
        try:
            data_raw = self.r.get(key)
            if not data_raw:
                logging.debug(f"No data found in Redis key '{key}'.")
                return None
            return data_raw
        except Exception as e:
            logging.error(f"Unexpected error getting key '{key}' from Redis: {e}")
            return None

    def _set_redis_data(self, key, data):
        """Safely sets data in Redis."""
        if not self.r:
            logging.error("Redis connection not available.")
            return False
        try:
            self.r.set(key, json.dumps(data))
            return True
        except TypeError as e:
            logging.error(f"Failed to serialize data to JSON for key '{key}': {e}. Data: {data}")
            return False
        except Exception as e:
            logging.error(f"Unexpected error setting key '{key}' in Redis: {e}")
            return False

    def run(self):
        """Main loop to read suggestions, find target, predict, and save."""
        while True:
            target_uav_data = None
            predicted_lat = None
            predicted_lon = None
            target_team_num = None
            try:
                # 1. Get Suggestions
                suggestions_raw = self._get_redis_data(self.SUGGESTIONS_KEY)
                if not suggestions_raw:
                    time.sleep(self.LOOP_INTERVAL)
                    continue

                try:
                    suggestions = json.loads(suggestions_raw)
                    if not isinstance(suggestions, list) or not suggestions:
                        logging.warning(f"Suggestions data is empty or not a list: {suggestions}")
                        time.sleep(self.LOOP_INTERVAL)
                        continue
                except json.JSONDecodeError as e:
                    logging.error(f"Failed to decode suggestions JSON: {e}. Data: {suggestions_raw}")
                    time.sleep(self.LOOP_INTERVAL)
                    continue

                # 2. Select Target UAV (first in list is highest score)
                if suggestions[0].get('takim_numarasi') == 1:
                    target_suggestion = suggestions[1]
                    target_team_num = target_suggestion.get('takim_numarasi')
                else:
                    target_suggestion = suggestions[0]
                    target_team_num = target_suggestion.get('takim_numarasi')

                if target_team_num is None:
                    logging.warning(f"Highest score suggestion missing 'takim_numarasi': {target_suggestion}")
                    time.sleep(self.LOOP_INTERVAL)
                    continue

                logging.info(f"Selected target UAV: Team {target_team_num} (Score: {target_suggestion.get('score', 'N/A')})")

                # 3. Get Full Telemetry
                telemetry_raw = self._get_redis_data(self.TELEMETRY_KEY)
                if not telemetry_raw:
                    logging.warning(f"No telemetry data found in Redis key '{self.TELEMETRY_KEY}'. Cannot find target details.")
                    time.sleep(self.LOOP_INTERVAL)
                    continue

                try:
                    telemetry_data = json.loads(telemetry_raw)
                    if not isinstance(telemetry_data, list):
                         logging.warning(f"Telemetry data is not a list: {telemetry_data}")
                         time.sleep(self.LOOP_INTERVAL)
                         continue
                except json.JSONDecodeError as e:
                    logging.error(f"Failed to decode telemetry JSON: {e}. Data: {telemetry_raw}")
                    time.sleep(self.LOOP_INTERVAL)
                    continue

                # 4. Find Target UAV Data in Telemetry
                for uav in telemetry_data:
                    if isinstance(uav, dict) and uav.get('takim_numarasi') == target_team_num:
                        target_uav_data = uav
                        break

                if not target_uav_data:
                    logging.warning(f"Could not find telemetry data for target Team {target_team_num}.")
                    time.sleep(self.LOOP_INTERVAL)
                    continue

                # 5. Extract data and Predict Location
                try:
                    current_lat = float(target_uav_data['iha_enlem'])
                    current_lon = float(target_uav_data['iha_boylam'])
                    speed_m_s = float(target_uav_data['iha_hizi'])
                    heading_deg = float(target_uav_data['iha_yonelme'])

                    predicted_lat, predicted_lon = self.calculate_predicted_location(
                        current_lat, current_lon, speed_m_s, heading_deg, self.DELTA_T
                    )

                except KeyError as e:
                    logging.error(f"Missing key {e} in telemetry data for Team {target_team_num}: {target_uav_data}")
                except (ValueError, TypeError) as e:
                     logging.error(f"Invalid data type for prediction input for Team {target_team_num}: {e}. Data: {target_uav_data}")

                # 6. Save Prediction to Redis
                if predicted_lat is not None and predicted_lon is not None:
                    prediction_data = {
                        'takim_numarasi': target_team_num,
                        'predicted_lat': predicted_lat,
                        'predicted_lon': predicted_lon,
                    }
                    
                    if self._set_redis_data(self.PREDICTION_KEY, prediction_data):
                        logging.info(f"Saved predicted location for Team {target_team_num} to Redis: Lat={predicted_lat:.6f}, Lon={predicted_lon:.6f}")

            except Exception as e:
                logging.exception(f"An unexpected error occurred in the main loop: {e}") # Log full traceback

            time.sleep(self.LOOP_INTERVAL)

if __name__ == "__main__":
    predictor = TargetPredictor()
    predictor.run()