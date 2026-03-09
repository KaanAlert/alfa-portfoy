"""
ALFA Portföy Tarayıcı v3 - Final
Kaynak: İş Yatırım kamuya açık temel göstergeler
Rate limit yok, ücretsiz, güvenilir
"""

import json, os, time, re, requests
from datetime import datetime, date
from bs4 import BeautifulSoup

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TOP_N            = 10
PORTFOY_DOSYASI  = "onceki_portfoy.json"

FILTRELER = {
    "pddd_max": 2.0, "fk_max": 10.0, "fna_max": 6.0,
    "ozs_min": 15.0, "efk_min": 10.0, "nk_min": 5.0,
}

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Referer": "https://www.isyatirim.com.tr/",
})


# ── VERİ ÇEKME ─────────────────────────────────────────────

def temel_gostergeler_cek() -> list:
    """
    İş Yatırım temel göstergeler API'si.
    Tüm BIST hisselerinin F/K, PD/DD, FD/FAVÖK, ROE vb. verilerini döndürür.
    """
    print("📡 İş Yatırım temel göstergeler çekiliyor...")

    endpoints = [
        # Birincil endpoint
        "https://www.isyatirim.com.tr/api/Data/GetHisseSirketFinansalOzet",
        # Alternatif 1
        "https://www.isyatirim.com.tr/api/Data/GetTemelGostergeler",
        # Alternatif 2
        "https://www.isyatirim.com.tr/api/Data/GetHisseBilgileri",
    ]

    for url in endpoints:
        try:
            print(f"  Deneniyor: {url}")
            r = SESSION.get(url, timeout=30)
            print(f"  HTTP {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) > 10:
                    print(f"  ✅ {len(data)} kayıt alındı")
                    print(f"  Örnek alanlar: {list(data[0].keys())[:10] if data else []}")
                    return data
                elif isinstance(data, dict):
                    # İç içe yapı olabilir
                    for key in ["data", "Data", "result", "Result", "items", "Items"]:
                        if key in data and isinstance(data[key], list):
                            print(f"  ✅ {len(data[key])} kayıt alındı ({key})")
                            return data[key]
        except Exception as e:
            print(f"  ⚠️  {e}")
        time.sleep(1)

    return []


def isyatirim_analiz_sayfasi() -> list:
    """
    İş Yatırım hisse analiz sayfasından HTML parse ile veri çeker.
    Tüm temel göstergeleri içerir.
    """
    print("\n📡 İş Yatırım analiz sayfası çekiliyor...")

    url = "https://www.isyatirim.com.tr/tr-tr/analiz/hisse/Sayfalar/default.aspx"

    try:
        r = SESSION.get(url, timeout=30)
        print(f"  HTTP {r.status_code}")
        if r.status_code != 200:
            return []

        soup = BeautifulSoup(r.text, "html.parser")

        # Tablo ara
        tablolar = soup.find_all("table")
        print(f"  {len(tablolar)} tablo bulundu")

        for tablo in tablolar:
            satirlar = tablo.find_all("tr")
            if len(satirlar) > 20:  # Büyük tablo = hisse listesi
                sonuc = []
                basliklar = [th.get_text(strip=True) for th in satirlar[0].find_all(["th","td"])]
                print(f"  Başlıklar: {basliklar[:8]}")

                for satir in satirlar[1:]:
                    hucreler = [td.get_text(strip=True) for td in satir.find_all("td")]
                    if len(hucreler) >= 4:
                        veri = dict(zip(basliklar, hucreler))
                        sonuc.append(veri)

                if sonuc:
                    print(f"  ✅ {len(sonuc)} hisse HTML'den alındı")
                    return sonuc

    except Exception as e:
        print(f"  ⚠️  {e}")

    return []


def verileri_isle(ham_liste: list) -> list:
    """Ham veriyi ALFA formatına dönüştürür."""

    def safe_float(val):
        if val is None: return None
        try:
            return float(str(val).replace(",", ".").replace("%", "").replace(" ", "").strip())
        except:
            return None

    def temizle(val, min_v=None, max_v=None):
        v = safe_float(val)
        if v is None: return None
        if min_v is not None and v < min_v: return None
        if max_v is not None and v > max_v: return None
        return round(v, 2)

    # Olası alan adı varyasyonları
    ALANLAR = {
        "ticker": ["HisseKodu","hisseKodu","Kod","kod","Symbol","symbol","HISSE","Hisse"],
        "sektor":  ["Sektor","sektor","Sector","sector","SektorAdi"],
        "pddd":    ["PD_DD","pd_dd","PDDD","FiyatDegerOrani","PD/DD","F/DD","price_book"],
        "fk":      ["FK","fk","PE","pe","FiyatKazanc","F/K","TrailingPE"],
        "fna":     ["FD_FAVOK","fd_favok","FDFAVOK","FD/FAVÖK","EV_EBITDA"],
        "ozs":     ["OzkaynaKarlilik","ROE","roe","OZS","ÖZS","ReturnOnEquity"],
        "efk":     ["FAVOKMarji","EBITDAMargin","ebitda_margin","FAVÖK%","EFKMarji"],
        "nk":      ["NetKarMarji","ProfitMargin","profit_margin","NK%","NetMargin"],
    }

    def alan_al(veri, adaylar):
        for a in adaylar:
            if a in veri and veri[a] not in [None, "", "-", "—", "N/A"]:
                return veri[a]
        return None

    sonuc = []
    for veri in ham_liste:
        ticker = alan_al(veri, ALANLAR["ticker"])
        if not ticker or len(str(ticker)) < 2:
            continue

        ticker = str(ticker).strip().upper()

        h = {
            "ticker": ticker,
            "sektor": str(alan_al(veri, ALANLAR["sektor"]) or "Bilinmiyor"),
            "pddd": temizle(alan_al(veri, ALANLAR["pddd"]), 0.01, 100),
            "fk":   temizle(alan_al(veri, ALANLAR["fk"]),   0.1,  500),
            "fna":  temizle(alan_al(veri, ALANLAR["fna"]),  0.1,  100),
            "ozs":  temizle(alan_al(veri, ALANLAR["ozs"]),  -200, 500),
            "efk":  temizle(alan_al(veri, ALANLAR["efk"]),  -200, 500),
            "nk":   temizle(alan_al(veri, ALANLAR["nk"]),   -200, 500),
        }
        sonuc.append(h)

    return sonuc


# ── ALFA ALGORİTMASI ───────────────────────────────────────

def skor(s):
    p = 0
    if s["pddd"] and s["pddd"] <= 2.0:
        p += 30 if s["pddd"] <= 1.0 else 30 * (2.0 - s["pddd"])
    if s["fk"] and 0 < s["fk"] <= 10:
        p += 20 * (1 - s["fk"] / 10)
    if s["fna"] and 0 < s["fna"] <= 6:
        p += 15 * (1 - s["fna"] / 6)
    if s["ozs"] and s["ozs"] >= 15:
        p += min(20, 20 * (s["ozs"] - 15) / 85)
    if s["efk"] and s["efk"] >= 10:
        p += min(10, 10 * (s["efk"] - 10) / 90)
    if s["nk"] and s["nk"] >= 5:
        p += min(5, 5 * (s["nk"] - 5) / 95)
    return round(p)


def filtre(s):
    f = FILTRELER
    if not s["pddd"] or s["pddd"] > f["pddd_max"]: return False
    if s["fk"]  and (s["fk"]  <= 0 or s["fk"]  > f["fk_max"]):  return False
    if s["fna"] and (s["fna"] <= 0 or s["fna"] > f["fna_max"]): return False
    if not s["ozs"] or s["ozs"] < f["ozs_min"]: return False
    if not s["efk"] or s["efk"] < f["efk_min"]: return False
    if not s["nk"]  or s["nk"]  < f["nk_min"]:  return False
    return True


# ── PORTFÖY ────────────────────────────────────────────────

def onceki_yukle():
    try:
        with open(PORTFOY_DOSYASI, "r", encoding="utf-8") as f:
            return json.load(f).get("portfoy", [])
    except FileNotFoundError:
        return []


def kaydet(portfoy, detaylar):
    with open(PORTFOY_DOSYASI, "w", encoding="utf-8") as f:
        json.dump({"tarih": date.today().isoformat(),
                   "portfoy": portfoy, "detaylar": detaylar}, f,
                  ensure_ascii=False, indent=2)


def degisim(onceki, yeni):
    o, y = set(onceki), set(yeni)
    return {"girenler": list(y-o), "cikanlar": list(o-y),
            "kalanlar": list(o&y), "degisti": o != y}


# ── TELEGRAM ───────────────────────────────────────────────

def telegram(mesaj):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"\n--- PREVIEW ---\n{mesaj}\n---")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": mesaj, "parse_mode": "HTML"},
            timeout=15
        ).raise_for_status()
        print("✅ Telegram gönderildi")
    except Exception as e:
        print(f"❌ {e}")


