"""CustomTkinter arayüzü — modern (gradyan + cam efekti) sürüm."""
import csv
import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk
import parser as ig_parser
from bot import Bot, durum_oku

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ====================== RENK PALETİ (açık, koyu) ======================
ARKA   = ("#eef0fb", "#0a0b17")   # pencere arka planı
KART   = ("#ffffff", "#12142a")   # ana kart
KART2  = ("#f3f4fd", "#1a1d3a")   # iç paneller (cam efekti)
KENAR  = ("#d9dcf2", "#2b2f5c")   # ince çerçeveler
YAZI   = ("#1b1d3a", "#eceeff")
YAZI2  = ("#5b6088", "#9aa0cf")
ACCENT = "#7c5cff"
ACCENT_HOVER = "#8f74ff"
LINK   = ("#3b5bdb", "#8ea8ff")

# Gradyan renk geçişleri
G_ANA     = ["#6366f1", "#8b5cf6", "#ec4899"]   # indigo → mor → pembe
G_MAVI    = ["#3b82f6", "#6366f1"]
G_YESIL   = ["#10b981", "#06b6d4"]
G_TURUNCU = ["#f59e0b", "#f97316"]
G_KIRMIZI = ["#f43f5e", "#e11d48"]
G_BASLIK  = ["#4f46e5", "#7c3aed", "#db2777"]


def tr(t):
    """(açık, koyu) renk çiftinden aktif temaya uygun olanı seç."""
    return t[0] if ctk.get_appearance_mode() == "Light" else t[1]


