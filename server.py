from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import time

# Sunucuya gelen tüm telemetri verilerini takım numarasına göre saklamak için bir sözlük
telemetry_data_store = {}


def save_packet(packet, file_name):
    # JSON verisini dosyaya kaydet
    with open(file_name, "w") as json_dosyasi:
        json.dump(packet, json_dosyasi, indent=4)
    print(f" veri {file_name} dosyasına kaydedildi.")



class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):

    def _set_response(self, status_code=200, content_type='application/json'):
        self.send_response(status_code)
        self.send_header('Content-type', content_type)
        self.end_headers()

    def do_GET(self):
        if self.path == '/api/sunucusaati':
            self._set_response()
            current_time = time.gmtime()

            server_time = {
                "gun": current_time.tm_mday,
                "saat": current_time.tm_hour,
                "dakika": current_time.tm_min,
                "saniye": current_time.tm_sec,
                "milisaniye": int((time.time() % 1) * 1000)
            }
            print(f"Server Time: {json.dumps(server_time, indent=4)}")
            self.wfile.write(json.dumps(server_time).encode('utf-8'))
        
        elif self.path == '/api/qr_koordinati':
            self._set_response()
            qr_koordinat = {
                "qrEnlem": 41.1015837,
                "qrBoylam": 28.5524824
            }
            print(f"QR Koordinat: {json.dumps(qr_koordinat, indent=4)}")
            self.wfile.write(json.dumps(qr_koordinat).encode('utf-8'))

        elif self.path == '/api/hss_koordinatlari':
            self._set_response()
            current_time = time.gmtime()

            hss_koordinatlari = {
                "sunucusaati": {
                    "gun": current_time.tm_mday,
                    "saat": current_time.tm_hour,
                    "dakika": current_time.tm_min,
                    "saniye": current_time.tm_sec,
                    "milisaniye": int((time.time() % 1) * 1000)
                },
                "hss_koordinat_bilgileri": [
                    {
                        "id": 0,
                        "hssEnlem": 40.23260922,
                        "hssBoylam": 29.00573015,
                        "hssYaricap": 50
                    },
                    {
                        "id": 1,
                        "hssEnlem": 40.23351019,
                        "hssBoylam": 28.99976492,
                        "hssYaricap": 50
                    },
                    {
                        "id": 2,
                        "hssEnlem": 40.23105297,
                        "hssBoylam": 29.00744677,
                        "hssYaricap": 75
                    },
                    {
                        "id": 3,
                        "hssEnlem": 40.23090554,
                        "hssBoylam": 29.00221109,
                        "hssYaricap": 150
                    }
                ]
            }
            print(f"HSS Koordinatları: {json.dumps(hss_koordinatlari, indent=4)}")
            self.wfile.write(json.dumps(hss_koordinatlari).encode('utf-8'))

        else:
            self._set_response(404)
            self.wfile.write(json.dumps({"message": "URL not found"}).encode('utf-8'))

    def do_POST(self):
        global telemetry_data_store
        if self.path == '/api/telemetri_gonder':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            telemetri_verisi = json.loads(post_data)

            #print(f"Alınan Telemetri Verisi: {json.dumps(telemetri_verisi, indent=4)}")

            # Gelen telemetri verisini takım numarasına göre saklayın veya güncelleyin
            print(telemetri_verisi)
            team_number = telemetri_verisi["takim_numarasi"]
            telemetry_data_store[team_number] = {
                "takim_numarasi": team_number,
                "iha_enlem": telemetri_verisi["iha_enlem"],
                "iha_boylam": telemetri_verisi["iha_boylam"],
                "iha_irtifa": telemetri_verisi["iha_irtifa"],
                "iha_dikilme": telemetri_verisi["iha_dikilme"],
                "iha_yonelme": telemetri_verisi["iha_yonelme"],
                "iha_yatis": telemetri_verisi["iha_yatis"],
                "iha_hizi": telemetri_verisi["iha_hiz"],
                "zaman_farki": 0  # Örnek zaman farkı, dilerseniz dinamik olarak hesaplayabilirsiniz
            }

            current_time = time.gmtime()
            response = {
                "sunucusaati": {
                    "gun": current_time.tm_mday,
                    "saat": current_time.tm_hour,
                    "dakika": current_time.tm_min,
                    "saniye": current_time.tm_sec,
                    "milisaniye": int((time.time() % 1) * 1000)
                },
                "konumBilgileri": list(telemetry_data_store.values())
            }

            print(f"Yanıt: {json.dumps(response, indent=4)}")
            self._set_response()
            self.wfile.write(json.dumps(response).encode('utf-8'))
        
        elif self.path == '/api/kilitlenme_bilgisi':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            kilitlenme_verisi = json.loads(post_data)

            print(f"Alınan Kilitlenme Bilgisi: {json.dumps(kilitlenme_verisi, indent=4)}")

            self._set_response()
            self.wfile.write(json.dumps({"message": "Kilitlenme bilgisi alındı"}).encode('utf-8'))

            file_name_kitlenme = "kilitlenme_bilgisi.json"  # Dosya adı olarak değişken kullanımı

            # Veriyi kaydet
            save_packet(kilitlenme_verisi, file_name_kitlenme)

        elif self.path == '/api/giris':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            login_data = json.loads(post_data)

            print(f"Giriş Bilgileri: {json.dumps(login_data, indent=4)}")

            if login_data['kadi'] == "takimkadi" and login_data['sifre'] == "takimsifresi":
                self._set_response()
                response = {
                    "takim_numarasi": 1
                }
                print(f"Giriş Yanıtı: {json.dumps(response, indent=4)}")
                self.wfile.write(json.dumps(response).encode('utf-8'))
            else:
                self._set_response(400)
                error_response = {"message": "Invalid credentials"}
                print(f"Giriş Hatası: {json.dumps(error_response, indent=4)}")
                self.wfile.write(json.dumps(error_response).encode('utf-8'))

        elif self.path == '/api/kamikaze_bilgisi':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            kamikaze_verisi = json.loads(post_data)

            print(f"Alınan Kamikaze Bilgisi: {json.dumps(kamikaze_verisi, indent=4)}")

            self._set_response()
            self.wfile.write(json.dumps({"message": "Kamikaze bilgisi alındı"}).encode('utf-8'))
            
            file_name_kam = "kamikaze_bilgisi.json"  

            save_packet(kamikaze_verisi, file_name_kam)
        else:
            self._set_response(404)
            error_response = {"message": "URL not found"}
            print(f"Hata: {json.dumps(error_response, indent=4)}")
            self.wfile.write(json.dumps(error_response).encode('utf-8'))

def run(server_class=HTTPServer, handler_class=SimpleHTTPRequestHandler, port=8080):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    print(f'Starting httpd server on port {port}')
    httpd.serve_forever()

if __name__ == '__main__':
    run()