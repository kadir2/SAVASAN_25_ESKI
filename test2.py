import socket
import json
import logging
import os
import datetime
import shutil
import redis

# İstemci kodundaki ile aynı IP ve Port olmalı
SERVER_IP = "127.0.0.1"
SERVER_PORT = 9999

class Logger:
    def init_logger(self):
        # create main logs folder
        base_logs_dir = 'sunucu_alıcı_logs'
        if not os.path.exists(base_logs_dir):
            os.makedirs(base_logs_dir)
        self.logs_dir = base_logs_dir

        self.logger = logging.getLogger('Sunucu_Alıcı')
        self.logger.setLevel(logging.DEBUG)

        # Logger'a zaten handler eklenip eklenmediğini kontrol et
        if self.logger.hasHandlers():
            self.logger.handlers.clear()

        c_handler = logging.StreamHandler()

        # all log files live under sunucu_logs/
        log_file_path = os.path.join(base_logs_dir, 'sunucu_alıcı.log')
        old_logs_dir = os.path.join(base_logs_dir, "old_logs")

        if not os.path.exists(old_logs_dir):
            os.makedirs(old_logs_dir)

        if os.path.exists(log_file_path):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            new_log_file_name = f"sunucu_alıcı_{timestamp}.log"
            new_log_file_path = os.path.join(old_logs_dir, new_log_file_name)
            shutil.move(log_file_path, new_log_file_path)

        f_handler = logging.FileHandler(log_file_path)
        c_handler.setLevel(logging.INFO)
        f_handler.setLevel(logging.DEBUG)

        c_format = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
        f_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        c_handler.setFormatter(c_format)
        f_handler.setFormatter(f_format)

        self.logger.addHandler(c_handler)
        self.logger.addHandler(f_handler)
        return self.logger

r = redis.Redis(host='localhost', port=6379, db=0)

def start_server():
    """Gelen telemetri verilerini dinleyen ve yazdıran bir TCP sunucusu başlatır."""
    logger_instance = Logger()
    logger = logger_instance.init_logger()

    # AF_INET: IPv4, SOCK_STREAM: TCP
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((SERVER_IP, SERVER_PORT))
        s.listen()
        logger.info(f"Sunucu {SERVER_IP}:{SERVER_PORT} adresinde başlatıldı. Bağlantı bekleniyor...")

        while True:
            conn, addr = s.accept()
            with conn:
                logger.info(f"Bağlantı sağlandı: {addr}")
                data_buffer = b""
                while True:
                    chunk = conn.recv(1024) # 1024 byte'lık parçalar halinde oku
                    if not chunk:
                        break
                    data_buffer += chunk
                
                # Gelen veriyi işle
                if data_buffer:
                    try:
                        # Gelen byte verisini string'e çevir
                        r.set('sunucu_json', data_buffer)
                        json_string = data_buffer.decode('utf-8')
                        # JSON string'ini Python sözlüğüne çevir
                        telemetry_data = json.loads(json_string)
                        
                        pretty_json = json.dumps(telemetry_data, indent=2, ensure_ascii=False)
                        r.set('sunucu', pretty_json)  
                        logger.info(f"Alınan Telemetri Verisi:\n{pretty_json}")

                    except json.JSONDecodeError:
                        logger.error("Gelen veri geçerli bir JSON formatında değil. Alınan veri: %s", data_buffer.decode('utf-8', errors='ignore'))
                    except Exception as e:
                        logger.error(f"Veri işlenirken bir sorun oluştu: {e}")

if __name__ == "__main__":
    start_server()