# ====================== GRADYAN YARDIMCILARI ======================
def _hex(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _parlat(c, oran=0.18):
    r, g, b = _hex(c)
    return "#%02x%02x%02x" % tuple(int(v + (255 - v) * oran) for v in (r, g, b))


def gradyan(w, h, renkler):
    """Soldan sağa çok duraklı gradyan (RGB)."""
    w, h = max(int(w), 2), max(int(h), 1)
    dur = [_hex(c) for c in renkler]
    cizgi = Image.new("RGB", (w, 1))
    for x in range(w):
        t = x / (w - 1) * (len(dur) - 1)
        i = min(int(t), len(dur) - 2)
        f = t - i
        cizgi.putpixel((x, 0), tuple(int(dur[i][k] + (dur[i + 1][k] - dur[i][k]) * f) for k in range(3)))
    return cizgi.resize((w, h))


def gradyan_yuvarlak(w, h, renkler, yaricap, olcek=2, parlak=True):
    """Köşeleri yuvarlatılmış, üstte hafif cam parlaması olan gradyan görseli (RGBA)."""
    W, H = int(w * olcek), int(h * olcek)
    img = gradyan(W, H, renkler).convert("RGBA")
    if parlak:
        gloss = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(gloss).rectangle((0, 0, W, H // 2), fill=(255, 255, 255, 30))
        img = Image.alpha_composite(img, gloss)
    maske = Image.new("L", (W, H), 0)
    ImageDraw.Draw(maske).rounded_rectangle((0, 0, W - 1, H - 1), radius=yaricap * olcek, fill=255)
    img.putalpha(maske)
    if olcek != 1:
        img = img.resize((int(w), int(h)), Image.LANCZOS)
    return img


class GradButton(tk.Canvas):
    """Gradyan arka planlı, üzerine gelince parlayan buton (Canvas tabanlı)."""
    hepsi = []

    def __init__(self, master, text, command, renkler, width=120, height=36, radius=12, zemin=KART2):
        super().__init__(master, highlightthickness=0, bd=0, cursor="hand2")
        olcek = self.winfo_fpixels("1i") / 96  # yüksek DPI ekranlarda boyutu orantıla
        W, H = int(width * olcek), int(height * olcek)
        self.configure(width=W, height=H)
        self.zemin, self.command = zemin, command
        self._n = ImageTk.PhotoImage(gradyan_yuvarlak(W, H, renkler, int(radius * olcek)))
        self._h = ImageTk.PhotoImage(gradyan_yuvarlak(W, H, [_parlat(c) for c in renkler], int(radius * olcek)))
        self._img = self.create_image(0, 0, image=self._n, anchor="nw")
        self.create_text(W // 2, H // 2, text=text, fill="white", font=("Segoe UI", 10, "bold"))
        self.bind("<Enter>", lambda e: self.itemconfigure(self._img, image=self._h))
        self.bind("<Leave>", lambda e: self.itemconfigure(self._img, image=self._n))
        self.bind("<ButtonRelease-1>", self._tikla)
        self.tema()
        GradButton.hepsi.append(self)

    def _tikla(self, e):
        if 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
            self.command()

    def tema(self):
        self.configure(bg=tr(self.zemin))


class Baslik(tk.Canvas):
    """Pencerenin üstündeki gradyan banner."""

    def __init__(self, master, baslik, alt, yukseklik=84):
        super().__init__(master, height=yukseklik, highlightthickness=0, bd=0)
        self.b, self.a, self.y = baslik, alt, yukseklik
        self._foto = None
        self.bind("<Configure>", self._ciz)

    def _ciz(self, e):
        self._foto = ImageTk.PhotoImage(gradyan(max(e.width, 10), self.y, G_BASLIK))
        self.delete("all")
        self.create_image(0, 0, image=self._foto, anchor="nw")
        self.create_text(28, 32, text=self.b, anchor="w", fill="white", font=("Segoe UI", 22, "bold"))
        self.create_text(28, 60, text=self.a, anchor="w", fill="#ece9ff", font=("Segoe UI", 11))


class GradBar(tk.Canvas):
    """Gradyan dolgulu, yuvarlak uçlu ilerleme çubuğu (CTkProgressBar yerine)."""

    def __init__(self, master, yukseklik=10):
        super().__init__(master, height=yukseklik, highlightthickness=0, bd=0)
        self.v, self.h, self._foto = 0.0, yukseklik, None
        self.bind("<Configure>", lambda e: self._ciz())
        self.tema()

    def tema(self):
        self.configure(bg=tr(KART))
        self._ciz()

    def set(self, v):
        self.v = max(0.0, min(1.0, float(v)))
        self._ciz()

    def _ciz(self):
        w = self.winfo_width()
        if w < 4:
            return
        self.delete("all")
        h = self.h
        self.create_line(h / 2, h / 2, w - h / 2, h / 2, width=h, capstyle="round", fill=tr(("#dfe2f5", "#23264a")))
        if self.v > 0:
            fw = max(int(w * self.v), h)
            self._foto = ImageTk.PhotoImage(gradyan_yuvarlak(fw, h, G_ANA, h // 2, olcek=1, parlak=False))
            self.create_image(0, 0, image=self._foto, anchor="nw")


# ====================== UYGULAMA ======================
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Instagram Araçları"); self.geometry("980x740"); self.minsize(880, 640)
        self.configure(fg_color=ARKA)
        self.q = queue.Queue()  # iş parçacıklarından arayüze güvenli mesaj kuyruğu
        self.sonuc = {"geri": [], "hayran": []}
        self.pending = []
        self.f_norm = ctk.CTkFont(family="Segoe UI", size=13)
        self.f_kalin = ctk.CTkFont(family="Segoe UI", size=14, weight="bold")
        self.f_mono = ctk.CTkFont(family="Consolas", size=12)
        self.bot = Bot(lambda m: self.q.put(("log", m)), lambda v: self.q.put(("prog", v)),
                       lambda: self.q.put(("bitti", None)))

        Baslik(self, "Instagram Araçları", "Takipçi analizi  •  Takip isteği iptal botu").pack(fill="x")

        # Üst çubuk: tema
        ust = ctk.CTkFrame(self, fg_color="transparent"); ust.pack(fill="x", padx=18, pady=(12, 0))
        ctk.CTkLabel(ust, text="Tema", text_color=YAZI2, font=self.f_norm).pack(side="left", padx=(0, 6))
        ctk.CTkOptionMenu(ust, values=["Dark", "Light"], width=92, corner_radius=10, font=self.f_norm,
                          fg_color=ACCENT, button_color=ACCENT_HOVER, button_hover_color=ACCENT_HOVER,
                          command=self._tema).pack(side="left")

        tabs = ctk.CTkTabview(self, fg_color=KART, corner_radius=22, border_width=1, border_color=KENAR,
                              segmented_button_fg_color=KART2, segmented_button_selected_color=ACCENT,
                              segmented_button_selected_hover_color=ACCENT_HOVER,
                              segmented_button_unselected_color=KART2,
                              segmented_button_unselected_hover_color=KENAR, text_color=YAZI)
        tabs.pack(fill="both", expand=True, padx=18, pady=14)
        self._tab1(tabs.add("Takipçi Analizi")); self._tab2(tabs.add("Takip İsteği İptal Botu"))
        self._link_renk()
        self.after(100, self._kuyruk)

    # ---------- Tema ----------
    def _tema(self, v):
        ctk.set_appearance_mode(v)
        self.bar.tema()
        self._link_renk()
        for b in GradButton.hepsi:
            if b.winfo_exists(): b.tema()

    def _link_renk(self):
        for box in [self.tb["geri"][0], self.tb["hayran"][0], self.pbox]:
            box._textbox.tag_config("u", foreground=tr(LINK), underline=True)

    # ---------- Ortak parçalar ----------
    def _kutu(self, parent, **kw):
        return ctk.CTkTextbox(parent, state="disabled", corner_radius=14, border_width=1, border_color=KENAR,
                              fg_color=KART2, text_color=YAZI, font=kw.pop("font", self.f_norm), **kw)

    def _panel(self, parent, **kw):
        return ctk.CTkFrame(parent, fg_color=KART2, corner_radius=14, border_width=1, border_color=KENAR, **kw)

    def _rozet(self, parent, text=""):
        return ctk.CTkLabel(parent, text=text, fg_color=KART2, corner_radius=12, text_color=YAZI,
                            font=self.f_norm, padx=14, pady=4)

    # ---------- Sekme 1 ----------
    def _tab1(self, t):
        f = self._panel(t); f.pack(fill="x", pady=(2, 0))
        self.yol1 = ctk.CTkLabel(f, text="Klasör seçilmedi", anchor="w", justify="left",
                                 text_color=YAZI2, font=self.f_norm)
        self.yol1.pack(side="left", padx=12, pady=8, expand=True, fill="x")
        GradButton(f, "Klasör Seç", self._sec1, G_MAVI, width=120).pack(side="right", padx=10, pady=8)
        self.bilgi1 = self._rozet(t); self.bilgi1.pack(pady=8)
        self.bilgi1.pack_forget()
        g = ctk.CTkFrame(t, fg_color="transparent"); g.pack(fill="both", expand=True)
        g.columnconfigure((0, 1), weight=1); g.rowconfigure(1, weight=1)
        self.tb = {}
        for i, (anahtar, baslik) in enumerate([("geri", "Geri Takip Yapmayanlar"), ("hayran", "Hayranlar")]):
            lbl = ctk.CTkLabel(g, text=baslik, font=self.f_kalin, text_color=YAZI); lbl.grid(row=0, column=i, pady=6)
            box = self._kutu(g); box.grid(row=1, column=i, sticky="nsew", padx=6)
            box._textbox.tag_config("u", foreground=tr(LINK), underline=True)
            box._textbox.tag_bind("u", "<Button-1>", lambda e, b=box: self._ac(e, b))
            GradButton(g, ".txt / .csv Olarak Dışa Aktar", lambda a=anahtar: self._disa(a),
                       G_ANA, width=240, zemin=KART).grid(row=2, column=i, pady=10)
            self.tb[anahtar] = (box, lbl, baslik)

    def _bilgi(self, text):
        """Bilgi rozetini göster/gizle."""
        if text:
            self.bilgi1.configure(text=text)
            if not self.bilgi1.winfo_ismapped():
                self.bilgi1.pack(pady=8, before=self.bilgi1.master.winfo_children()[-1])
        else:
            self.bilgi1.pack_forget()

    def _sec1(self):
        k = filedialog.askdirectory(title="Instagram veri klasörünü seçin")
        if not k: return
        bulunan = ig_parser.bulunan_dosyalar(k, "followers") + ig_parser.bulunan_dosyalar(k, "following")
        self.yol1.configure(text=f"{k}\nBulundu: {', '.join(bulunan) or 'hiçbir dosya yok'}")
        self._bilgi("Analiz ediliyor...")
        self._yukle2(k, sessiz=True)  # aynı klasörde bekleyen istek dosyası varsa otomatik yükle
        def is_():  # büyük dosyalar arayüzü dondurmasın diye ayrı iş parçacığı
            try:
                self.q.put(("analiz", ig_parser.analiz_et(k)))
            except Exception as e:
                self.q.put(("hata", str(e)))
        threading.Thread(target=is_, daemon=True).start()

    def _ac(self, e, box):
        tk_ = box._textbox
        satir = tk_.get(f"{tk_.index(f'@{e.x},{e.y}')} linestart", f"{tk_.index(f'@{e.x},{e.y}')} lineend").strip()
        if satir: webbrowser.open(f"https://www.instagram.com/{satir}/")

    def _doldur(self, anahtar, liste):
        box, lbl, baslik = self.tb[anahtar]
        lbl.configure(text=f"{baslik} ({len(liste)})")
        box.configure(state="normal"); box.delete("1.0", "end")
        for u in liste: box._textbox.insert("end", u + "\n", "u")
        box.configure(state="disabled")

    def _disa(self, anahtar):
        yol = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Metin", "*.txt"), ("CSV", "*.csv")])
        if not yol: return
        with open(yol, "w", encoding="utf-8", newline="") as f:
            if yol.endswith(".csv"):
                w = csv.writer(f); w.writerow(["kullanici_adi", "profil"])
                for u in self.sonuc[anahtar]: w.writerow([u, f"https://www.instagram.com/{u}/"])
            else:
                f.write("\n".join(self.sonuc[anahtar]))

    # ---------- Sekme 2 ----------
    def _tab2(self, t):
        f = self._panel(t); f.pack(fill="x", pady=(2, 0))
        self.yol2 = ctk.CTkLabel(f, text="Klasör/dosya seçilmedi", anchor="w", justify="left",
                                 text_color=YAZI2, font=self.f_norm)
        self.yol2.pack(side="left", padx=12, pady=8, expand=True, fill="x")
        GradButton(f, "Dosya Seç", lambda: self._sec2(False), G_MAVI, width=100).pack(side="right", padx=(4, 10), pady=8)
        GradButton(f, "Klasör Seç", lambda: self._sec2(True), G_MAVI, width=100).pack(side="right", padx=4, pady=8)
        self.sayi2 = self._rozet(t, "Bekleyen istek: -"); self.sayi2.pack(pady=8)
        orta = ctk.CTkFrame(t, fg_color="transparent"); orta.pack(fill="both", expand=True, pady=2)
        orta.columnconfigure((0, 1), weight=1); orta.rowconfigure(1, weight=1)
        self.lbl_pend = ctk.CTkLabel(orta, text="İsteğimi Kabul Etmeyenler (0)", font=self.f_kalin, text_color=YAZI)
        self.lbl_pend.grid(row=0, column=0, pady=4)
        ctk.CTkLabel(orta, text="İşlem Günlüğü", font=self.f_kalin, text_color=YAZI).grid(row=0, column=1, pady=4)
        self.pbox = self._kutu(orta); self.pbox.grid(row=1, column=0, sticky="nsew", padx=6)
        self.pbox._textbox.tag_config("u", foreground=tr(LINK), underline=True)
        self.pbox._textbox.tag_bind("u", "<Button-1>", lambda e: self._ac(e, self.pbox))
        self.log = self._kutu(orta, font=self.f_mono); self.log.grid(row=1, column=1, sticky="nsew", padx=6)

        k = self._panel(t); k.pack(fill="x", pady=(10, 4))
        ctk.CTkLabel(k, text="Oturum limiti", text_color=YAZI2, font=self.f_norm).pack(side="left", padx=(12, 6), pady=10)
        self.limit = ctk.CTkEntry(k, width=70, corner_radius=10, fg_color=KART, border_color=KENAR,
                                  text_color=YAZI, font=self.f_norm, justify="center")
        self.limit.insert(0, "100"); self.limit.pack(side="left")
        GradButton(k, "Tarayıcıyı Aç", self.bot.tarayici_ac, G_MAVI, width=130).pack(side="left", padx=(14, 6))
        GradButton(k, "İşlemi Başlat", self._baslat, G_YESIL, width=130).pack(side="left", padx=6)
        GradButton(k, "Duraklat / Devam", self.bot.duraklat_degistir, G_TURUNCU, width=150).pack(side="left", padx=6)
        GradButton(k, "Durdur", self.bot.durdur, G_KIRMIZI, width=100).pack(side="left", padx=6)
        self.bar = GradBar(t, 10); self.bar.pack(fill="x", padx=8, pady=(8, 4))

    def _sec2(self, klasor):
        y = filedialog.askdirectory() if klasor else filedialog.askopenfilename(filetypes=[("Veri", "*.html *.json")])
        if y: self._yukle2(y)

    def _yukle2(self, yol, sessiz=False):
        """Klasör içinde pending_follow_requests dosyasını kendisi bulur, listeyi gösterir (işlem başlamaz)."""
        try:
            self.pending = ig_parser.bekleyen_istekler(yol)
        except Exception as e:
            if not sessiz: messagebox.showerror("Hata", str(e))
            return
        if not self.pending:
            if not sessiz:
                messagebox.showwarning("Uyarı", "Dosya bulundu ama içinden hiç kullanıcı adı okunamadı. "
                    "Dosyanın gerçekten 'pending_follow_requests' olduğundan ve boş olmadığından emin olun.")
            return
        bulunan = ig_parser.bulunan_dosyalar(yol, "pending_follow_requests") if not yol.endswith((".html", ".json")) else [yol]
        self.yol2.configure(text=f"{yol}\nBulundu: {', '.join(bulunan)}")
        islenen = set(durum_oku())
        self.sayi2.configure(text=f"Bekleyen istek: {len(self.pending)}  |  Daha önce işlenen: {len([u for u in self.pending if u in islenen])}")
        self.lbl_pend.configure(text=f"İsteğimi Kabul Etmeyenler ({len(self.pending)})")
        self.pbox.configure(state="normal"); self.pbox.delete("1.0", "end")
        for u in self.pending: self.pbox._textbox.insert("end", u + "\n", "u")
        self.pbox.configure(state="disabled")
        self._yaz("Liste yüklendi. İptal için 'Tarayıcıyı Aç' > giriş yap > 'İşlemi Başlat'.")

    def _baslat(self):
        if not self.pending: return messagebox.showwarning("Uyarı", "Liste boş: bekleyen istek dosyası seçilmemiş ya da içinden kullanıcı okunamamış.")
        try: lim = int(self.limit.get())
        except ValueError: return messagebox.showwarning("Uyarı", "Limit sayı olmalı.")
        if not (self.bot.thread and self.bot.thread.is_alive()):
            return messagebox.showwarning("Uyarı", "Önce 'Tarayıcıyı Aç' ile giriş yapın.")
        self.bot.baslat(self.pending, lim)

    # ---------- Kuyruk (iş parçacığı -> arayüz) ----------
    def _yaz(self, m):
        self.log.configure(state="normal"); self.log.insert("end", m + "\n"); self.log.see("end"); self.log.configure(state="disabled")

    def _kuyruk(self):
        while not self.q.empty():
            tur, v = self.q.get()
            if tur == "log": self._yaz(v)
            elif tur == "prog": self.bar.set(v)
            elif tur == "bitti": self._yaz("— Tarayıcı oturumu sona erdi —")
            elif tur == "hata": self._bilgi(""); messagebox.showerror("Hata", v)
            elif tur == "analiz":
                geri, hayran, ts, ks = v
                self.sonuc = {"geri": geri, "hayran": hayran}
                self._doldur("geri", geri); self._doldur("hayran", hayran)
                self._bilgi(f"Takipçi: {ts}  |  Takip edilen: {ks}")
        self.after(100, self._kuyruk)