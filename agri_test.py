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
    koordinatlar: List[List[float]]

@app.get("/")
def ana_sayfa():
    return {"durum": "Sistem Aktif", "mesaj": "AgriPulse Uydu Analiz API'sine Hoş Geldiniz!"}

@app.post("/analiz/ndvi")
def ndvi_analizi_yap(tarla: TarlaAlani):
    try:
        if not tarla.koordinatlar or len(tarla.koordinatlar) < 3:
            raise HTTPException(status_code=400, detail="Geçersiz poligon. En az 3 koordinat gereklidir.")
            
        poligon = ee.Geometry.Polygon(tarla.koordinatlar)
        
        # Sadece B4 ve B8 bantları içinde fiziksel olarak veri barındıran resimleri listele
        gorsel_koleksiyonu = (
            ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
            .filterBounds(poligon)
            .filterDate('2025-01-01', '2026-06-01')
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 10))
            # Boş/Hatalı pikselleri listeden elemek için maskeleme filtresi
            .filter(ee.Filter.listContains('system:band_names', 'B8'))
            .filter(ee.Filter.listContains('system:band_names', 'B4'))
        )
        
        # Koleksiyon boş mu kontrol et, boşsa tarihi esnetip tekrar dene
        if gorsel_koleksiyonu.size().getInfo() == 0:
            gorsel_koleksiyonu = (
                ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                .filterBounds(poligon)
                .filterDate('2024-06-01', '2026-06-01') # Tarihi genişlettik
                .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
            )

        # En az bulutlu olan ve veri içeren görüntüyü seç
        en_temiz_gorsel = gorsel_koleksiyonu.sort('CLOUDY_PIXEL_PERCENTAGE').first()
        
        if en_temiz_gorsel is None:
            raise HTTPException(status_code=404, detail="Belirtilen kriterlerde uydu görüntüsü bulunamadı.")
            
        # Resmi garantiye almak için doğrudan yerleşik normalizedDifference fonksiyonunu kullanalım
        ndvi = en_temiz_gorsel.normalizedDifference(['B8', 'B4']).rename('nd')
        
        istatistikler = ndvi.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=poligon,
            scale=10,
            maxPixels=1e9
        )
        
        sonuc = istatistikler.getInfo()
        ortalama_ndvi = sonuc.get('nd')
        
        if ortalama_ndvi is None:
            raise HTTPException(status_code=500, detail="Seçilen alandaki görüntü bozuk veya piksel verisi eksik.")
            
        return {
            "durum": "Başarılı",
            "ortalama_ndvi": round(ortalama_ndvi, 4),
            "mesaj": "Tarla analizi başarıyla tamamlandı."
        }
        
    except HTTPException as http_err:
        raise http_err
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sistem Hatası: {str(e)}")
