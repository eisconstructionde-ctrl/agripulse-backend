import os
import json

# Render bulut ortamında kimlik doğrulama ayarı
token_data = os.environ.get("EARTHENGINE_TOKEN")
if token_data:
    config_dir = os.path.expanduser("~/.config/earthengine")
    os.makedirs(config_dir, exist_ok=True)
    with open(os.path.join(config_dir, "credentials"), "w") as f:
        f.write(token_data)
        import ee
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List

# 1. Earth Engine Başlatma
try:
    ee.Initialize(project='agri-core-uk')
    print("Google Earth Engine API sunucusu için başarıyla başlatıldı.")
except Exception as e:
    print(f"EE Başlatma Hatası: {e}")

# 2. FastAPI Uygulamasını Tanımlıyoruz (Uvicorn'un aradığı 'app' burası)
app = FastAPI(title="AgriPulse Uydu Analiz API'si")

# 3. Veri Modeli (FlutterFlow'un bize göndereceği koordinat yapısı)
class TarlaAlanı(BaseModel):
    koordinatlar: List[List[float]] # [[boylam, enlem], [boylam, enlem], ...]

@app.get("/")
def ana_sayfa():
    return {"durum": "Sistem Aktif", "mesaj": "AgriPulse Uydu API'sine Hoş Geldiniz!"}

@app.post("/analiz/ndvi")
def ndvi_analizi_yap(tarla: TarlaAlanı):
    try:
        # Gelen koordinatları EE Polygon formatına çeviriyoruz
        polygon_geometrisi = ee.Geometry.Polygon([tarla.koordinatlar])

        # Sentinel-2 uydusundan en temiz görüntüyü filtreliyoruz
        görüntü = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                   .filterBounds(polygon_geometrisi)
                   .filterDate('2026-05-01', '2026-06-01')
                   .sort('CLOUDY_PIXEL_PERCENTAGE')
                   .first())

        # NDVI Hesaplama
        ndvi = görüntü.normalizedDifference(['B8', 'B4'])

        # Bölgesel Ortalama Hesaplama (Reducer)
        ortalama_ndvi = ndvi.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=polygon_geometrisi,
            scale=10,
            maxPixels=1e9
        )

        # Skoru sayısal değere çeviriyoruz
        skor = ortalama_ndvi.get('nd').getInfo()

        if skor is None:
            raise HTTPException(status_code=400, detail="Seçilen alanda geçerli uydu verisi bulunamadı.")

        return {
            "durum": "Basarili",
            "ortalama_ndvi": round(skor, 4),
            "tavsiye": "Deger dusuk. Tarla bos olabilir veya acil gubreleme/sulama ihtiyaci olabilir." if skor < 0.2 else "Bitki sagligi yerinde."
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