def rapor(top, passing, deg, onceki):
    bugun = datetime.now().strftime("%d.%m.%Y %H:%M")
    em = lambda s: "🟢" if s >= 70 else "🟡" if s >= 45 else "🔴"

    if not onceki:       b = "🚀 <b>ALFA PORTFÖY — İLK ANALİZ</b>"
    elif deg["degisti"]: b = "🔔 <b>ALFA PORTFÖY — PORTFÖY DEĞİŞTİ!</b>"
    else:                b = "📊 <b>ALFA PORTFÖY — GÜNLÜK RAPOR</b>"

    m = f"{b}\n📅 {bugun}\n{'─'*28}\n\n<b>⭐ TOP {TOP_N}</b>\n"
    for i, h in enumerate(top, 1):
        yeni = " 🆕" if h["ticker"] in deg.get("girenler", []) else ""
        m += (f"\n{em(h['skor'])} <b>#{i} {h['ticker']}</b>{yeni}  "
              f"[{h['skor']}/100]\n"
              f"   PD/DD:{h['pddd'] or '—'}  F/K:{h['fk'] or '—'}  "
              f"ÖZS:%{h['ozs'] or '—'}\n")

    if deg["degisti"] and onceki:
        m += f"\n{'─'*28}\n"
        if deg["girenler"]: m += f"✅ Giren: {', '.join(deg['girenler'])}\n"
        if deg["cikanlar"]: m += f"❌ Çıkan: {', '.join(deg['cikanlar'])}\n"
    elif onceki:
        m += f"\n✅ Değişiklik yok.\n"

    m += f"\n{'─'*28}\n📈 {len(passing)} hisse geçti\n⚠️ <i>Yatırım tavsiyesi değildir.</i>"
    return m


