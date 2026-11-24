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
BEKLEYEN = re.compile(r"^(Requested|İstek Gönderildi)$", re.I)
ONAY = re.compile(r"^(Unfollow|Takibi Bırak)$", re.I)
TAKIP = re.compile(r"^(Following|Takip Ediliyor|Follow|Takip Et|Follow Back|Sen de Takip Et)$", re.I)
YOK = ("isn't available", "ulaşılamıyor", "Page Not Found", "Sayfa bulunamadı")


CDP_PORT = 9222
# Playwright yalnızca Chromium tabanlı tarayıcıları (Chrome, Edge, Brave) uzaktan yönetebilir.
ADAYLAR = {
    "chrome": ["chrome.exe", "google-chrome", "google-chrome-stable", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
    "opera": ["opera.exe", "opera", "/Applications/Opera.app/Contents/MacOS/Opera"],
    "brave": ["brave.exe", "brave-browser", "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"],
    "edge": ["msedge.exe", "microsoft-edge", "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"],
    "firefox": ["firefox.exe", "firefox", "/Applications/Firefox.app/Contents/MacOS/firefox"]

}
WIN_DIZINLER = [os.environ.get(k, "") for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
WIN_ALT = {"chrome.exe": r"Google\Chrome\Application\chrome.exe", "msedge.exe": r"Microsoft\Edge\Application\msedge.exe",
           "brave.exe": r"BraveSoftware\Brave-Browser\Application\brave.exe"}


def varsayilan_tarayici():
    """İşletim sisteminin varsayılan web tarayıcısını tahmin eder: chrome/opera/brave/firefox/diger."""
    try:
        sis = platform.system()
        if sis == "Windows":
            import winreg
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice")
            prog = winreg.QueryValueEx(k, "ProgId")[0].lower()
        elif sis == "Linux":
            prog = subprocess.run(["xdg-settings", "get", "default-web-browser"], capture_output=True, text=True).stdout.lower()
        else:
            prog = ""
        for ad, anahtar in (("opera", "opera"), ("brave", "brave"), ("edge", "edge"), ("chrome", "chrome"),
                            ("firefox", "firefox"), ("msedge", "edge")):
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
    """Varsayılan tarayıcıyı seçer; Chromium tabanlı değilse kurulu olan ilk uygun tarayıcıya düşer."""
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
        self.thread = None

    # ---- Dışarıdan kontrol ----
    def tarayici_ac(self):
        if self.thread and self.thread.is_alive():
            return self.log("Tarayıcı zaten açık.")
        self.baslat_ev.clear(); self.durdur_ev.clear(); self.devam_ev.set()
        self.thread = threading.Thread(target=self._calis, daemon=True)
        self.thread.start()

    def baslat(self, kullanicilar, limit):
        self.kullanicilar, self.limit = kullanicilar, limit
        self.baslat_ev.set()

    def duraklat_degistir(self):
        if self.devam_ev.is_set():
            self.devam_ev.clear(); self.log("⏸ Duraklatıldı.")
        else:
            self.devam_ev.set(); self.log("▶ Devam ediliyor.")

    def durdur(self):
        self.durdur_ev.set(); self.devam_ev.set()

    # ---- Dahili ----
    def _bekle(self, sn):
        """Durdurma/duraklatmaya duyarlı bekleme (Playwright iş parçacığında çalışır)."""
        bitis = sn
        while bitis > 0 and not self.durdur_ev.is_set():
            self.devam_ev.wait()
            adim = min(0.5, bitis)
            self.page.wait_for_timeout(int(adim * 1000))
            bitis -= adim

    def _insansi(self, a=2.5, b=6.0):
        self._bekle(random.uniform(a, b))

    def _calis(self):
        # Playwright sync API aynı iş parçacığında kullanılmalı; tüm tarayıcı işi burada.
        try:
            with sync_playwright() as p:
                exe = tarayici_sec(self.log)
                proc = None
                if exe:
                    # Kullanıcının kendi tarayıcısını uzaktan hata ayıklama portuyla, ayrı profil klasöründe açıyoruz.
                    proc = subprocess.Popen([exe, f"--remote-debugging-port={CDP_PORT}",
                        f"--user-data-dir={Path('tarayici_profili').resolve()}", "--no-first-run",
                        "https://www.instagram.com/accounts/login/"])
                    for _ in range(40):  # tarayıcının portu açmasını bekle (en çok ~20 sn)
                        try:
                            urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=1); break
                        except Exception:
                            time.sleep(0.5)
                    br = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
                    ctx = br.contexts[0]
                else:
                    self.log("⚠ Chrome/Edge/Brave bulunamadı, Playwright Chromium kullanılıyor.")
                    ctx = p.chromium.launch_persistent_context("tarayici_profili", headless=False)
                    ctx.pages[0].goto("https://www.instagram.com/accounts/login/") if ctx.pages else None
                self.page = next((pg for pg in ctx.pages if "instagram" in pg.url), None) or (ctx.pages[0] if ctx.pages else ctx.new_page())
                self.log("Tarayıcı açıldı. Instagram'a kendiniz giriş yapın (şifre bu uygulamaya girilmez, 2FA dahil).")
                self.log("Giriş bitince 'İşlemi Başlat'a basın.")
                while not self.baslat_ev.is_set() and not self.durdur_ev.is_set():
                    self.page.wait_for_timeout(500)
                if not self.durdur_ev.is_set():
                    self._isle()
                # Kullanıcının tarayıcısını kapatmıyoruz, sadece bağlantıyı bırakıyoruz.
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
        islem, mola_siniri = 0, random.randint(20, 25)
        toplam = min(len(liste), self.limit)
        for u in liste:
            if self.durdur_ev.is_set() or islem >= self.limit:
                break
            self.devam_ev.wait()
            sonuc = self._profil(u)
            if sonuc:  # None = geçici hata, kaydetme (sonra tekrar denenir)
                durum[u] = sonuc
                durum_yaz(durum)  # her işlemden hemen sonra kaydet
            islem += 1
            self.ilerleme(islem / max(toplam, 1))
            if islem >= mola_siniri and islem < toplam:
                s = random.randint(120, 180)
                self.log(f"☕ Uzun mola: {s} sn")
                for k in range(s, 0, -10):
                    if self.durdur_ev.is_set():
                        break
                    self.log(f"   mola bitimine {k} sn...")
                    self._bekle(min(10, k))
                mola_siniri += random.randint(20, 25)
            else:
                self._insansi(4, 9)
        self.log(f"Bitti. Bu oturumda {islem} profil işlendi.")

    def _profil(self, u):
        try:
            self.log(f"→ {u}")
            self.page.goto(f"https://www.instagram.com/{u}/", wait_until="domcontentloaded", timeout=30000)
            self._insansi()
            govde = self.page.inner_text("body")
            if any(k in govde for k in YOK):
                self.log("   profil bulunamadı/silinmiş"); return "bulunamadi"
            btn = self.page.get_by_role("button", name=BEKLEYEN).first
            if btn.count():
                btn.click(); self._insansi(1.5, 3.5)
                onay = self.page.get_by_role("button", name=ONAY).first
                onay.wait_for(timeout=5000)
                onay.click(); self._insansi(1.5, 3.5)
                self.log("   ✅ istek geri çekildi"); return "iptal"
            if self.page.get_by_role("button", name=TAKIP).first.count():
                self.log("   istek yok (kabul edilmiş veya zaten iptal)"); return "kabul_edilmis"
            self.log("   ⚠ buton bulunamadı, atlandı (tekrar denenecek)"); return None
        except Exception as e:
            self.log(f"   ⚠ hata: {str(e)[:80]} — sonraki profile geçiliyor"); return None
