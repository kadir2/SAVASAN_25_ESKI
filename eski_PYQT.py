import sys
import cv2
import redis
import json
import numpy as np
import requests
import geopy.distance
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QPushButton, QHBoxLayout, QSizePolicy, QGraphicsTextItem ,QLabel, QGridLayout, QSlider
from PyQt5.QtGui import QPixmap, QImage, QFont
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QProcess
import shlex
import style as style
import logging
import os
import shutil
from datetime import datetime
import signal




class Loggerr:
    def __init__(self):
        # Logger oluştur
        self.logger = logging.Logger('Arayuz_Handler')
        self.logger.setLevel(logging.DEBUG)  # Log seviyesi DEBUG olarak ayarlanır
        
        # Handlers: Konsol ve Dosya
        c_handler = logging.StreamHandler()  # Konsol için handler
        log_file_path = 'Arayuz.log'  # Log dosyasının adı
        old_logs_dir = "old_logs_ARAYUZ_Handler"  # Eski log dosyalarının taşınacağı klasör

        # Eski log dosyalarını yedekle
        if not os.path.exists(old_logs_dir):  # Eğer klasör yoksa oluştur
            os.makedirs(old_logs_dir)
        if os.path.exists(log_file_path):  # Eğer log dosyası varsa
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")  # Zaman damgası oluştur
            new_log_file_name = f"ARAYUZ_{timestamp}.log"  # Yeni log dosyasının adı
            new_log_file_path = os.path.join(old_logs_dir, new_log_file_name)  # Yeni log dosyasının yolu
            shutil.move(log_file_path, new_log_file_path)  # Eski log dosyasını taşı
        
        f_handler = logging.FileHandler(log_file_path)  # Log dosyasına handler
        
        # Seviyeleri belirle
        c_handler.setLevel(logging.DEBUG)  # Konsola yazdırılacak log seviyesi
        f_handler.setLevel(logging.DEBUG)  # Dosyaya yazdırılacak log seviyesi
        
        # Formatlar
        c_format = logging.Formatter('%(name)s - %(levelname)s - %(message)s')  # Konsol formatı
        f_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s') # dosyaya yazdırılacak log formatı

        
        # Formatları handler'lara ekle
        c_handler.setFormatter(c_format)
        f_handler.setFormatter(f_format)
        
        # Handler'ları logger'a ekle
        self.logger.addHandler(c_handler)
        self.logger.addHandler(f_handler)
# Kullanım
logger_instance = Loggerr()  # Logger nesnesi oluştur
logger = logger_instance.logger   # Logger nesnesini al



### 9 Parçalı Harita Al ve Birleştir
def fetch_large_map(lat, lon, zoom=18, tile_size=400, grid_size=3):
    """
    Yandex'ten 9 parçalı (3x3) büyük bir harita alır ve birleştirerek tek bir görüntü oluşturur.
    Harita boyutu **1200x1000** olarak ayarlandı.
    """

    if test == 0:
        lat_offset = 0.001622 * (19 - zoom)   # büyürse birbirlerine yaklaşırlar dikey olarak
        lon_offset = 0.002149 * (19 - zoom)   # büyürse birbirlerine yaklaşırlar yatay olarak
    else:
        lat_offset = 0.002172 * (19 - 16)   # test için ayarlanmıştır
        lon_offset = 0.002869 * (19 - 16)
    logger.debug(f"lat_offset: {lat_offset}")
    # Harita boyutu (örn. 1200x1000 için ayarlandı)
    combined_width = tile_size * grid_size
    combined_height = tile_size * grid_size
    combined_image = Image.new("RGB", (combined_width, combined_height))

    #  3x3 harita parçaları için koordinatlar oluştur
    coords = [
        (lat + lat_offset * (1 - i), lon + lon_offset * (j - 1))
        for i in range(grid_size)
        for j in range(grid_size)
    ]

    for index, (tile_lat, tile_lon) in enumerate(coords):
        i, j = divmod(index, grid_size)

        tile_url = f"https://static-maps.yandex.ru/1.x/?ll={tile_lon},{tile_lat}&z={zoom}&size={tile_size},{tile_size}&l=sat"
        logger.debug(f"[INFO] Harita parçaları indiriliyor: {tile_url}")

        response = requests.get(tile_url)
        if response.status_code == 200:
            tile_image = Image.open(BytesIO(response.content))

            if tile_image.mode != "RGB":
                tile_image = tile_image.convert("RGB")  

            combined_image.paste(tile_image, (j * tile_size, i * tile_size))
            logger.debug(f"[INFO] {i},{j} konumundaki harita indirildi ve eklendi.")
        else:
            logger.debug(f"[ERROR] {i},{j} harita yüklenemedi! Hata kodu: {response.status_code}")

    # 1200x1000'e ölçekleme
    combined_image = combined_image.resize((1200, 1000), Image.LANCZOS)
    combined_image.save("map_highres.jpg", "JPEG")
    logger.debug("[INFO] Yüksek kaliteli 1200x1000 harita oluşturuldu!")
    return "map_highres.jpg"


### Harita Görselleştirme (PyQt5)