# ── MAIN ───────────────────────────────────────────────────

def main():
    print("=" * 50)
    print("  ALFA PORTFÖY v3 — İş Yatırım")
    print(f"  {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
    print("=" * 50)

    onceki = onceki_yukle()

    # Veri çek — iki yöntem dene
    ham = temel_gostergeler_cek()

    if not ham or len(ham) < 5:
        print("\n⚠️  API boş, HTML yöntemi deneniyor...")
        ham = isyatirim_analiz_sayfasi()

    if not ham or len(ham) < 5:
        msg = "❌ ALFA Hata: İş Yatırım'dan veri alınamadı. Endpoint güncellenmesi gerekebilir."
        print(f"\n{msg}")
        telegram(msg)
        return

    # İşle
    hisseler = verileri_isle(ham)
    print(f"\n✅ {len(hisseler)} hisse işlendi")

    if len(hisseler) < 5:
        telegram(f"❌ ALFA: Sadece {len(hisseler)} hisse parse edilebildi.")
        return

    # Analiz
    for h in hisseler:
        h["skor"]  = skor(h)
        h["gecti"] = filtre(h)

    passing = sorted([h for h in hisseler if h["pddd"] and h["pddd"] > 0],
                 key=lambda x: x["skor"], reverse=True)
top = passing[:TOP_N]

    print(f"📊 Filtreden geçen: {len(passing)}")
    print(f"🏆 Top {TOP_N}: {[h['ticker'] for h in top]}")

    if not top:
        telegram("⚠️ ALFA: Bugün filtre şartını karşılayan hisse bulunamadı.")
        return

    yeni_portfoy = [h["ticker"] for h in top]
    deg = degisim(onceki, yeni_portfoy)
    kaydet(yeni_portfoy, top)

    if datetime.now().weekday() < 5:
        telegram(rapor(top, passing, deg, onceki))

    print("\n✅ Tamamlandı!")


if __name__ == "__main__":
    main()
