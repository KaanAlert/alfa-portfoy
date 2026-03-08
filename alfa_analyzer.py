"""
ALFA Portföy Tarayıcı v2
Rate limit sorunu çözüldü - toplu veri çekme + retry
"""

import yfinance as yf
import json
import os
import time
import random
import requests
from datetime import datetime, date

# ─────────────────────────────────────────
# AYARLAR
# ─────────────────────────────────────────

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

TOP_N = 5

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

FILTRELER = {
    "pddd_max": 2.0,
    "fk_max": 10.0,
    "fna_max": 6.0,
    "ozs_min": 15.0,
    "efk_min": 10.0,
    "nk_min": 5.0,
}

PORTFOY_DOSYASI = "onceki_portfoy.json"

# ─────────────────────────────────────────
# TOPLU VERİ ÇEKME (Rate limit dostu)
# ─────────────────────────────────────────

def toplu_veri_cek(tickers: list, batch_size: int = 10) -> dict:
    """
    Hisseleri küçük gruplar halinde çeker.
    Her grup arasında bekleme yapar → rate limit engeli aşılır.
    """
    tum_info = {}
    gruplar = [tickers[i:i+batch_size] for i in range(0, len(tickers), batch_size)]

    for gi, grup in enumerate(gruplar):
        print(f"\n  📦 Grup {gi+1}/{len(gruplar)}: {[t.replace('.IS','') for t in grup]}")

        for deneme in range(3):  # 3 deneme hakkı
            try:
                # Tek ticker yerine grup olarak çek
                data = yf.download(
                    tickers=grup,
                    period="5d",
                    auto_adjust=True,
                    progress=False,
                    threads=False,
                )
                print(f"    ✓ Fiyat verisi alındı")
                break
            except Exception as e:
                print(f"    ⚠️  Deneme {deneme+1}: {e}")
                time.sleep(5)

        # Her hisse için info ayrı çek ama yavaşça
        for ticker in grup:
            for deneme in range(3):
                try:
                    h = yf.Ticker(ticker)
                    info = h.fast_info  # fast_info daha az istek atar
                    basic = h.info
                    tum_info[ticker] = basic
                    print(f"    ✓ {ticker.replace('.IS','')}")
                    # Rastgele bekleme: rate limit'i önler
                    time.sleep(random.uniform(1.5, 3.0))
                    break
                except Exception as e:
                    print(f"    ⚠️  {ticker}: deneme {deneme+1} - {str(e)[:50]}")
                    time.sleep(random.uniform(3, 6))

        # Gruplar arası bekleme
        if gi < len(gruplar) - 1:
            bekleme = random.uniform(8, 12)
            print(f"  ⏳ Grup arası bekleme: {bekleme:.0f}s")
            time.sleep(bekleme)

    return tum_info


def info_den_metrik_cikart(ticker: str, info: dict) -> dict | None:
    """yfinance info dict'inden metrikleri çıkarır."""
    try:
        if not info:
            return None

        kod = ticker.replace(".IS", "")

        pddd = info.get("priceToBook")
        fk = info.get("trailingPE")
        fna = info.get("enterpriseToEbitda")
        roe = info.get("returnOnEquity")
        ebitda_margin = info.get("ebitdaMargins")
        profit_margin = info.get("profitMargins")
        sektor = info.get("sector", "Bilinmiyor")
        fiyat = info.get("currentPrice") or info.get("regularMarketPrice", 0)

        # Geçersiz değerleri filtrele
        ozs = round(roe * 100, 2) if roe and abs(roe) < 100 else None
        efk = round(ebitda_margin * 100, 2) if ebitda_margin and abs(ebitda_margin) < 10 else None
        nk = round(profit_margin * 100, 2) if profit_margin and abs(profit_margin) < 10 else None
        pddd = round(pddd, 3) if pddd and 0 < pddd < 100 else None
        fk = round(fk, 2) if fk and 0 < fk < 1000 else None
        fna = round(fna, 2) if fna and 0 < fna < 100 else None

        # En az PD/DD veya ÖZS olmalı
        if pddd is None and ozs is None:
            return None

        return {
            "ticker": kod,
            "sektor": sektor,
            "fiyat": fiyat,
            "pddd": pddd,
            "fk": fk,
            "fna": fna,
            "ozs": ozs,
            "efk": efk,
            "nk": nk,
        }

    except Exception as e:
        print(f"    ⚠️  Metrik çıkarma hatası {ticker}: {e}")
        return None


