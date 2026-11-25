"""Playwright ile bekleyen takip isteklerini geri çeken bot."""
import json
import os
import platform
import random
import re
import shutil
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

DURUM = Path("durum.json")  # işlenen profiller burada saklanır (kaldığı yerden devam için)

# Türkçe İ/i uyumsuzluklarına karşı esnek regex desenleri
BEKLEYEN = re.compile(r"(Requested|[İiI]stek\s+[Gg]önderildi)", re.I)
ONAY = ONAY = re.compile(r"^(Unfollow|Takibi\s+[Bb]ırak)$", re.I)
TAKIP = re.compile(r"^(Following|Takiptesin|Takip\s+Ediliyor|Follow|Takip\s+Et|Follow\s+Back|Sen\s+de\s+Takip\s+Et)$", re.I)
YOK = ("isn't available", "ulaşılamıyor", "Page Not Found", "Sayfa bulunamadı")

# Hız modları: bekleme aralıkları (sn). "Güvenli" mevcut varsayılan değerlerle birebir aynıdır.
# sayfa: sayfa açıldıktan sonra | hover: tıklamadan önce | tik/tik2: tıklama sonrası | arasi: profiller arası
# mola_her: kaç işlemde bir uzun mola | mola: uzun mola süresi (sn) | gorsel_engel: resim/video/font yüklemeyi kapat
HIZ = {
    "Güvenli": dict(sayfa=(2.0, 4.0), hover=(0.4, 0.8), tik=(1.0, 2.0), tik2=(1.5, 2.5), arasi=(4, 9),
                    mola_her=(20, 25), mola=(120, 180), gorsel_engel=False,
                    bilgi="≈12-20 sn/profil · 20-25 işlemde 2-3 dk mola"),
    "Dengeli": dict(sayfa=(1.2, 2.5), hover=(0.3, 0.6), tik=(0.7, 1.4), tik2=(0.9, 1.7), arasi=(3, 6),
                    mola_her=(25, 30), mola=(90, 150), gorsel_engel=True,
                    bilgi="≈8-13 sn/profil · 25-30 işlemde 1,5-2,5 dk mola"),
    "Hızlı": dict(sayfa=(0.8, 1.6), hover=(0.2, 0.4), tik=(0.4, 0.9), tik2=(0.6, 1.2), arasi=(2, 4),
                  mola_her=(30, 35), mola=(60, 100), gorsel_engel=True,
                  bilgi="≈5-9 sn/profil · 30-35 işlemde 1-1,7 dk mola · kısıtlama riski daha yüksek"),
}