class FlightMap(QGraphicsView):
    def __init__(self, r, map_center):
        super().__init__()
        self.r = r
        self.map_center = map_center  # Ana harita merkezi koordinatları
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.pixmap = QPixmap()
        self.image_item = None

        # Harita güncelleme işlemi QThread ile yapılacak
        self.worker = MapUpdaterThread(self.r, self.map_center)
        self.worker.update_signal.connect(self.update_map_from_data)
        self.worker.start()  # Arka planda sürekli çalışacak

        self.setAlignment(Qt.AlignCenter)
        self.setSceneRect(0, 0, 1200, 1000)

        self.load_static_map()

    def load_static_map(self):
        """Eğer Redis'ten harita gelmezse, boş bir görüntü göster."""
        self.scene.clear()
        placeholder = QPixmap(1200, 1000) 
        placeholder.fill()
        self.image_item = QGraphicsPixmapItem(placeholder)
        self.scene.addItem(self.image_item)

    def update_map_from_data(self, img):
        """QThread işlemi tamamlandıktan sonra haritayı güncelle."""
        try:
            height, width, channel = img.shape
            bytes_per_line = channel * width
            qimage = QImage(img.data, width, height, bytes_per_line, QImage.Format_RGB888)
            self.pixmap = QPixmap.fromImage(qimage)
            self.scene.clear()
            self.image_item = QGraphicsPixmapItem(self.pixmap)
            self.scene.addItem(self.image_item)
            #logger.debug("[INFO] Harita başarıyla güncellendi!")
        except Exception as e:
            logger.debug(f"[ERROR] Güncellenen harita yüklenirken hata oluştu: {e}")

    def resizeEvent(self, event):
        """Pencere boyutu değiştiğinde görüntüyü yeniden boyutlandır."""
        super().resizeEvent(event)
        if self.image_item:
            self.fitInView(self.image_item, Qt.KeepAspectRatio)