# ─────────────────────────────────────────
# ALFA ALGORİTMASI
# ─────────────────────────────────────────

def skor_hesapla(s: dict) -> int:
    puan = 0
    if s["pddd"] and s["pddd"] <= 2.0:
        puan += 30 if s["pddd"] <= 1.0 else 30 * (2.0 - s["pddd"])
    if s["fk"] and 0 < s["fk"] <= 10:
        puan += 20 * (1 - s["fk"] / 10)
    if s["fna"] and 0 < s["fna"] <= 6:
        puan += 15 * (1 - s["fna"] / 6)
    if s["ozs"] and s["ozs"] >= 15:
        puan += min(20, 20 * (s["ozs"] - 15) / 85)
    if s["efk"] and s["efk"] >= 10:
        puan += min(10, 10 * (s["efk"] - 10) / 90)
    if s["nk"] and s["nk"] >= 5:
        puan += min(5, 5 * (s["nk"] - 5) / 95)
    return round(puan)


def filtre_gec(s: dict) -> bool:
    f = FILTRELER
    if not s["pddd"] or s["pddd"] > f["pddd_max"]: return False
    if s["fk"] and (s["fk"] <= 0 or s["fk"] > f["fk_max"]): return False
    if s["fna"] and (s["fna"] <= 0 or s["fna"] > f["fna_max"]): return False
    if not s["ozs"] or s["ozs"] < f["ozs_min"]: return False
    if not s["efk"] or s["efk"] < f["efk_min"]: return False
    if not s["nk"] or s["nk"] < f["nk_min"]: return False
    return True


# ─────────────────────────────────────────
# PORTFÖY KARŞILAŞTIRMA
# ─────────────────────────────────────────

def onceki_portfoyu_yukle() -> list:
    try:
        with open(PORTFOY_DOSYASI, "r", encoding="utf-8") as f:
            return json.load(f).get("portfoy", [])
    except FileNotFoundError:
        return []


def portfoyu_kaydet(portfoy: list, detaylar: list):
    with open(PORTFOY_DOSYASI, "w", encoding="utf-8") as f:
        json.dump({
            "tarih": date.today().isoformat(),
            "portfoy": portfoy,
            "detaylar": detaylar
        }, f, ensure_ascii=False, indent=2)


def degisiklikleri_bul(onceki: list, yeni: list) -> dict:
    o, y = set(onceki), set(yeni)
    return {
        "girenler": list(y - o),
        "cikanlar": list(o - y),
        "kalanlar": list(o & y),
        "degisti": o != y,
    }


# ─────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────

def telegram_gonder(mesaj: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"\n--- MESAJ ---\n{mesaj}\n---")
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": mesaj, "parse_mode": "HTML"},
            timeout=15
        )
        r.raise_for_status()
        print("✅ Telegram mesajı gönderildi.")
        return True
    except Exception as e:
        print(f"❌ Telegram hatası: {e}")
        return False


