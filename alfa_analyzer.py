"""
ALFA Portföy Tarayıcı
Borsa İstanbul - Temel Analiz Motoru
yfinance + Telegram Bildirimi
"""

import yfinance as yf
import json
import os
import requests
from datetime import datetime, date
from typing import Optional

# ─────────────────────────────────────────
# AYARLAR
# ─────────────────────────────────────────

# Telegram (GitHub Secrets'dan gelir)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Portföy büyüklüğü
TOP_N = 5

# Taranacak BIST hisseleri (.IS eki Yahoo Finance için zorunlu)
HISSELER = [
    "ISGSY.IS", "KZBGY.IS", "AVPGY.IS", "INVEO.IS", "KTLEV.IS",
    "ARTMS.IS", "KRSTL.IS", "SANEL.IS", "MACKO.IS", "LMKDC.IS",
    "A1CAP.IS", "ESCOM.IS", "ARASE.IS", "DOAS.IS", "ATATP.IS",
    "GOLTS.IS", "BUCIM.IS", "ORGE.IS", "BANVT.IS", "BULGS.IS",
    "THYAO.IS", "EREGL.IS", "BIMAS.IS", "AKBNK.IS", "GARAN.IS",
    "SAHOL.IS", "KCHOL.IS", "TOASO.IS", "FROTO.IS", "SISE.IS",
    "PETKM.IS", "TUPRS.IS", "ARCLK.IS", "TCELL.IS", "ASELS.IS",
    "PGSUS.IS", "TAVHL.IS", "SOKM.IS", "HEKTS.IS", "LOGO.IS",
    "MGROS.IS", "ULKER.IS", "CCOLA.IS", "AGHOL.IS", "KOZAL.IS",
    "ODAS.IS", "ENKAI.IS", "TKFEN.IS", "MPARK.IS", "VESTL.IS",
]

# Filtre eşikleri (19 aylık analizden)
FILTRELER = {
    "pddd_max": 2.0,
    "fk_max": 10.0,
    "fna_max": 6.0,
    "ozs_min": 15.0,
    "efk_min": 10.0,
    "nk_min": 5.0,
}

# Skor ağırlıkları
AGIRLIKLAR = {
    "pddd": 30,
    "fk": 20,
    "fna": 15,
    "ozs": 20,
    "efk": 10,
    "nk": 5,
}

# Önceki portföy kayıt dosyası
PORTFOY_DOSYASI = "onceki_portfoy.json"


# ─────────────────────────────────────────
# VERİ ÇEKME
# ─────────────────────────────────────────

def hisse_verisi_cek(ticker: str) -> Optional[dict]:
    """Tek hisse için yfinance'dan temel verileri çeker."""
    try:
        hisse = yf.Ticker(ticker)
        info = hisse.info

        # Temel kontrol
        if not info or info.get("quoteType") is None:
            return None

        kod = ticker.replace(".IS", "")

        # Metrikleri al
        pddd = info.get("priceToBook")           # PD/DD
        fk = info.get("trailingPE")              # F/K
        fna = info.get("enterpriseToEbitda")     # FD/FAVÖK ~ FNA proxy
        roe = info.get("returnOnEquity")         # ÖZS Karlılığı (ondalık)
        ebitda_margin = info.get("ebitdaMargins") # EFK Marjı (ondalık)
        profit_margin = info.get("profitMargins") # NK Marjı (ondalık)
        sektor = info.get("sector", "Bilinmiyor")
        piy_deg = info.get("marketCap", 0)
        fiyat = info.get("currentPrice") or info.get("regularMarketPrice", 0)

        # None kontrolü ve dönüşüm
        ozs = round(roe * 100, 2) if roe is not None else None
        efk = round(ebitda_margin * 100, 2) if ebitda_margin is not None else None
        nk = round(profit_margin * 100, 2) if profit_margin is not None else None
        pddd = round(pddd, 3) if pddd is not None else None
        fk = round(fk, 2) if fk is not None else None
        fna = round(fna, 2) if fna is not None else None

        return {
            "ticker": kod,
            "sektor": sektor,
            "fiyat": fiyat,
            "piy_deg": piy_deg,
            "pddd": pddd,
            "fk": fk,
            "fna": fna,
            "ozs": ozs,
            "efk": efk,
            "nk": nk,
        }

    except Exception as e:
        print(f"  ⚠️  {ticker}: {e}")
        return None


def tum_verileri_cek() -> list[dict]:
    """Tüm hisselerin verilerini çeker."""
    print(f"\n📡 {len(HISSELER)} hisse için veri çekiliyor...\n")
    sonuclar = []
    for i, ticker in enumerate(HISSELER, 1):
        print(f"  [{i:2d}/{len(HISSELER)}] {ticker}...", end=" ")
        veri = hisse_verisi_cek(ticker)
        if veri:
            print(f"✓  PD/DD:{veri['pddd']}  F/K:{veri['fk']}  ÖZS:{veri['ozs']}")
            sonuclar.append(veri)
        else:
            print("✗ atlandı")
    print(f"\n✅ {len(sonuclar)} hisse başarıyla alındı.\n")
    return sonuclar


