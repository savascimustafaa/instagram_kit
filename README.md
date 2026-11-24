# Instagram Araçları

## Kurulum
    python -m venv venv
    venv\Scripts\activate 
    pip install -r requirements.txt
    

## Çalıştırma
    python main.py

## Kullanım
1. Instagram > Ayarlar > Hesap Merkezi > Bilgilerini indir (HTML veya JSON) ile verini al, zip'i aç.
2. Takipçi Analizi: klasörü seç; liste otomatik oluşur, kullanıcı adına tıklayınca profil açılır.
3. İptal Botu: pending_follow_requests dosyasını/klasörünü seç > "Tarayıcıyı Aç" > elle giriş yap > "İşlemi Başlat".
   İlerleme `durum.json` dosyasına kaydedilir; program yeniden açılınca işlenenler atlanır.

Not: Otomasyon Instagram kullanım koşullarına aykırı olabilir; düşük limitlerle kullan (günlük ~100).
Arayüz metinleri Instagram tarafından değişirse bot.py başındaki regex'ler güncellenmelidir.

## Tarayıcı notu
Bot, varsayılan tarayıcın Chrome/Edge/Brave ise onu kullanır (ayrı bir profil klasöründe, uzaktan kontrol portuyla).
Firefox/Safari varsayılansa kurulu ilk Chromium tabanlı tarayıcı açılır; hiçbiri yoksa Playwright Chromium kullanılır.
