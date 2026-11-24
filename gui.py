"""CustomTkinter arayüzü."""
import csv
import queue
import threading
import webbrowser
from tkinter import filedialog, messagebox
import customtkinter as ctk
import parser as ig_parser
from bot import Bot, durum_oku

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Instagram Araçları"); self.geometry("900x680")
        self.q = queue.Queue()  # iş parçacıklarından arayüze güvenli mesaj kuyruğu
        self.sonuc = {"geri": [], "hayran": []}
        self.pending = []
        self.bot = Bot(lambda m: self.q.put(("log", m)), lambda v: self.q.put(("prog", v)),
                       lambda: self.q.put(("bitti", None)))
        ust = ctk.CTkFrame(self); ust.pack(fill="x", padx=10, pady=(10, 0))
        ctk.CTkLabel(ust, text="Tema:").pack(side="left", padx=8)
        ctk.CTkOptionMenu(ust, values=["Dark", "Light"], width=90,
                          command=lambda v: ctk.set_appearance_mode(v)).pack(side="left")
        tabs = ctk.CTkTabview(self); tabs.pack(fill="both", expand=True, padx=10, pady=10)
        self._tab1(tabs.add("Takipçi Analizi")); self._tab2(tabs.add("Takip İsteği İptal Botu"))
        self.after(100, self._kuyruk)

    # ---------- Sekme 1 ----------
    def _tab1(self, t):
        f = ctk.CTkFrame(t); f.pack(fill="x")
        self.yol1 = ctk.CTkLabel(f, text="Klasör seçilmedi", anchor="w"); self.yol1.pack(side="left", padx=8, expand=True, fill="x")
        ctk.CTkButton(f, text="Klasör Seç", command=self._sec1).pack(side="right", padx=4)
        self.bilgi1 = ctk.CTkLabel(t, text=""); self.bilgi1.pack(pady=4)
        g = ctk.CTkFrame(t); g.pack(fill="both", expand=True)
        g.columnconfigure((0, 1), weight=1); g.rowconfigure(1, weight=1)
        self.tb = {}
        for i, (anahtar, baslik) in enumerate([("geri", "Geri Takip Yapmayanlar"), ("hayran", "Hayranlar")]):
            lbl = ctk.CTkLabel(g, text=baslik); lbl.grid(row=0, column=i, pady=4)
            box = ctk.CTkTextbox(g, state="disabled"); box.grid(row=1, column=i, sticky="nsew", padx=4)
            box._textbox.tag_config("u", foreground="#4da3ff", underline=True)
            box._textbox.tag_bind("u", "<Button-1>", lambda e, b=box: self._ac(e, b))
            ctk.CTkButton(g, text=".txt / .csv Olarak Dışa Aktar",
                          command=lambda a=anahtar: self._disa(a)).grid(row=2, column=i, pady=6)
            self.tb[anahtar] = (box, lbl, baslik)

    def _sec1(self):
        k = filedialog.askdirectory(title="Instagram veri klasörünü seçin")
        if not k: return
        bulunan = ig_parser.bulunan_dosyalar(k, "followers") + ig_parser.bulunan_dosyalar(k, "following")
        self.yol1.configure(text=f"{k}\nBulundu: {', '.join(bulunan) or 'hiçbir dosya yok'}")
        self.bilgi1.configure(text="Analiz ediliyor...")
        self._yukle2(k, sessiz=True)  # aynı klasörde bekleyen istek dosyası varsa otomatik yükle
        def is_():  # büyük dosyalar arayüzü dondurmasın diye ayrı iş parçacığı
            try:
                self.q.put(("analiz", ig_parser.analiz_et(k)))
            except Exception as e:
                self.q.put(("hata", str(e)))
        threading.Thread(target=is_, daemon=True).start()

    def _ac(self, e, box):
        tk = box._textbox
        satir = tk.get(f"{tk.index(f'@{e.x},{e.y}')} linestart", f"{tk.index(f'@{e.x},{e.y}')} lineend").strip()
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
        f = ctk.CTkFrame(t); f.pack(fill="x")
        self.yol2 = ctk.CTkLabel(f, text="Klasör/dosya seçilmedi", anchor="w", justify="left"); self.yol2.pack(side="left", padx=8, expand=True, fill="x")
        ctk.CTkButton(f, text="Dosya Seç", width=90, command=lambda: self._sec2(False)).pack(side="right", padx=4)
        ctk.CTkButton(f, text="Klasör Seç", width=90, command=lambda: self._sec2(True)).pack(side="right", padx=4)
        self.sayi2 = ctk.CTkLabel(t, text="Bekleyen istek: -"); self.sayi2.pack(pady=4)
        orta = ctk.CTkFrame(t); orta.pack(fill="both", expand=True, pady=4)
        orta.columnconfigure((0, 1), weight=1); orta.rowconfigure(1, weight=1)
        self.lbl_pend = ctk.CTkLabel(orta, text="İsteğimi Kabul Etmeyenler (0)"); self.lbl_pend.grid(row=0, column=0)
        ctk.CTkLabel(orta, text="İşlem Günlüğü").grid(row=0, column=1)
        self.pbox = ctk.CTkTextbox(orta, state="disabled"); self.pbox.grid(row=1, column=0, sticky="nsew", padx=4)
        self.pbox._textbox.tag_config("u", foreground="#4da3ff", underline=True)
        self.pbox._textbox.tag_bind("u", "<Button-1>", lambda e: self._ac(e, self.pbox))
        self.log = ctk.CTkTextbox(orta, state="disabled"); self.log.grid(row=1, column=1, sticky="nsew", padx=4)
        k = ctk.CTkFrame(t); k.pack(fill="x", pady=4)
        ctk.CTkLabel(k, text="Oturum limiti:").pack(side="left", padx=6)
        self.limit = ctk.CTkEntry(k, width=70); self.limit.insert(0, "100"); self.limit.pack(side="left")
        ctk.CTkButton(k, text="Tarayıcıyı Aç", command=self.bot.tarayici_ac).pack(side="left", padx=6)
        ctk.CTkButton(k, text="İşlemi Başlat", fg_color="green", command=self._baslat).pack(side="left", padx=6)
        ctk.CTkButton(k, text="Duraklat / Devam", command=self.bot.duraklat_degistir).pack(side="left", padx=6)
        ctk.CTkButton(k, text="Durdur", fg_color="red", command=self.bot.durdur).pack(side="left", padx=6)
        self.bar = ctk.CTkProgressBar(t); self.bar.set(0); self.bar.pack(fill="x", padx=8, pady=6)

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
        self.sayi2.configure(text=f"Bekleyen istek: {len(self.pending)} | Daha önce işlenen: {len([u for u in self.pending if u in islenen])}")
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
            elif tur == "hata": self.bilgi1.configure(text=""); messagebox.showerror("Hata", v)
            elif tur == "analiz":
                geri, hayran, ts, ks = v
                self.sonuc = {"geri": geri, "hayran": hayran}
                self._doldur("geri", geri); self._doldur("hayran", hayran)
                self.bilgi1.configure(text=f"Takipçi: {ts} | Takip edilen: {ks}")
        self.after(100, self._kuyruk)
