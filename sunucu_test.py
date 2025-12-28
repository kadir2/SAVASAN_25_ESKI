# ==========================================================
# server.py - Test Sunucu (Flask Simulasyonu)
# ==========================================================

from flask import Flask, request, jsonify
from datetime import datetime
import random
import json

app = Flask(__name__)

# Test kullanıcı bilgileri
USERNAME = 'takimkadi'
PASSWORD = 'takimsifresi'

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

@app.route('/api/giris', methods=['POST'])
def login():
    data = request.get_json()
    print(f"data: {data}")
    if data.get('kadi') == USERNAME and data.get('sifre') == PASSWORD:
        # Başarılı oturum açma: 200 OK
        return '', 200
    else:
        # Geçersiz kimlik: 400 Bad Request
        return 'Invalid credentials', 400

@app.route('/api/sunucusaati', methods=['GET'])
def server_time():
    now = datetime.utcnow()
    return jsonify({
        "gun": now.day,
        "saat": now.hour,
        "dakika": now.minute,
        "saniye": now.second,
        "milisaniye": int(now.microsecond/1000)
    })

@app.route('/api/telemetri_gonder', methods=['POST'])
def telemetry():
    data = request.get_json(force=True)
    print(f"Received telemetry data:", json.dumps(data, indent=2))

    now = datetime.utcnow()
    # Sunucu saati
    sunucu_saati = {
        "gun": now.day,
        "saat": now.hour,
        "dakika": now.minute,
        "saniye": now.second,
        "milisaniye": int(now.microsecond/1000)
    }

    # Gelen değer None ise 0 kullan (Önceki hatayı da önler)
    enlem = data.get("iha_enlem") or 0
    boylam = data.get("iha_boylam") or 0
    irtifa = data.get("iha_irtifa") or 0
    dikilme = data.get("iha_dikilme") or 0
    yonelme = data.get("iha_yonelme") or 0
    yatis = data.get("iha_yatis") or 0
    hiz = data.get("iha_hiz") or 0
    
    # 10 takım için örnek konum listesi oluştur
    konum_listesi = []
    for i in range(1, 11):
        konum_listesi.append({
            # --- YENİ: İstenen sıralamaya göre düzenlendi ---
            "takim_numarasi": i,
            "iha_enlem": round(enlem + random.uniform(-0.002, 0.002), 7),
            "iha_boylam": round(boylam + random.uniform(-0.002, 0.002), 7),
            # --- YENİ: Değerler tam sayıya (integer) çevrildi ---
            "iha_irtifa": int(irtifa + random.uniform(-2, 2)),
            "iha_dikilme": int(dikilme + random.uniform(-5, 5)),
            "iha_yonelme": int((yonelme + random.uniform(-10, 10)) % 360),
            "iha_yatis": int(yatis + random.uniform(-10, 10)),
            "iha_hizi": int(hiz + random.uniform(-5, 5)),
            "zaman_farki": random.randint(0, 500)
        })

    # --- YENİ: Anahtar sırası isteğe göre düzenlendi ---
    response = {
        "sunucusaati": sunucu_saati,
        "konumBilgileri": konum_listesi
    }
    return jsonify(response), 200

@app.route('/api/kilitlenme_bilgisi', methods=['POST'])
def kilitlenme_bilgisi():
    data = request.get_json(force=True)
    print(">>> KİLİTLENME VERİSİ ALINDI:")
    print(json.dumps(data, indent=2))
    return jsonify({"status": "ok", "message": "Kilitlenme verisi başarıyla alındı."}), 200

@app.route('/api/kamikaze_bilgisi', methods=['POST'])
def kamikaze_bilgisi():
    data = request.get_json(force=True)
    print(">>> KAMİKAZE VERİSİ ALINDI:")
    print(json.dumps(data, indent=2))
    response_data = {
        "status": "ok",
        "message": "Kamikaze verisi başarıyla alındı."
    }
    return jsonify({"status": "ok", "message": "Kamikaze verisi başarıyla alındı."}), 200

# ... diğer @app.route'lardan sonra

@app.route('/api/qr/', methods=['GET'])
def qr_coordinates():
    # Örnek bir QR kod koordinatı döndür
    return jsonify({
        "qrEnlem": 41.12345,
        "qrBoylam": 28.67890
    })

@app.route('/api/hss/', methods=['GET'])
def hss_coordinates():
    # Örnek bir Hava Savunma Sistemi (HSS) koordinatı döndür
    return jsonify({
        "hss_latitude": 41.54321,
        "hss_longitude": 28.98765
    })

if __name__ == '__main__':
    # Çalıştırmadan önce: pip install flask
    print("Test sunucusu çalışıyor: http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)


# ==========================================================
# client.py - Test İstemci (Redis Tabanlı)
# ==========================================================