class MapUpdaterThread(QThread):
    update_signal = pyqtSignal(np.ndarray)  # Güncellenmiş görüntüyü sinyal olarak gönder

    def __init__(self, r, map_center):
        super().__init__()
        self.r = r
        self.center = [41.10336, 28.54721]
        self.solumsu = 20
        self.yukarimsi = 50
        self.testing = test
        self.map_center = map_center  # Ana harita merkezi koordinatları
        self.bir_boylam = None
        self.bir_enlem = None
        self.bir_irtifa = None

        


    def run(self):
        """Sürekli olarak haritayı günceller (1 saniyede bir çalışır)."""

        # PNG ikonunu bir kez yükle
        icon_orig = Image.open("airplane.png").convert("RGBA")

        # Koordinatları piksel değerlerine dönüştürme fonksiyonu
        def latlon_to_pixel(lat, lon):
            if self.testing == 1:
                en_soll = 28.54095   #17 için
                en_ustt = 41.10793   #17 için
                en_sol  = 28.53423   #16
                en_ust  = 41.11315   #16
            else:    
                en_sol = 28.54393
                en_ust = 41.10580

            sol_orta  = [41.10336, en_sol]
            üst_orta  = [en_ust,  28.54721]
            yanal_fark = geopy.distance.distance(self.center, sol_orta).m
            dik_fark   = geopy.distance.distance(self.center, üst_orta).m
            sol_orani  = 600 / yanal_fark
            dik_orani  = 500 / dik_fark

            # logger.debug(f"sol_orani: {sol_orani}")
            # logger.debug(f"dik_orani: {dik_orani}")
            # logger.debug(f"yanal_fark: {yanal_fark}")
            # logger.debug(f"dik_fark: {dik_fark}")

            self.solumsu  = self.map_center[1] - (self.center[1] - en_sol)
            self.yukarimsi = self.map_center[0] + (en_ust   - self.center[0])

            x = int(geopy.distance.distance((lat, lon), (lat, self.solumsu)).m * sol_orani)
            y = int(geopy.distance.distance((lat, lon), (self.yukarimsi, lon)).m * dik_orani)

            return x, y
        

        while True:
            try:
                # Harita ve koordinatları Redis'ten çek
                map_data         = self.r.get("map")
                coordinates_data = self.r.get("konum_bilgileri")
            except redis.ConnectionError:
                logger.debug("[ERROR] Redis bağlantısı sağlanamadı! Lütfen Redis servisini kontrol edin.")
                self.msleep(1000)
                continue

            #gerçek kısım
            takim_map = {1: "bir", 2: "iki", 3: "uc", 4: "dort", 5: "bes"}

            # Takım konumlarını sıfırla
            for isim in takim_map.values():
                setattr(self, f"{isim}_enlem", None)
                setattr(self, f"{isim}_boylam", None)
                setattr(self, f"{isim}_irtifa", 0.0)
                setattr(self, f"{isim}_yonelme", 0.0)

            # Konum bilgilerini işle
            try:
                if self.testing == 1:
                    if coordinates_data is not None:
                        vehicles = json.loads(coordinates_data.decode("utf-8"))
                        for vehicle in vehicles:
                            takim = vehicle.get("takim_numarasi")
                            if takim in takim_map:
                                sayi = takim_map[takim]
                                setattr(self, f"{sayi}_enlem", float(vehicle.get("iha_enlem")))
                                setattr(self, f"{sayi}_boylam", float(vehicle.get("iha_boylam")))
                                setattr(self, f"{sayi}_irtifa", float(vehicle.get("iha_irtifa")))
                                setattr(self, f"{sayi}_yonelme", float(vehicle.get("iha_yonelme", 0))-90)
                    else:
                        logger.debug("[WARNING] Redis'te 'konum_bilgileri' verisi bulunamadı!")
                else:
                    if coordinates_data is not None:
                        try:
                            cor = json.loads(coordinates_data)
                            for i in cor.get("konumBilgileriii", []):
                                takim_no = i.get("takim_numarasi")
                                if takim_no in takim_map:
                                    sayi = takim_map[takim_no]
                                    setattr(self, f"{sayi}_enlem", float(i.get("iha_enlem")))
                                    setattr(self, f"{sayi}_boylam", float(i.get("iha_boylam")))
                                    setattr(self, f"{sayi}_irtifa", float(i.get("iha_irtifa")))
                                    setattr(self, f"{sayi}_yonelme", float(i.get("iha_yonelme", 0))-90)

                        except Exception as e:
                            logger.debug(f"[ERROR] Konum bilgileri JSON formatında değil veya bozuk! Hata: {e}")
                    else:
                        logger.debug("[WARNING] Redis'te 'konum_bilgileri' verisi bulunamadı!")
            except Exception as e:
                logger.debug(f"[ERROR] Konum bilgileri işlenirken hata oluştu: {e}")

            #tek uçak imuk ya da hezarfen testinde
            # try:
            #     lat_data = self.r.get("lat")
            #     lon_data = self.r.get("lon")
            #     alt      = self.r.get("alt")  # İstersen alt verisini de alabilirsin
            #     heading  = self.r.get("heading")  # İstersen heading verisini de alabilirsin
            #
            #     if lat_data is None or lon_data is None:
            #         logger.debug("[WARNING] Redis'te 'lat' veya 'lon' verisi yok!")
            #
            #     self.bir_enlem  = float(lat_data)
            #     self.bir_boylam = float(lon_data)
            #     self.bir_irtifa = float(alt)
            #    self.bir_yonelme = float(heading) if heading is not None else 0.0 
            # except Exception as e:
            #     logger.debug(f"[ERROR] 'lat' ve 'lon' verisi alınırken hata oluştu: {e}")

            if map_data is None:
                logger.debug("[ERROR] Redis'te 'map' verisi bulunamadı!")
                self.msleep(1000)
                continue

            np_img = np.frombuffer(map_data, dtype=np.uint8)
            img    = cv2.imdecode(np_img, cv2.IMREAD_COLOR)
            if img is None:
                logger.debug("[ERROR] cv2.imdecode başarısız oldu! map_data boyutu: %d" % len(map_data))
                continue

            if img is not None:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                self.color_size = 3 if self.testing == 1 else 5

                #Her takım için gerekli bilgileri içeren bir liste tanımlıyoruz.
                takimlar = [
                    {"label": f"T1 {self.bir_irtifa:.1f}", "enlem_attr": "bir_enlem",   "boylam_attr": "bir_boylam",   "boylam_val": self.bir_boylam, "color": (255, 205, 0),   "icon_size": (30,30), "heading": getattr(self, "bir_yonelme", 0)},
                    {"label": f"T2 {self.iki_irtifa:.1f}", "enlem_attr": "iki_enlem",   "boylam_attr": "iki_boylam",   "boylam_val": self.iki_boylam, "color": (50, 0, 255),   "icon_size": (30,30), "heading":  getattr(self, "iki_yonelme", 0)},
                    {"label": f"T3 {self.uc_irtifa:.1f}",  "enlem_attr": "uc_enlem",    "boylam_attr": "uc_boylam",    "boylam_val": self.uc_boylam,  "color": (50, 0, 255),   "icon_size": (30,30), "heading": getattr(self, "uc_yonelme", 0)},
                    {"label": f"T4 {self.dort_irtifa:.1f}","enlem_attr": "dort_enlem", "boylam_attr": "dort_boylam","boylam_val": self.dort_boylam,"color": (50, 0, 255),   "icon_size": (30,30), "heading": getattr(self, "dort_yonelme", 0)},
                    {"label": f"T5 {self.bes_irtifa:.1f}", "enlem_attr": "bes_enlem",   "boylam_attr": "bes_boylam",   "boylam_val": self.bes_boylam, "color": (50, 0, 255),"icon_size": (30,30), "heading": getattr(self, "bes_yonelme", 0)}
                ]

                # --- OpenCV img -> PIL img
                img_pil     = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).convert("RGBA")
                overlay_pil = Image.new("RGBA", img_pil.size, (0, 0, 0, 0))
                draw_overlay = ImageDraw.Draw(overlay_pil)
                draw_main    = ImageDraw.Draw(img_pil)

                # Font seçimi
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
                except:
                    font = ImageFont.load_default()

                try:
                    # --- Takım noktalarını ve ikonlarını çiz
                    for takim in takimlar:
                        enlem  = getattr(self, takim["enlem_attr"])
                        boylam = getattr(self, takim["boylam_attr"])
                        if enlem is None or boylam is None:
                            continue
                        if not (self.solumsu < takim["boylam_val"] < self.yukarimsi):
                            continue

                        x, y = latlon_to_pixel(enlem, boylam)

                        # İkon boyutlandırma ve döndürme
                        # Yeni: Oranı koruyarak ölçekleme + döndürme
                        orig_w, orig_h       = icon_orig.size
                        target_w, target_h   = takim.get("icon_size", (self.color_size*2, self.color_size*2))
                        scale                = min(target_w/orig_w, target_h/orig_h)
                        new_w, new_h         = int(orig_w * scale), int(orig_h * scale)

                        icon = icon_orig.resize((new_w, new_h), resample=Image.Resampling.LANCZOS)
                        icon = icon.rotate(-takim.get("heading", 0), expand=True)


                    # --- Renk tonlama (tint) için
                        r, g, b = takim["color"]
                        # 1) Boş bir RGBA katman oluştur
                        colored = Image.new("RGBA", icon.size, (r, g, b, 0))
                        # 2) Orijinal ikonun alpha kanalını al
                        alpha = icon.split()[3]
                        # 3) Alpha’yı yeni katmana uygula
                        colored.putalpha(alpha)
                        # 4) Paste ederken bu renklenmiş ikonu kullan
                        paste_icon = colored

                        # --- Haritaya yapıştır
                        iw, ih = paste_icon.size
                        paste_pos = (x - iw//2, y - ih//2)
                        img_pil.paste(paste_icon, paste_pos, paste_icon)

                        # --- Label rengini de takım rengine çekmek istersen:
                        label_pos = (x + iw//2 + 5, y - ih//2)
                        draw_main.text(label_pos, takim["label"], font=font, fill=(*takim["color"], 255))

                    # --- Overlay çemberlerini çiz (yarı saydam alanlar)
                    circle_positions = [
                        (41.10758,   28.54625, 17 * 50 / 50),
                        (41.107534,  28.554835,17 * 40 / 50),
                        (41.10461,   28.55171, 17 * 75 / 50),
                        (41.109865,  28.550058,17 *150/ 50),
                    ]
                    for lat, lon, radius in circle_positions:
                        u, v = latlon_to_pixel(lat, lon)
                        r    = int(radius)
                        draw_overlay.ellipse(
                            [(u - r, v - r), (u + r, v + r)],
                            fill=(0, 0, 255, int(255 * 0.3))
                        )

                    # --- Overlay'i ana görsele bindir
                    combined = Image.alpha_composite(img_pil, overlay_pil)

                    # --- PIL -> OpenCV (güncellenmiş img)
                    img = cv2.cvtColor(np.array(combined.convert("RGB")), cv2.COLOR_RGB2BGR)

                    # GUI'ye gönder
                    self.update_signal.emit(img)
                    self.msleep(500)  # 0.5 saniye bekle ve tekrar güncelle

                except Exception as e:
                    logger.debug(f"[ERROR] Harita çiziminde hata oluştu: {e}")
                    self.msleep(1000)  # Hata oluşursa 1 saniye bekleyip tekrar dene

            else:
                logger.debug("[ERROR] Harita resmi decode edilemedi!")
                self.msleep(1000)


class LiveFeed(QGraphicsView):
    def __init__(self, r):
        super().__init__()
        self.r = r
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.pixmap = QPixmap()
        self.image_item = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(33)  # 30FPS

        self.setAlignment(Qt.AlignCenter)  
        # 'Frame bekleniyor...' metnini sadece bir kez eklemek için
        self.waiting_text_item = None  
        self.testing = test


        # Telemetri label'ını oluştur (stil ayarlarıyla birlikte)
        self.telemetry_label = QLabel()
        self.telemetry_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 16px;
                background-color: rgba(0, 0, 0, 150);
                padding: 5px;
                border-radius: 5px;
            }
        """)
        self.telemetry_label.setAlignment(Qt.AlignCenter)
        self.telemetry_label.setText("Veriler bekleniyor...")  # Başlangıçta bekleme mesajı

        # Telemetri güncelleme timer'ı
        self.telemetry_timer = QTimer(self)
        self.telemetry_timer.timeout.connect(self.update_telemetry)
        self.telemetry_timer.start(500)


    def update_telemetry(self):
        try:
            telemetry_data = self.r.get("konum_bilgileri")  # JSON bekleniyor
            #logger.debug(f"telemetry_data: {telemetry_data}")
            try:
                if telemetry_data:
                        vehicles = json.loads(telemetry_data.decode('utf-8'))
                        #print(f"vehicles: {vehicles}")

                        for vehicle in vehicles:
                            if vehicle.get("takim_numarasi") == 5:
                                hiz = vehicle.get("iha_hizi")
                                irtifa = vehicle.get("iha_irtifa")
                                lat = vehicle.get("iha_enlem")
                                lon = vehicle.get("iha_boylam")
                                gr_speed = hiz
                                air_speed = hiz*1.2
                                mod = vehicle.get("mod")
                                # print(f"irtifa: {irtifa}")
                                # print(f"lat: {lat}")
                                # print(f"lon: {lon}")
                                # print(f"gr_speed: {gr_speed}")
                                # print(f"air_speed: {air_speed}")

                else:
                        hiz = 0
                        irtifa = 0
                        lat = 0
                        lon = 0
                        gr_speed = 0
                        air_speed = 0
                        mod = "N/A"
            except json.JSONDecodeError:
                    logger.debug("[ERROR] Telemetri verisi JSON formatında değil veya bozuk!")

            blist = self.r.get("blacklist").decode('utf-8') if self.r.get("blacklist") else None
            if blist is None:
                blist = "----"





            # hezarfen testi ------------------------------------------------------------------
            # lat = self.r.get("lat")
            # lon = self.r.get("lon")
            # irtifa = self.r.get("alt")
            # gr_speed = self.r.get("ground")
            # air_speed = self.r.get("air")


            
            mod = self.r.get("mod").decode('utf-8') if self.r.get("mod") else "N/A"
            blist_ = "Team2, Team3"



            # HTML formatında telemetri bilgisi oluştur
            telemetry_html = f"""
            <div style="font-family: Arial; color: white; font-size: 14px; background-color: rgba(0, 0, 0, 0.7); padding: 8px; border-radius: 5px;">
                <table style="width: 100%; border-collapse: collapse; color: rgb(255,255,255); font-size: 16px;">
                    <tr>
                        <td style="padding: 2px;"><b>Mod:</b> {mod}</td>
                        <td style="padding: 2px;"><b>İrtifa:</b> {irtifa} m</td>
                        <td style="padding: 2px;"><b>Gr Speed:</b> {gr_speed:.2f} m/s</td>
                    </tr>
                    <tr>
                        <td style="padding: 2px;"><b>Enlem:</b> {lat:.6f}</td>
                        <td style="padding: 2px; padding-right: 20px;"><b>Boylam:</b> {lon:.6f}</td>
                        <td style="padding: 2px;"><b>Air Speed:</b> {air_speed:.2f} m/s</td>
                    </tr>
                    <tr>
                    <td colspan="3" style="padding: 2px;">
                        <tr style="color: rgb(255,255,255); font-size: 13px;">
                            <td colspan="3" style="padding: 2px;">
                                <b>KARA Takımlar:</b> {blist}   </td>
                    </tr> 
                    <tr style="color: rgb(255,255,255); font-size: 13px;">
                        <td colspan="3" style="padding: 2px;">
                            <b>KARA Takımlar Öneri:</b> {blist_}
                        </td>
                    <!--
                    </tr>
                    <tr style="color: rgb(255,255,255); font-size: 14px;">
                        <td colspan="3" style="padding: 2px;">
                            <b>KARA takımlar:</b> {blist}
                        </td>
                    </tr>
                    -->
                </table>
            </div>
            """
        
        
            self.telemetry_label.setText(telemetry_html)
            #     self.telemetry_label.setText(f"Hız: {hiz} \n\n İrtifa: {irtifa} | Lat: {lat} | Lon: {lon} \n\n Kilitlenme Dörtgeni: {bbox}  |  HSS: {222}")
        except Exception as e:
            logger.debug(f"[ERROR] Telemetri verisi okunamadı: {e}")

###############################################################################sonradan ekleme sonu
    def update_frame(self):
        """Redis'ten 'frame' başlıklı canlı görüntüyü çek ve güncelle."""
        try:
            frame_data = self.r.get("frame")  if self.testing == 0 else self.r.get("frame_tracker")

            if frame_data is None:
                #logger.debug("[WARNING] Redis'te 'frame' verisi bulunamadı!")
               # 'Frame bekleniyor' yazısını yalnızca bir kez ekle
                if self.waiting_text_item is None:
                    self.scene.clear()  # Önceki görüntüyü temizle
                    self.waiting_text_item = QGraphicsTextItem("Frame bekleniyor...")
                    self.waiting_text_item.setFont(QFont("Arial", 20))
                    self.waiting_text_item.setDefaultTextColor(Qt.red)
                    self.scene.addItem(self.waiting_text_item)
                return
            
            np_img = np.frombuffer(frame_data, dtype=np.uint8)
            img = cv2.imdecode(np_img, cv2.IMREAD_COLOR)

            if img is not None:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                h, w, ch = img.shape
                bytes_per_line = ch * w
                qimg = QImage(img.data, w, h, bytes_per_line, QImage.Format_RGB888)
                self.pixmap = QPixmap.fromImage(qimg)
                self.scene.clear()
                self.image_item = QGraphicsPixmapItem(self.pixmap)
                self.scene.addItem(self.image_item)
                #logger.debug("[INFO] Canlı görüntü Redis'ten alındı ve güncellendi!")
            else:
                logger.debug("[ERROR] Redis'ten gelen 'frame' verisi bozuk olabilir!")
        except Exception as e:
            logger.debug(f"[ERROR] Canlı görüntü alınırken hata oluştu: {e}")

    def resizeEvent(self, event):
        """Pencere boyutu değiştiğinde görüntüyü yeniden boyutlandır."""
        super().resizeEvent(event)
        if self.image_item:
            self.fitInView(self.image_item, Qt.KeepAspectRatio)


### Ana Arayüz (GUI)
class MainWindow(QMainWindow):
    def __init__(self, center):
        super().__init__()
        self.setWindowTitle("ITUNOM INTERFACE")
        screen = QApplication.primaryScreen().geometry()
        width = int(screen.width() * 0.8)
        height = int(screen.height() * 0.8)
        self.setGeometry(0, 0, width, height)
        self.map_center = center
        self.blacklist_teams = [ 0 for _ in range(17)]

        self.setStyleSheet("background-color: rgb(32, 32, 32);")  # arkaplan rengi

        try:
            self.r = redis.Redis(host='localhost', port=6379, db=0)
        except redis.ConnectionError:
            logger.debug("[ERROR] Redis bağlantısı sağlanamadı! Lütfen Redis servisini kontrol edin.")
            self.r = None  # Redis bağlantısı başarısız olursa None olarak ayarla

        self.r.delete("blacklist_teams")  # Önceki blacklist verisini temizle

        # Komut çalıştırmak için QProcess
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.on_process_stdout)
        self.process.readyReadStandardError.connect(self.on_process_stderr)

        self.update_map_button = QPushButton("MAP")
        #self.test_button = QPushButton("Test")

        for i in range(1, 17):
            setattr(self, f"black_list_teams{i}", QPushButton(f"Team {i}"))

        for i in range(1, 15):
            setattr(self, f"track_buttons{i}", QPushButton(f"Track {i}"))

        # for i in range(1,8):
        #     setattr(self, f"button{i}", QPushButton(f""))
        self.button1 = QPushButton("Görüntülü")
        self.button2 = QPushButton("Konumlu")
        self.button3 = QPushButton("Auto")
        self.button4 = QPushButton("Sekiz")
        self.button5 = QPushButton("Kamikze")   
        self.button6 = QPushButton("Av Modu")
        self.button7 = QPushButton("HSS")

        # for button in [self.update_map_button, self.test_button, self.black_list_teams1, self.black_list_teams2, self.black_list_teams3, self.black_list_teams4, self.black_list_teams5, self.black_list_teams6, self.black_list_teams7,
        #  self.black_list_teams8, self.black_list_teams9, self.black_list_teams10, self.black_list_teams11, self.black_list_teams12, self.black_list_teams13, self.black_list_teams14, self.black_list_teams15, self.black_list_teams16]:
        #     button.setStyleSheet("background-color: rgb(238, 222, 8); border-radius: 4px; padding: 3px;")

        self.update_map_button.clicked.connect(lambda: self.update_map_in_redis(self.map_center[0],self.map_center[1]))
        #self.test_button.clicked.connect(lambda: self.update_map_in_redis(self.map_center[0],self.map_center[1]))

        self.update_map_button.setStyleSheet(style.map_button_style)

        for i in range(1, 17):
            button = getattr(self, f"black_list_teams{i}")
            button.setStyleSheet(style.blist_buttons_style)
            button.clicked.connect(lambda checked, x=i: self.blacklist(x))
            self.r.set(f"blist_team{i}", 0)

        
        for i in range(1, 15):
            button = getattr(self, f"track_buttons{i}")
            button.setStyleSheet(style.track_buttons_def_style)
            button.clicked.connect(lambda checked, x=i: self.track(x))
            self.r.set(f"track_button{i}", 0)  # Redis'te başlangıç değeri olarak 0 ayarla


        for i in range(1, 8):
            button = getattr(self, f"button{i}")
            button.setStyleSheet(style.mode_buttons_def_style)
            button.clicked.connect(lambda checked, x=i: self.update_mode(x))


        