def rapor_olustur(top5, passing, degisiklik, onceki) -> str:
    bugun = datetime.now().strftime("%d.%m.%Y %H:%M")
    em = lambda s: "🟢" if s >= 70 else "🟡" if s >= 45 else "🔴"

    if not onceki:
        baslik = "🚀 <b>ALFA PORTFÖY — İLK ANALİZ</b>"
    elif degisiklik["degisti"]:
        baslik = "🔔 <b>ALFA PORTFÖY — PORTFÖY DEĞİŞTİ!</b>"
    else:
        baslik = "📊 <b>ALFA PORTFÖY — GÜNLÜK RAPOR</b>"

    mesaj = f"{baslik}\n📅 {bugun}\n{'─'*28}\n\n<b>⭐ TOP {TOP_N} — ALFA SEÇİMİ</b>\n"

    for i, h in enumerate(top5, 1):
        yeni = " 🆕" if h["ticker"] in degisiklik.get("girenler", []) else ""
        mesaj += f"""
{em(h['skor'])} <b>#{i} {h['ticker']}</b>{yeni}
   Skor: <b>{h['skor']}/100</b>
   PD/DD: {h['pddd'] or '—'}  |  F/K: {h['fk'] or '—'}
   ÖZS: %{h['ozs'] or '—'}  |  EFK: %{h['efk'] or '—'}
"""

    if degisiklik["degisti"] and onceki:
        mesaj += f"\n{'─'*28}\n<b>📋 DEĞİŞİKLİKLER</b>\n"
        if degisiklik["girenler"]: mesaj += f"✅ Giren: {', '.join(degisiklik['girenler'])}\n"
        if degisiklik["cikanlar"]: mesaj += f"❌ Çıkan: {', '.join(degisiklik['cikanlar'])}\n"
        if degisiklik["kalanlar"]: mesaj += f"🔄 Kalan: {', '.join(degisiklik['kalanlar'])}\n"
    elif onceki:
        mesaj += f"\n{'─'*28}\n✅ Portföyde değişiklik yok.\n"

    mesaj += f"\n{'─'*28}\n📈 {len(passing)} hisse filtreden geçti\n⚠️ <i>Yatırım tavsiyesi değildir.</i>"
    return mesaj


# ─────────────────────────────────────────
# ANA FONKSİYON
# ─────────────────────────────────────────

def main():
    print("=" * 50)
    print("  ALFA PORTFÖY ANALİZ SİSTEMİ v2")
    print(f"  {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
    print("=" * 50)

    onceki = onceki_portfoyu_yukle()
    print(f"\n📂 Önceki portföy: {onceki or 'Yok (ilk çalışma)'}")

    # Toplu veri çek
    print(f"\n📡 {len(HISSELER)} hisse için veri çekiliyor (rate limit korumalı)...\n")
    tum_info = toplu_veri_cek(HISSELER, batch_size=10)

    # Metrikleri çıkar
    hisseler = []
    for ticker, info in tum_info.items():
        metrik = info_den_metrik_cikart(ticker, info)
        if metrik:
            hisseler.append(metrik)

    print(f"\n✅ {len(hisseler)} hisseden geçerli veri alındı.")

    if not hisseler:
        telegram_gonder("❌ ALFA Sistem Hatası: Hiç veri alınamadı! Rate limit sorunu olabilir.")
        return

    # Analiz
    for h in hisseler:
        h["skor"] = skor_hesapla(h)
        h["gecti"] = filtre_gec(h)

    passing = sorted([h for h in hisseler if h["gecti"]], key=lambda x: x["skor"], reverse=True)
    top5 = passing[:TOP_N]

    print(f"📊 Filtreden geçen: {len(passing)} hisse")
    print(f"🏆 Top {TOP_N}: {[h['ticker'] for h in top5]}")

    if not top5:
        telegram_gonder("⚠️ ALFA: Bugün filtre şartlarını karşılayan hisse bulunamadı.")
        return

    yeni_portfoy = [h["ticker"] for h in top5]
    degisiklik = degisiklikleri_bul(onceki, yeni_portfoy)
    portfoyu_kaydet(yeni_portfoy, top5)

    bugun = datetime.now().weekday()
    if bugun < 5:
        mesaj = rapor_olustur(top5, passing, degisiklik, onceki)
        telegram_gonder(mesaj)
    else:
        print("📅 Bugün borsa kapalı, mesaj gönderilmedi.")

    print("\n✅ Analiz tamamlandı!")


if __name__ == "__main__":
    main()
