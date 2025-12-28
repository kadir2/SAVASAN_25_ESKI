import redis
import json

# Redis'e yazılacak olan veri
data_to_send = {
    "kamikazeBaslangicZamani": {
        "saat": 11,
        "dakika": 44,
        "saniye": 13,
        "milisaniye": 361
    },
    "kamikazeBitisZamani": {
        "saat": 11,
        "dakika": 44,
        "saniye": 27,
        "milisaniye": 874
    },
    "qrMetni": "teknofest2025"
}

try:
    # Varsayılan ayarlarla (localhost:6379) Redis'e bağlan
    # decode_responses=True, Redis'ten okuma yaparken sonucu otomatik string'e çevirir.
    r = redis.Redis(decode_responses=True)
    
    # Python dictionary'sini JSON formatında bir string'e dönüştür
    json_data = json.dumps(data_to_send)
    
    # Veriyi "kamikaze_data" anahtarıyla Redis'e yaz
    r.set("kamikaze_data", json_data)
    
    print("Veri başarıyla Redis'e yazıldı.")
    print(f"Anahtar: kamikaze_data")
    print(f"Değer: {r.get('kamikaze_data')}")

except redis.exceptions.ConnectionError as e:
    print(f"Hata: Redis sunucusuna bağlanılamadı. Lütfen sunucunun çalıştığından emin olun.")
    print(f"Detay: {e}")


def kilitlenme_bilgisini_redise_yaz():
    """
    Belirtilen kilitlenme verisini JSON formatına çevirip Redis'e yazar.
    """
    # Redis'e yazılacak olan kilitlenme verisi
    kilitlenme_verisi = {
        "kilitlenmeBitisZamani": {
            "saat": 11,
            "dakika": 41,
            "saniye": 3,
            "milisaniye": 141
        },
        "otonom_kilitlenme": 1
    }
    
    try:
        # Varsayılan ayarlarla (localhost:6379) Redis'e bağlan
        r = redis.Redis(decode_responses=True)
        r.ping() # Bağlantıyı test et

        # Python dictionary'sini JSON formatında bir string'e dönüştür
        json_veri = json.dumps(kilitlenme_verisi)
        
        # Veriyi "kilitlenme_data" anahtarıyla Redis'e yaz
        anahtar = "lock_data"
        r.set(anahtar, json_veri)
        
        print("Kilitlenme verisi başarıyla Redis'e yazıldı.")
        print(f"Anahtar: {anahtar}")
        print(f"Değer: {r.get(anahtar)}")

    except redis.exceptions.ConnectionError as e:
        print(f"Hata: Redis sunucusuna bağlanılamadı.")
        print(f"Detay: {e}")
    except Exception as e:
        print(f"Beklenmedik bir hata oluştu: {e}")

kilitlenme_bilgisini_redise_yaz()