# ─────────────────────────────────────────
# ALFA ALGORİTMASI
# ─────────────────────────────────────────

def skor_hesapla(s: dict) -> int:
    """19 aylık portföy verisiyle kalibre edilmiş ALFA skoru."""
    puan = 0

    # PD/DD (30 puan) — düşük iyi
    if s["pddd"] is not None and s["pddd"] <= 2.0:
        puan += 30 if s["pddd"] <= 1.0 else 30 * (2.0 - s["pddd"])

    # F/K (20 puan) — düşük iyi
    if s["fk"] is not None and 0 < s["fk"] <= 10:
        puan += 20 * (1 - s["fk"] / 10)

    # FNA (15 puan) — düşük iyi
    if s["fna"] is not None and 0 < s["fna"] <= 6:
        puan += 15 * (1 - s["fna"] / 6)

    # ÖZS Karlılığı (20 puan) — yüksek iyi
    if s["ozs"] is not None and s["ozs"] >= 15:
        puan += min(20, 20 * (s["ozs"] - 15) / 85)

    # EFK Marjı (10 puan) — yüksek iyi
    if s["efk"] is not None and s["efk"] >= 10:
        puan += min(10, 10 * (s["efk"] - 10) / 90)

    # NK Marjı (5 puan) — yüksek iyi
    if s["nk"] is not None and s["nk"] >= 5:
        puan += min(5, 5 * (s["nk"] - 5) / 95)

    return round(puan)


def filtre_gec(s: dict) -> bool:
    """Tüm filtre şartlarını karşılıyor mu?"""
    f = FILTRELER

    # Zorunlu metrik: PD/DD
    if s["pddd"] is None or s["pddd"] > f["pddd_max"]:
        return False

    # F/K — boşsa geç (negatif kazanç varsa)
    if s["fk"] is not None and (s["fk"] <= 0 or s["fk"] > f["fk_max"]):
        return False

    # FNA — boşsa geç
    if s["fna"] is not None and (s["fna"] <= 0 or s["fna"] > f["fna_max"]):
        return False

    # ÖZS Karlılığı — zorunlu
    if s["ozs"] is None or s["ozs"] < f["ozs_min"]:
        return False

    # EFK Marjı — zorunlu
    if s["efk"] is None or s["efk"] < f["efk_min"]:
        return False

    # NK Marjı — zorunlu
    if s["nk"] is None or s["nk"] < f["nk_min"]:
        return False

    return True


def analiz_et(hisseler: list[dict]) -> tuple[list, list]:
    """Filtreleme + sıralama yapar. (passing, failing) döner."""
    for h in hisseler:
        h["skor"] = skor_hesapla(h)
        h["gecti"] = filtre_gec(h)

    passing = [h for h in hisseler if h["gecti"]]
    failing = [h for h in hisseler if not h["gecti"]]

    passing.sort(key=lambda x: x["skor"], reverse=True)
    failing.sort(key=lambda x: x["skor"], reverse=True)

    return passing, failing


# ─────────────────────────────────────────
# PORTFÖY KARŞILAŞTIRMA
# ─────────────────────────────────────────

