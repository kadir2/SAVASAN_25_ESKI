import socket
import redis
import json
import threading
import time

class XYZ:
    def __init__(self, ip, port):
        # Redis bağlantısını oluştur
        self.r = redis.StrictRedis(host='localhost', port=6379, decode_responses=True)
        
        # UDP soketi oluştur ve belirtilen IP/Port'a bağla
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server_address = (ip, port)
        self.sock.bind(self.server_address)
        
        print(f"UDP Sunucu başlatıldı: {ip}:{port}")
        
        # Veri işleme thread'ini başlat
        threading.Thread(target=self.receiver_thread).start()

    def receiver_thread(self):
        while True:
            try:
                # UDP üzerinden veri al
                data, addr = self.sock.recvfrom(3024)
                data = data.decode('utf-8')
                data = json.loads(data)  # JSON formatına çevir

                if isinstance(data, list) and all(isinstance(i, dict) for i in data):
                    print(f"Gelen Veri: {data}")

                    # Redise gönder
                    self.redis_gonder(data)

                time.sleep(0.1)  # 100ms gecikme
            except Exception as e:
                print(f"Hata: {e}")

    def redis_gonder(self, veriler):
        try:
            # JSON formatında tüm listeyi sakla
            self.r.set("konum_bilgileri", json.dumps(veriler))
            print("Veriler Redis'e JSON formatında kaydedildi")
        
        except Exception as e:
            print(f"Redis'e veri gönderme hatası: {e}")

if __name__ == '__main__':
    server = XYZ("0.0.0.0", 8100)

    # Sonsuz döngü ile programın çalışmasını devam ettir
    while True:
        time.sleep(1)
