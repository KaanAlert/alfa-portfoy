"""
ALFA Portföy Tarayıcı v4 - DÜZELTİLMİŞ
- Hisse listesi: İş Yatırım (HTML parse) + Fallback
- Temel veriler: Yahoo Finance (yfinance)
- Skor bazlı seçim (iyileştirilmiş)
- FIX: TOP_N=10, Error handling, None kontrolleri
"""

import json, os, time, re, requests
from datetime import datetime, date
from bs4 import BeautifulSoup
import yfinance as yf

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TOP_N            = 10  # FIX: 5'den 10'a çıkardık
PORTFOY_DOSYASI  = "onceki_portfoy.json"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Referer": "https://www.isyatirim.com.tr/",
})

def bist_listesi_cek() -> list:
    print("📡 İş Yatırım'dan hisse listesi çekiliyor...")
    url = "https://www.isyatirim.com.tr/tr-tr/analiz/hisse/Sayfalar/Temel-Degerler-Ve-Oranlar.aspx"
    try:
        r = SESSION.get(url, timeout=30)
        soup = BeautifulSoup(r.text, "html.parser")
        kodlar = set()
        for a in soup.find_all("a", href=True):
            m = re.search(r'/hisse/([A-Z]{3,6})', a["href"])
            if m:
                kodlar.add(m.group(1))
        for td in soup.find_all("td"):
            txt = td.get_text(strip=True)
            if re.match(r'^[A-Z]{3,6}$', txt):
                kodlar.add(txt)
        kodlar = sorted(kodlar)
        print(f"  ✅ {len(kodlar)} hisse kodu bulundu")
        return kodlar
    except Exception as e:
        print(f"  ⚠️ Hata: {e}")
        return []

def yedek_bist_listesi() -> list:
    return [
        "AKBNK","AKGRT","AKSA","AKSEN","ALARK","ALBRK","ALGYO","ALKIM","ANACM","ANSGR",
        "ARCLK","ARDYZ","ARASE","ARTMS","ASELS","ATATP","ATGYO","ATLAS","AVPGY","AYDEM",
        "AYGAZ","BAGFS","BANVT","BERA","BIMAS","BIOEN","BORSK","BRISA","BRYAT","BUCIM",
        "BULGS","CEMTS","CIMSA","CLEBI","CWENE","DOAS","DOHOL","DYOBY","ECILC","EGEEN",
        "ENJSA","ENKAI","EREGL","ESCOM","EUPWR","FENER","FROTO","GARAN","GESAN","GLRYH",
        "GOLTS","GOZDE","GRSEL","GUBRF","HALKB","HEKTS","INVEO","IPEKE","ISGYO","ISGSY",
        "ISMEN","ISYAT","ITTFK","IZMDC","KARSN","KAYSE","KCHOL","KLNMA","KMPUR","KONTR",
        "KONYA","KORDS","KOZAA","KOZAL","KRDMD","KRSTL","KTLEV","KZBGY","LMKDC","LOGO",
        "MACKO","MAVI","MGROS","MPARK","NETAS","NTHOL","NUGYO","ODAS","ORGE","OTKAR",
        "OYAKC","PGSUS","PKART","PRDGS","SAHOL","SANEL","SELEC","SISE","SKBNK","SNICA",
        "SOKM","SPSN","TATGD","TCELL","THYAO","TKFEN","TOASO","TSKB","TTKOM","TTRAK",
        "TUKAS","TUPRS","TURSG","ULKER","UMPAS","VAKBN","VESBE","VESTL","YKBNK","ZOREN",
    ]

def safe_float(val):
    """None kontrolü ile güvenli float dönüştürme"""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None

def yahoo_veri_cek(kodlar: list) -> list:
    print(f"\n📡 Yahoo Finance'den {len(kodlar)} hisse verisi çekiliyor...")
    sonuc = []
    basarisiz = 0
    
    for i, kod in enumerate(kodlar):
        try:
            ticker = yf.Ticker(f"{kod}.IS")
            info = ticker.info
            
            # FIX: safe_float ile None kontrolü
            fk   = safe_float(info.get("trailingPE") or info.get("forwardPE"))
            pddd = safe_float(info.get("priceToBook"))
            fna  = safe_float(info.get("enterpriseToEbitda"))
            
            # Yüzde dönüştürmeleri
            ozs = info.get("returnOnEquity")
            if ozs is not None:
                ozs = round(ozs * 100, 2)
            
            efk = info.get("ebitdaMargins")
            if efk is not None:
                efk = round(efk * 100, 2)
            
            nk = info.get("profitMargins")
            if nk is not None:
                nk = round(nk * 100, 2)
            
            sektor = info.get("sector") or info.get("industry") or "Bilinmiyor"
            piy_deger = info.get("marketCap")
            
            # FIX: pddd kontrol et
            if pddd and pddd > 0:
                sonuc.append({
                    "ticker": kod, 
                    "sektor": sektor, 
                    "piy_deger": piy_deger,
                    "fk": fk, 
                    "pddd": pddd, 
                    "fna": fna,
                    "ozs": ozs, 
                    "efk": efk, 
                    "nk": nk,
                })
            
            if (i + 1) % 20 == 0:
                print(f"  {i+1}/{len(kodlar)} işlendi, {len(sonuc)} veri var...")
        
        except Exception as e:
            # FIX: Hata mesajını göster (debug için)
            print(f"  ⚠️ {kod}: {type(e).__name__}")
            basarisiz += 1
        
        time.sleep(0.1)
    
    print(f"  ✅ {len(sonuc)} hisse verisi alındı, {basarisiz} başarısız")
    return sonuc