def onceki_portfoyu_yukle() -> list[str]:
    """Önceki günün Top N hisse listesini yükler."""
    try:
        with open(PORTFOY_DOSYASI, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("portfoy", [])
    except FileNotFoundError:
        return []


def portfoyu_kaydet(portfoy: list[str], detaylar: list[dict]):
    """Bugünün portföyünü kaydeder."""
    with open(PORTFOY_DOSYASI, "w", encoding="utf-8") as f:
        json.dump({
            "tarih": date.today().isoformat(),
            "portfoy": portfoy,
            "detaylar": detaylar
        }, f, ensure_ascii=False, indent=2)


def degisiklikleri_bul(onceki: list[str], yeni: list[str]) -> dict:
    """Portföydeki değişiklikleri tespit eder."""
    onceki_set = set(onceki)
    yeni_set = set(yeni)

    return {
        "girenler": list(yeni_set - onceki_set),
        "cikanlar": list(onceki_set - yeni_set),
        "kalanlar": list(onceki_set & yeni_set),
        "degisti": onceki_set != yeni_set,
    }


# ─────────────────────────────────────────
# TELEGRAM BİLDİRİMİ
# ─────────────────────────────────────────

def telegram_gonder(mesaj: str) -> bool:
    """Telegram mesajı gönderir."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️  Telegram bilgileri eksik, mesaj gönderilmedi.")
        print(f"\n--- MESAJ PREVİEW ---\n{mesaj}\n---")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mesaj,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        print("✅ Telegram mesajı gönderildi.")
        return True
    except Exception as e:
        print(f"❌ Telegram hatası: {e}")
        return False


def gunluk_rapor_olustur(top5: list[dict], passing: list[dict],
                          degisiklik: dict, onceki: list[str]) -> str:
    """Günlük Telegram mesajını oluşturur."""

    bugun = datetime.now().strftime("%d.%m.%Y %H:%M")
    emoji_skor = lambda s: "🟢" if s >= 70 else "🟡" if s >= 45 else "🔴"

    # Başlık
    if not onceki:
        baslik = "🚀 <b>ALFA PORTFÖY — İLK ANALİZ</b>"
    elif degisiklik["degisti"]:
        baslik = "🔔 <b>ALFA PORTFÖY — PORTFÖY DEĞİŞTİ!</b>"
    else:
        baslik = "📊 <b>ALFA PORTFÖY — GÜNLÜK RAPOR</b>"

    mesaj = f"""{baslik}
📅 {bugun}
{'─' * 30}

<b>⭐ TOP {TOP_N} — ALFA SEÇİMİ</b>
"""

    for i, h in enumerate(top5, 1):
        yeni_mi = h["ticker"] in degisiklik.get("girenler", [])
        yeni_etiketi = " 🆕" if yeni_mi else ""
        mesaj += f"""
{emoji_skor(h['skor'])} <b>#{i} {h['ticker']}</b>{yeni_etiketi}
   Skor: <b>{h['skor']}/100</b>
   PD/DD: {h['pddd'] or '—'}  |  F/K: {h['fk'] or '—'}  |  FNA: {h['fna'] or '—'}
   ÖZS Karl: %{h['ozs'] or '—'}  |  EFK: %{h['efk'] or '—'}  |  NK: %{h['nk'] or '—'}
"""

    # Değişiklik özeti
    if degisiklik["degisti"] and onceki:
        mesaj += f"\n{'─' * 30}\n<b>📋 PORTFÖY DEĞİŞİKLİKLERİ</b>\n"
        if degisiklik["girenler"]:
            mesaj += f"✅ Giren: {', '.join(degisiklik['girenler'])}\n"
        if degisiklik["cikanlar"]:
            mesaj += f"❌ Çıkan: {', '.join(degisiklik['cikanlar'])}\n"
        if degisiklik["kalanlar"]:
            mesaj += f"🔄 Kalan: {', '.join(degisiklik['kalanlar'])}\n"
    elif onceki:
        mesaj += f"\n{'─' * 30}\n✅ Portföyde değişiklik yok.\n"

    # İstatistik
    mesaj += f"""
{'─' * 30}
<b>📈 TARAMA İSTATİSTİKLERİ</b>
Taranan: {len(passing)} hisse filtreden geçti
Filtre: PD/DD≤{FILTRELER['pddd_max']} | F/K≤{FILTRELER['fk_max']} | ÖZS≥%{FILTRELER['ozs_min']}

⚠️ <i>Yatırım tavsiyesi değildir.</i>"""

    return mesaj


# ─────────────────────────────────────────
# ANA FONKSİYON
# ─────────────────────────────────────────

def main():
    print("=" * 50)
    print("  ALFA PORTFÖY ANALİZ SİSTEMİ")
    print(f"  {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
    print("=" * 50)

    # 1. Önceki portföyü yükle
    onceki_portfoy = onceki_portfoyu_yukle()
    print(f"\n📂 Önceki portföy: {onceki_portfoy or 'Yok (ilk çalışma)'}")

    # 2. Veri çek
    hisseler = tum_verileri_cek()

    if not hisseler:
        print("❌ Hiç veri alınamadı!")
        telegram_gonder("❌ ALFA Sistem Hatası: Hiç veri alınamadı!")
        return

    # 3. Analiz et
    passing, failing = analiz_et(hisseler)
    top5 = passing[:TOP_N]

    print(f"📊 Filtreden geçen: {len(passing)} hisse")
    print(f"🏆 Top {TOP_N}:", [h["ticker"] for h in top5])

    # 4. Değişiklik kontrolü
    yeni_portfoy = [h["ticker"] for h in top5]
    degisiklik = degisiklikleri_bul(onceki_portfoy, yeni_portfoy)

    print(f"\n🔄 Değişiklik: {'EVET' if degisiklik['degisti'] else 'YOK'}")
    if degisiklik["girenler"]:
        print(f"   ✅ Girenler: {degisiklik['girenler']}")
    if degisiklik["cikanlar"]:
        print(f"   ❌ Çıkanlar: {degisiklik['cikanlar']}")

    # 5. Portföyü kaydet
    portfoyu_kaydet(yeni_portfoy, top5)

    # 6. Telegram gönder
    # Şartlar: İlk çalışma VEYA portföy değişti VEYA Pazar değil
    bugun = datetime.now().weekday()  # 0=Pazartesi, 6=Pazar
    borsada_gun = bugun < 5  # Hafta içi

    if borsada_gun:
        mesaj = gunluk_rapor_olustur(top5, passing, degisiklik, onceki_portfoy)
        telegram_gonder(mesaj)
    else:
        print("📅 Bugün borsa kapalı, mesaj gönderilmedi.")

    print("\n✅ Analiz tamamlandı!")


if __name__ == "__main__":
    main()
