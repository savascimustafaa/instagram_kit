"""Instagram veri dosyalarını (HTML/JSON) okuyan ve analiz eden modül."""
import json
import re
from pathlib import Path
from bs4 import BeautifulSoup

IG_RE = re.compile(r"instagram\.com/(?:_u/)?([A-Za-z0-9._]+)/?(?:\?|$)")


def _bul(klasor, desen):
    """Klasörde (alt klasörler dahil) desene uyan dosyaları sıralı döndürür."""
    return sorted(Path(klasor).rglob(desen))


HAM_RE = re.compile(r"instagram\.com/(?:_u/)?([A-Za-z0-9._]{1,30})(?=[/?\"'\s<>#]|$)")
ETIKETLER = {"kullanıcı adı", "kullanici adi", "username", "user name"}
GECERLI = re.compile(r"^[A-Za-z0-9._]{1,30}$")
YASAK = {"accounts", "explore", "p", "reel", "reels", "stories", "direct", "about", "legal", "web"}


def _html_oku(yol):
    ham = Path(yol).read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(ham, "html.parser")
    kullanicilar = []
    for a in soup.find_all("a", href=True):
        m = IG_RE.search(a["href"])
        if m and m.group(1) not in YASAK:
            kullanicilar.append(m.group(1))
    if not kullanicilar:
        # Link yoksa: "Kullanıcı adı" / "Username" etiketinden sonra gelen metin kullanıcı adıdır
        satirlar = [s.strip() for s in soup.get_text("\n", strip=True).split("\n") if s.strip()]
        for i, s in enumerate(satirlar[:-1]):
            if s.lower().rstrip(":") in ETIKETLER and GECERLI.match(satirlar[i + 1]):
                kullanicilar.append(satirlar[i + 1])
    if not kullanicilar:
        # Yedek yöntem: link yapısı farklıysa ham metindeki tüm instagram.com/... adreslerini tara
        kullanicilar = [u for u in HAM_RE.findall(ham.replace("\\/", "/")) if u not in YASAK]
    return kullanicilar


def _json_oku(yol):
    """JSON yapısı sürümlere göre değiştiği için tüm ağacı gezip string_list_data'yı toplar."""
    veri = json.loads(Path(yol).read_text(encoding="utf-8", errors="ignore"))
    sonuc = []

    def gez(o):
        if isinstance(o, dict):
            if "string_list_data" in o:
                for it in o["string_list_data"]:
                    ad = it.get("value")
                    if not ad and it.get("href"):
                        m = IG_RE.search(it["href"])
                        ad = m.group(1) if m else None
                    ad = ad or o.get("title")
                    if ad:
                        sonuc.append(ad)
            else:
                for v in o.values():
                    gez(v)
        elif isinstance(o, list):
            for v in o:
                gez(v)

    gez(veri)
    if not sonuc:
        ham = Path(yol).read_text(encoding="utf-8", errors="ignore").replace("\\/", "/")
        sonuc = [u for u in HAM_RE.findall(ham) if u not in YASAK]
    return sonuc


def _oku(yol):
    return _json_oku(yol) if str(yol).lower().endswith(".json") else _html_oku(yol)


def _tekil(liste):
    """Sırayı koruyarak tekrarları temizler."""
    return list(dict.fromkeys(u.lower() for u in liste))


def _dosyalar(kaynak, onek):
    """Kaynak klasör ya da tek dosya olabilir; followers_1, followers_2... hepsini birleştirir."""
    p = Path(kaynak)
    if p.is_file():
        return [p]
    return _bul(p, f"{onek}*.html") + _bul(p, f"{onek}*.json")


def analiz_et(klasor):
    """(geri_takip_etmeyenler, hayranlar, takipci_sayisi, takip_sayisi) döndürür."""
    takipci_d = _dosyalar(klasor, "followers")
    takip_d = _dosyalar(klasor, "following")
    if not takipci_d or not takip_d:
        raise FileNotFoundError("followers_*.html/json veya following.html/json bulunamadı.")
    takipci, takip = [], []
    for d in takipci_d:
        takipci += _oku(d)
    for d in takip_d:
        takip += _oku(d)
    takipci, takip = _tekil(takipci), _tekil(takip)
    ts, ks = set(takipci), set(takip)
    return [u for u in takip if u not in ts], [u for u in takipci if u not in ks], len(takipci), len(takip)


def bekleyen_istekler(kaynak):
    """pending_follow_requests.html/json içindeki kullanıcı adlarını döndürür."""
    dosyalar = _dosyalar(kaynak, "pending_follow_requests")
    if not dosyalar:
        raise FileNotFoundError("pending_follow_requests.html/json bulunamadı.")
    sonuc = []
    for d in dosyalar:
        sonuc += _oku(d)
    return _tekil(sonuc)


def bulunan_dosyalar(klasor, onek):
    """Arayüzde göstermek için bulunan dosyaların adlarını döndürür."""
    return [str(d.name) for d in _dosyalar(klasor, onek)]
