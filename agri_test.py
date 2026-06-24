import os
import json

# 1. Render bulut ortamında kimlik doğrulama ayarı
token_data = os.environ.get("EARTHENGINE_TOKEN")
if token_data:
    config_dir = os.path.expanduser("~/.config/earthengine")
    os.makedirs(config_dir, exist_ok=True)
    with open(os.path.join(config_dir, "credentials"), "w") as f:
        f.write(token_data)

# 2. Gerekli Kütüphanelerin Yüklenmesi
import ee
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List

# 3. Earth Engine Başlatma
try:
    ee.Initialize(project='agri-core-uk')
    print("Google Earth Engine API sunucusu için başarıyla başlatıldı.")
except Exception as e:
    print(f"EE Başlatma Hatası: {e}")

# 4. FastAPI Uygulamasını Tanımlıyoruz
app = FastAPI(title="AgriPulse Uydu Analiz API'si")

# 5. Veri Modeli
class TarlaAlani(BaseModel):
    koordinatlar: List[List[float]] # [[boylam, enlem], [boylam, enlem], ...]

@app.get("/")
def ana_sayfa():
    return {"durum": "Sistem Aktif", "mesaj": "AgriPulse Uydu Analiz API'sine Hoş Geldiniz!"}

@app.post("/analiz/ndvi")
def ndvi_analizi_yap(tarla: TarlaAlani):
    try:
        if not tarla.koordinatlar or len(tarla.koordinatlar) < 3:
            raise HTTPException(status_code=400, detail="Geçersiz poligon. En az 3 koordinat gereklidir.")
            
        poligon = ee.Geometry.Polygon(tarla.koordinatlar)
        
        gorsel_koleksiyonu = (
            ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
            .filterBounds(poligon)
            .filterDate('2025-01-01', '2026-06-01')
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 10))
            .sort('CLOUDY_PIXEL_PERCENTAGE')
        )
        
        en_temiz_gorsel = gorsel_koleksiyonu.first()
        
        if en_temiz_gorsel.count().getInfo() == 0:
            raise HTTPException(status_code=404, detail="Belirtilen tarihlerde bulutsuz uydu görüntüsü bulunamadı.")
            
        ndvi = en_temiz_gorsel.normalizedDifference(['B8', 'B4'])
        
        istatistikler = ndvi.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=poligon,
            scale=10,
            maxPixels=1e9
        )
        
        sonuc = istatistikler.getInfo()
        ortalama_ndvi = sonuc.get('nd')
        
        if ortalama_ndvi is None:
            raise HTTPException(status_code=500, detail="Seçilen alanda NDVI hesaplanamadı.")
            
        return {
            "durum": "Başarılı",
            "ortalama_ndvi": round(ortalama_ndvi, 4),
            "mesaj": "Tarla analizi başarıyla tamamlandı."
        }
        
    except HTTPException as http_err:
        raise http_err
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sistem Hatası: {str(e)}")