CDP_PORT = 9222
# Yalnızca CDP destekleyen Chromium tabanlı tarayıcılar
ADAYLAR = {
    "chrome": ["chrome.exe", "google-chrome", "google-chrome-stable", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
    "brave": ["brave.exe", "brave-browser", "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"],
    "edge": ["msedge.exe", "microsoft-edge", "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"],
}
WIN_DIZINLER = [os.environ.get(k, "") for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
WIN_ALT = {
    "chrome.exe": r"Google\Chrome\Application\chrome.exe",
    "msedge.exe": r"Microsoft\Edge\Application\msedge.exe",
    "brave.exe": r"BraveSoftware\Brave-Browser\Application\brave.exe",
}


def varsayilan_tarayici():
    """İşletim sisteminin varsayılan web tarayıcısını tahmin eder."""
    try:
        sis = platform.system()
        if sis == "Windows":
            import winreg
            k = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice",
            )
            prog = winreg.QueryValueEx(k, "ProgId")[0].lower()
        elif sis == "Linux":
            prog = subprocess.run(
                ["xdg-settings", "get", "default-web-browser"],
                capture_output=True, text=True
            ).stdout.lower()
        else:
            prog = ""
        for ad, anahtar in (("brave", "brave"), ("edge", "edge"), ("msedge", "edge"), ("chrome", "chrome"), ("opera", "opera"), ("firefox", "firefox")):
            if ad in prog:
                return anahtar
    except Exception:
        pass
    return "diger"


def exe_bul(ad):
    for aday in ADAYLAR[ad]:
        if os.path.isabs(aday) and os.path.exists(aday):
            return aday
        if aday in WIN_ALT:
            for d in WIN_DIZINLER:
                yol = os.path.join(d, WIN_ALT[aday])
                if d and os.path.exists(yol):
                    return yol
        w = shutil.which(aday)
        if w:
            return w
    return None


def tarayici_sec(log):
    """Varsayılan tarayıcıyı seçer; Chromium tabanlı değilse kurulu ilk uygun tarayıcıya düşer."""
    vt = varsayilan_tarayici()
    sira = ([vt] if vt in ADAYLAR else []) + [a for a in ADAYLAR if a != vt]
    for ad in sira:
        exe = exe_bul(ad)
        if exe:
            if ad != vt:
                log(f"ℹ Varsayılan tarayıcı ({vt}) otomasyona uygun değil; {ad} kullanılıyor.")
            return exe
    return None


def durum_oku():
    try:
        return json.loads(DURUM.read_text(encoding="utf-8"))
    except Exception:
        return {}


def durum_yaz(d):
    DURUM.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


class Bot:
    def __init__(self, log, ilerleme, bitti):
        self.log, self.ilerleme, self.bitti = log, ilerleme, bitti
        self.baslat_ev, self.durdur_ev = threading.Event(), threading.Event()
        self.devam_ev = threading.Event()
        self.devam_ev.set()  # set = çalışıyor, clear = duraklatıldı
        self.kullanicilar, self.limit, self.page = [], 100, None
        self.hiz = HIZ["Güvenli"]  # seçili hız modu
        self.thread = None

    # ---- Dışarıdan kontrol ----
    def tarayici_ac(self):
        if self.thread and self.thread.is_alive():
            return self.log("Tarayıcı zaten açık.")
        self.baslat_ev.clear()
        self.durdur_ev.clear()
        self.devam_ev.set()
        self.thread = threading.Thread(target=self._calis, daemon=True)
        self.thread.start()

    def baslat(self, kullanicilar, limit):
        self.kullanicilar, self.limit = kullanicilar, limit
        self.baslat_ev.set()

    def hiz_ayarla(self, ad):
        """Hız modunu değiştirir; bekleme süreleri her adımda self.hiz'den okunduğu için çalışırken de geçerlidir."""
        self.hiz = HIZ.get(ad, HIZ["Güvenli"])
        self.log(f"⚙ Hız modu: {ad}")

    def duraklat_degistir(self):
        if self.devam_ev.is_set():
            self.devam_ev.clear()
            self.log("⏸ Duraklatıldı.")
        else:
            self.devam_ev.set()
            self.log("▶ Devam ediliyor.")

    def durdur(self):
        self.durdur_ev.set()
        self.devam_ev.set()

    # ---- Dahili ----
    def _bekle(self, sn):
        """Durdurma/duraklatmaya duyarlı bekleme (Playwright iş parçacığında çalışır)."""
        bitis = sn
        while bitis > 0 and not self.durdur_ev.is_set():
            self.devam_ev.wait()
            adim = min(0.5, bitis)
            self.page.wait_for_timeout(int(adim * 1000))
            bitis -= adim

    def _insansi(self, a=2.5, b=5.5):
        self._bekle(random.uniform(a, b))

    def _t(self, anahtar):
        """Seçili hız modundaki aralıkta rastgele bekle."""
        self._insansi(*self.hiz[anahtar])

    def _engelle(self, route):
        """Resim, video ve fontları yüklemeyerek sayfa açılışını hızlandırır."""
        if route.request.resource_type in ("image", "media", "font"):
            route.abort()
        else:
            route.continue_()

    def _calis(self):
        try:
            with sync_playwright() as p:
                exe = tarayici_sec(self.log)
                if exe:
                    subprocess.Popen([
                        exe,
                        f"--remote-debugging-port={CDP_PORT}",
                        f"--user-data-dir={Path('tarayici_profili').resolve()}",
                        "--no-first-run",
                        "https://www.instagram.com/accounts/login/",
                    ])
                    for _ in range(40):
                        try:
                            urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=1)
                            break
                        except Exception:
                            time.sleep(0.5)
                    br = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
                    ctx = br.contexts[0]
                else:
                    self.log("⚠ Chrome/Edge/Brave bulunamadı, Playwright Chromium kullanılıyor.")
                    ctx = p.chromium.launch_persistent_context("tarayici_profili", headless=False)
                    if ctx.pages:
                        ctx.pages[0].goto("https://www.instagram.com/accounts/login/")

                self.page = (
                    next((pg for pg in ctx.pages if "instagram" in pg.url), None)
                    or (ctx.pages[0] if ctx.pages else ctx.new_page())
                )
                self.log("Tarayıcı açıldı. Instagram'a kendiniz giriş yapın (şifre bu uygulamaya girilmez, 2FA dahil).")
                self.log("Giriş bitince 'İşlemi Başlat'a basın.")

                # 30000ms yerine 300ms: 'İşlemi Başlat'a basıldığında anında tepki verir
                while not self.baslat_ev.is_set() and not self.durdur_ev.is_set():
                    self.page.wait_for_timeout(300)

                if not self.durdur_ev.is_set():
                    self._isle()
                if not exe:
                    ctx.close()
        except Exception as e:
            self.log(f"❌ Kritik hata: {e}")
        finally:
            self.bitti()

    def _isle(self):
        durum = durum_oku()
        liste = [u for u in self.kullanicilar if u not in durum]
        self.log(f"{len(self.kullanicilar) - len(liste)} profil atlandı (önceden işlenmiş). Kalan: {len(liste)}")
        islem, mola_siniri = 0, random.randint(*self.hiz["mola_her"])
        toplam = min(len(liste), self.limit)

        # Görsel engelleme yalnızca işlem sırasında açık (giriş/2FA ekranları etkilenmez)
        engelli = self.hiz["gorsel_engel"]
        if engelli:
            self.page.route("**/*", self._engelle)

        for u in liste:
            if self.durdur_ev.is_set() or islem >= self.limit:
                break
            self.devam_ev.wait()
            sonuc = self._profil(u)
            if sonuc:
                durum[u] = sonuc
                durum_yaz(durum)
            islem += 1
            self.ilerleme(islem / max(toplam, 1))

            if islem >= mola_siniri and islem < toplam:
                s = random.randint(*self.hiz["mola"])
                self.log(f"☕ Uzun mola: {s} sn")
                for k in range(s, 0, -10):
                    if self.durdur_ev.is_set():
                        break
                    self.log(f"   mola bitimine {k} sn...")
                    self._bekle(min(10, k))
                mola_siniri += random.randint(*self.hiz["mola_her"])
            else:
                self._t("arasi")

        if engelli:
            try:
                self.page.unroute("**/*", self._engelle)
            except Exception:
                pass
        self.log(f"Bitti. Bu oturumda {islem} profil işlendi.")

    def _profil(self, u):
        try:
            self.log(f"→ {u}")
            self.page.goto(f"https://www.instagram.com/{u}/", wait_until="domcontentloaded", timeout=30000)

            # Profil içeriğinin (header veya hata yazısının) ekrana gelmesini bekle
            try:
                self.page.locator("header, main").first.wait_for(state="visible", timeout=10000)
            except Exception:
                pass
            self._t("sayfa")

            govde = self.page.inner_text("body")
            if any(k in govde for k in YOK):
                self.log("   profil bulunamadı/silinmiş")
                return "bulunamadi"

            # Hem <button> hem <div role="button"> öğelerini tara
            butonlar = self.page.locator("header button, header div[role='button']")
            bekleyen_btn = butonlar.filter(has_text=BEKLEYEN).first

            if bekleyen_btn.count() and bekleyen_btn.is_visible():
                self.page.bring_to_front()
                bekleyen_btn.scroll_into_view_if_needed()
                bekleyen_btn.hover()
                self._t("hover")
                bekleyen_btn.click()
                self._t("tik")

                # Onay penceresindeki "Takibi Bırak" / "Unfollow" butonunu bekle (button, div veya doğrudan metin)
                onay_btn = self.page.locator("button, div[role='button']").filter(has_text=ONAY).first
                if not onay_btn.count():
                    onay_btn = self.page.get_by_text(ONAY).first

                try:
                    onay_btn.wait_for(state="visible", timeout=6000)
                    onay_btn.click()
                    self._t("tik2")
                    self.log("   ✅ istek geri çekildi")
                    return "iptal"
                except Exception:
                    # İlk tıklama pencereyi açmadıysa içteki metne bir kez daha tıkla
                    bekleyen_btn.locator("div[dir='auto']").first.click()
                    self._t("tik")
                    onay_btn = self.page.get_by_text(ONAY).first
                    if onay_btn.count() and onay_btn.is_visible():
                        onay_btn.click()
                        self._t("tik2")
                        self.log("   ✅ istek geri çekildi")
                        return "iptal"

                    self.log("   ⚠ 'Takibi Bırak' onay butonuna ulaşılamadı, tekrar denenecek")
                    return None

            # Bekleyen istek yoksa Takip Et / Takiptesin durumunu kontrol et
            takip_btn = butonlar.filter(has_text=TAKIP).first
            if takip_btn.count() and takip_btn.is_visible():
                self.log("   istek yok (kabul edilmiş veya zaten iptal)")
                return "kabul_edilmis"

            self.log("   ⚠ buton bulunamadı, atlandı (tekrar denenecek)")
            return None
        except Exception as e:
            self.log(f"   ⚠ hata: {str(e)[:100]} — sonraki profile geçiliyor")
            return None