def skor(s):
    """FIX: Daha dengeli skor fonksiyonu"""
    p = 0.0
    
    # PD/DD (0-20)
    if s["pddd"] and s["pddd"] > 0:
        if s["pddd"] <= 1.0:
            p += 20
        elif s["pddd"] <= 3.5:
            p += 20 * (1 - (s["pddd"] - 1.0) / 2.5)
    
    # F/K (0-20)
    if s["fk"] and 0 < s["fk"] <= 25:
        p += 20 * (1 - s["fk"] / 25)
    
    # ÖZS (0-20)
    if s["ozs"] and s["ozs"] > 0:
        roe_score = min(20, 20 * s["ozs"] / 25)
        p += roe_score
    
    # FAVÖK% (0-20)
    if s["efk"] and s["efk"] > 0:
        ebitda_score = min(20, 20 * s["efk"] / 30)
        p += ebitda_score
    
    # Net Kar% (0-20)
    if s["nk"] and s["nk"] > 0:
        np_score = min(20, 20 * s["nk"] / 15)
        p += np_score
    
    return round(p)

def onceki_yukle():
    try:
        with open(PORTFOY_DOSYASI, "r", encoding="utf-8") as f:
            return json.load(f).get("portfoy", [])
    except FileNotFoundError:
        return []

def kaydet(portfoy, detaylar):
    with open(PORTFOY_DOSYASI, "w", encoding="utf-8") as f:
        json.dump({"tarih": date.today().isoformat(), "portfoy": portfoy, "detaylar": detaylar},
                  f, ensure_ascii=False, indent=2)

def degisim(onceki, yeni):
    o, y = set(onceki), set(yeni)
    return {"girenler": list(y-o), "cikanlar": list(o-y), "kalanlar": list(o&y), "degisti": o!=y}

def telegram(mesaj):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"\n--- TELEGRAM PREVIEW ---\n{mesaj}\n---")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": mesaj, "parse_mode": "HTML"},
            timeout=15
        ).raise_for_status()
        print("✅ Telegram gönderildi")
    except Exception as e:
        print(f"❌ Telegram hatası: {e}")

def rapor(top, toplam, deg, onceki):
    bugun = datetime.now().strftime("%d.%m.%Y %H:%M")
    em = lambda s: "🟢" if s >= 70 else "🟡" if s >= 45 else "🔴"
    if not onceki: baslik = "🚀 <b>ALFA PORTFÖY — İLK ANALİZ</b>"
    elif deg["degisti"]: baslik = "🔔 <b>ALFA PORTFÖY — PORTFÖY DEĞİŞTİ!</b>"
    else: baslik = "📊 <b>ALFA PORTFÖY — GÜNLÜK RAPOR</b>"
    m = f"{baslik}\n📅 {bugun}\n{'─'*28}\n\n<b>⭐ TOP {TOP_N} HİSSE</b>\n"
    for i, h in enumerate(top, 1):
        yeni_isaret = " 🆕" if h["ticker"] in deg.get("girenler", []) else ""
        m += (f"\n{em(h['skor'])} <b>#{i} {h['ticker']}</b>{yeni_isaret}  [{h['skor']}/100]\n"
              f"   PD/DD:{h['pddd'] or '—'}  F/K:{h['fk'] or '—'}  ÖZS:%{h['ozs'] or '—'}\n"
              f"   Sektör: {h['sektor']}\n")
    if deg["degisti"] and onceki:
        m += f"\n{'─'*28}\n"
        if deg["girenler"]: m += f"✅ Giren: {', '.join(deg['girenler'])}\n"
        if deg["cikanlar"]: m += f"❌ Çıkan: {', '.join(deg['cikanlar'])}\n"
    elif onceki:
        m += f"\n✅ Değişiklik yok.\n"
    m += f"\n{'─'*28}\n📈 {toplam} hisse tarandı\n⚠️ <i>Yatırım tavsiyesi değildir.</i>"
    return m

def main():
    print("=" * 50)
    print("  ALFA PORTFÖY v4 — Düzeltilmiş")
    print(f"  {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
    print("=" * 50)
    
    onceki = onceki_yukle()
    
    # Hisse listesi çek
    kodlar = bist_listesi_cek()
    if len(kodlar) < 50:
        print("⚠️  Yeterli hisse bulunamadı, yedek liste kullanılıyor...")
        kodlar = yedek_bist_listesi()
    
    print(f"📋 {len(kodlar)} hisse taranacak")
    
    # Yahoo Finance'den veri çek
    hisseler = yahoo_veri_cek(kodlar)
    
    if len(hisseler) < 5:
        msg = f"❌ ALFA Hata: Sadece {len(hisseler)} hisse verisi alınabildi."
        print(msg)
        telegram(msg)
        return
    
    # Skor hesapla
    for h in hisseler:
        h["skor"] = skor(h)
    
    # Sıra göre düzenle
    sirali = sorted(hisseler, key=lambda x: x["skor"], reverse=True)
    top = sirali[:TOP_N]
    
    print(f"\n🏆 TOP {TOP_N}:")
    for i, h in enumerate(top, 1):
        print(f"  #{i} {h['ticker']} — Skor:{h['skor']}/100 PDDD:{h['pddd']} FK:{h['fk']}")
    
    # Portföy değişimini algıla
    yeni_portfoy = [h["ticker"] for h in top]
    deg = degisim(onceki, yeni_portfoy)
    
    # Kaydet
    kaydet(yeni_portfoy, top)
    
    # Telegram gönder (hafta içi)
    if datetime.now().weekday() < 5:
        telegram(rapor(top, len(hisseler), deg, onceki))
    
    print("\n✅ Tamamlandı!")

if __name__ == "__main__":
    main()