# --- Terminal bölümü için widget'lar ---
        # Multi-line çıktı göstermek için QTextEdit
        # self.terminal_output = QTextEdit()
        # self.terminal_output.setReadOnly(True)
        # self.terminal_output.setPlaceholderText("Terminal çıktısı burada gözükecek...")
        # # Metin rengi yeşil, arka plan siyah, çerçeve kırmızı, hafif yuvarlak köşeler
        # self.terminal_output.setStyleSheet(style.terminal_output_style)

        # # Tek satırlık komut girişi için QLineEdit
        # self.terminal_input = QLineEdit()
        # self.terminal_input.setPlaceholderText("Komut girip Enter’a basın")
        # self.terminal_input.returnPressed.connect(self.handle_terminal_input)
        # self.terminal_input.setStyleSheet(style.terminal_input_style)

        self.map_view = FlightMap(self.r, self.map_center)  # Harita alanını oluştur
        self.live_feed = LiveFeed(self.r)  # Canlı görüntü alanını oluştur
        self.map_view.setMinimumSize(400, 300)
        self.live_feed.setMinimumSize(400, 300)  # Canlı video için minimum boyut

        # Live Feed ve Telemetri için container
        live_container = QWidget()
        live_layout = QVBoxLayout(live_container)
        live_layout.setContentsMargins(0, 0, 0, 0)  # Kenar boşluklarını kaldır
        live_layout.setSpacing(0)  # Widget'lar arası boşluğu kaldır
        


        # --- Track butonları için GridLayout ile container ---
        track_buttons_container = QWidget()
        track_buttons_grid = QGridLayout(track_buttons_container)
        track_buttons_grid.setContentsMargins(0, 0, 0, 0)
        track_buttons_grid.setSpacing(2)

        buton_sayisi = 14
        sutun_sayisi = 7   # Her satırda 7 buton (2 satır olacak)
        for idx in range(buton_sayisi):
            btn = getattr(self, f"track_buttons{idx+1}")
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            satir = idx // sutun_sayisi
            sutun = idx % sutun_sayisi
            track_buttons_grid.addWidget(btn, satir, sutun)


        # Canlı video
        live_layout.addWidget(self.live_feed, stretch=13)
        # Terminal
        # live_layout.addWidget(self.terminal_output, stretch=2)         #terminal pencerelerini eklemek için
        # live_layout.addWidget(self.terminal_input,  stretch=1)
        # Telemetri
        live_layout.addWidget(self.live_feed.telemetry_label, stretch=3)
        # self.terminal_output.setMaximumHeight(100)
        # self.terminal_input.setMaximumHeight(30)
        self.live_feed.telemetry_label.setMaximumWidth(610)
        live_layout.addWidget(track_buttons_container)

        
        # Ana layout
        main_layout = QHBoxLayout()
        main_layout.addWidget(self.map_view, stretch=2)  # Harita 2/3 alan
        main_layout.addWidget(live_container, stretch=1)  # Kamera+Telemetri 1/3 alan burdada değişikjlik var

        #Update Map Butonu için Container
        update_map_container = QWidget()
        update_map_layout = QHBoxLayout(update_map_container)
        update_map_layout.setContentsMargins(0, 0, 0, 0)
        update_map_layout.setSpacing(0)
        update_map_layout.addWidget(self.update_map_button)
        # update_map_container.setMinimumWidth(100)  # Gerekirse minimum genişlik ayarlayın
        # update_map_container.setMaximumHeight(100)  # Gerekirse maximum genişlik ayarlayın
        update_map_container.setFixedHeight(30)
        self.update_map_button.setFixedHeight(27)
        self.update_map_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # mode butonları için
        button_layout = QHBoxLayout()
        for i in range(1, 8):
            button = getattr(self, f"button{i}")
            button_layout.addWidget(button)


        # Diğer(blist) Butonlar için Container
        other_buttons_container = QWidget()
        other_buttons_layout = QHBoxLayout(other_buttons_container)
        other_buttons_layout.setContentsMargins(0, 0, 0, 0)
        #other_buttons_layout.addWidget(self.test_button)
        for i in range(1, 17):
            other_buttons_layout.addWidget(getattr(self, f"black_list_teams{i}"))


        # Parlaklık ikonunu gösteren label
        # Parlaklık ☀️ ikonu
        self.brightness_icon = QLabel("☀️")
        self.brightness_icon.setStyleSheet("font-size: 20px; color: yellow;")
        self.brightness_icon.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        # Slider (küçük)
        self.brightness_slider = QSlider(Qt.Horizontal)
        self.brightness_slider.setMinimum(-100)
        self.brightness_slider.setMaximum(100)
        self.brightness_slider.setValue(0)
        self.brightness_slider.setFixedWidth(80)
        self.brightness_slider.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.brightness_slider.setStyleSheet("""
            QSlider::groove:horizontal { background: #333; height: 4px; border-radius: 2px;}
            QSlider::handle:horizontal { background: #FFD700; border: 1px solid #888; width: 10px; margin: -3px 0; border-radius: 5px;}
        """)
        self.brightness_slider.sliderReleased.connect(self.my_brightness_function)
        self.brightness_value = QLabel("0")
        self.brightness_value.setStyleSheet("color: white; font-size: 13px; min-width: 25px;")
        self.brightness_value.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.brightness_slider.valueChanged.connect(
            lambda v: self.brightness_value.setText(f"{v/10}"))


        # Parlaklık için container
        self.brightness_widget = QWidget()
        self.brightness_layout = QHBoxLayout(self.brightness_widget)
        self.brightness_layout.setContentsMargins(0, 0, 0, 0)
        self.brightness_layout.setSpacing(2)
        self.brightness_layout.addWidget(self.brightness_icon)
        self.brightness_layout.addWidget(self.brightness_slider)
        self.brightness_layout.addWidget(self.brightness_value)
        self.brightness_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        # En sona ekle
        other_buttons_layout.addWidget(self.brightness_widget)





        other_buttons_container.setFixedHeight(27)
        other_buttons_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # Ana Update Butonları Layout
        update_buttons_layout = QHBoxLayout()
        update_buttons_layout.setContentsMargins(0, 0, 0, 0)
        update_buttons_layout.addWidget(update_map_container, 1)
        update_buttons_layout.addWidget(other_buttons_container, 40)
        #update_buttons_layout.addWidget(track_buttons_container, 40)

 


        layout_with_buttons = QVBoxLayout()
        layout_with_buttons.addLayout(main_layout)
        layout_with_buttons.addLayout(button_layout)
        layout_with_buttons.addLayout(update_buttons_layout)


        # Sabit boyut yerine minimum boyut ve esnek boyutlandırma tanımlamaları
        self.map_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.live_feed.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        container = QWidget()
        container.setLayout(layout_with_buttons)
        self.setCentralWidget(container)
        QTimer.singleShot(100, self.center_window)  # 100ms gecikmeli çağır, tam ekran hesaplanması için



    def handle_terminal_input(self):
        cmd = self.terminal_input.text().strip()
        if not cmd:
            return

        # GUI'ye echo
        self.terminal_output.append(f"<b>> {cmd}</b>")

        # Komutu parse et (shlex, tırnakları da düzgün işler)
        parts = shlex.split(cmd)
        program = parts[0]
        args = parts[1:]

        # QProcess ile başlat
        self.process.start(program, args)

        # Input'u temizle
        self.terminal_input.clear()


    def on_process_stdout(self):
            data = self.process.readAllStandardOutput().data().decode('utf-8')
            self.terminal_output.append(data)

    def on_process_stderr(self):
            data = self.process.readAllStandardError().data().decode('utf-8')
            # Hataları kırmızı renkle göstermek için
            self.terminal_output.append(f"<span style='color:red'>{data}</span>")



    def update_map_in_redis(self, lat, lon):
        try:
            map_path = fetch_large_map(lat, lon, zoom= 18 if test == 0 else 16)  # Harita dosyasını al
            if not map_path:
                logger.debug("[ERROR] Harita indirilemedi!")
                return

            with open(map_path, "rb") as f:
                map_data = f.read()

                if len(map_data) < 10000:  
                    logger.debug("[ERROR] Harita çok küçük veya bozuk olabilir!")
                    return

                self.r.set("map", map_data)  # Harita artık "map" key'i ile Redis'e kaydediliyor!
                logger.debug("[INFO] Yeni 9 parçalı harita Redis'e kaydedildi!")
        except Exception as e:
            logger.debug(f"[ERROR] Harita güncellenirken hate oluştu: {e}")

    def center_window(self):
        """Pencereyi tam ekranın ortasına taşır."""
        self.show()  # Önce pencereyi göster, böylece tam boyut hesaplanabilir

        screen_geometry = QApplication.primaryScreen().geometry()  # Ana ekranın çözünürlüğünü al
        window_geometry = self.frameGeometry()  # Pencerenin boyutlarını al

        # Ekran merkezini hesapla
        center_x = (screen_geometry.width() - window_geometry.width()) // 2
        center_y = (screen_geometry.height() - window_geometry.height()) // 2

        self.move(center_x, center_y)  # Pencereyi hesaplanan konuma taşı



    def update_mode(self, value):

        self.r.set("guid", value)

        # BUtonlar
        buttons = {
            1: self.button1,
            2: self.button2,
            3: self.button3,
            4: self.button4,
            5: self.button5,
            6: self.button6,
            7: self.button7,
        }
        if value == 5:
            self.r.set("kamikaze_buton", "True")

        # Hepsine önce default stil ver
        for btn in buttons.values():
            btn.setStyleSheet(style.mode_buttons_def_style)

        # Tıklanan değere karşılık gelen butona özel stil uygula
        if value in buttons:
            buttons[value].setStyleSheet(style.mode_buttons_selct_style)



    def blacklist(self,number):

        value =0
        # if self.r.get(f"blist_team{number}") == b'1':
        #     value = 0
        #     button = getattr(self, f"black_list_teams{number}")
        #     button.setStyleSheet(style.def_style_blist)
        # else:
        #     value = 1
        #     button = getattr(self, f"black_list_teams{number}")
        #     button.setStyleSheet(style.selct_style_blist)

        team_name = f"{number}"

        if self.blacklist_teams[number-1] == 0:
            self.blacklist_teams[number-1] = 1
            self.r.rpush("blacklist_teams", team_name)
            button = getattr(self, f"black_list_teams{number}")
            button.setStyleSheet(style.selct_style_blist)

        elif self.blacklist_teams[number-1] == 1:
            self.blacklist_teams[number-1] = 0
            self.r.lrem("blacklist_teams", 0, team_name)
            button = getattr(self, f"black_list_teams{number}")
            button.setStyleSheet(style.def_style_blist)

        logger.debug(f"[INFO] Blacklist {number} komutu gönderildi!")


    def track(self, number):
        """Takım numarasına göre takip modunu değiştirir."""
        
        buttons = {
            1: self.track_buttons1,
            2: self.track_buttons2,
            3: self.track_buttons3,
            4: self.track_buttons4,
            5: self.track_buttons5,
            6: self.track_buttons6,
            7: self.track_buttons7,
            8: self.track_buttons8,
            9: self.track_buttons9,
            10: self.track_buttons10,
            11: self.track_buttons11,
            12: self.track_buttons12,
            13: self.track_buttons13,
            14: self.track_buttons14
        }
        # Hepsine önce default stil ver
        for btn in buttons.values():
            btn.setStyleSheet(style.track_buttons_def_style)

        # Tıklanan değere karşılık gelen butona özel stil uygula
        if number in buttons:
            current_value = self.r.get(f"track_button{number}")
            if current_value is None or current_value.decode('utf-8') == '0':
                new_value = 1
                buttons[number].setStyleSheet(style.track_buttons_selct_style)
            else:
                new_value = 0
                buttons[number].setStyleSheet(style.track_buttons_def_style)

            self.r.set(f"track_button{number}", new_value)
            logger.debug(f"[INFO] Takip modu {number} için {'aktif' if new_value else 'pasif'} edildi!")

            
    def my_brightness_function(self):
        value = self.brightness_slider.value()
        logger.debug(f"Parlaklık değeri: {value}")
        self.r.set("exposure", value)

### Ana Uygulama
if __name__ == "__main__":
    test = 1
    app = QApplication(sys.argv) 
    window = MainWindow(center=[41.10108, 28.55196])
    window.show()  # Önce pencereyi göster
    window.center_window()  # Sonra ekranın ortasına yerleştir
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    sys.exit(app.exec_())