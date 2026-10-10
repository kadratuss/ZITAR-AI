# KVM4 sunucu kabul kaydı — 10 Ekim 2026

## Son durum — 23:20 İstanbul

Kod/durum KVM4'e taşındı, PC işlem sahipleri kapalı. Üretim, öğrenme,
birleşik panel, V3, ücretsiz yerel qwen2.5:7b sohbet/RAG servisleri etkin.
Gerçek emir kapalı; hiçbir araştırma adayı otomatik etkinleşmez.
PC SSH tüneli, telefon salt okunur Tailscale HTTPS panelini kullanır.
33 sanal hesap kullanıcı isteğiyle başlangıçta 10.000'e sıfırlandı;
bu yeni araştırma deneyi canlı sanal hesapları tekrar sıfırlamadı.

Google Drive crypt yedeği ve günlük/sağlık timer'ları etkin. Gerçek bulut
arşivi ayrı alana indirilip açıldı: SHA256, 35 SQLite bütünlük kontrolü,
29 model arşivi ve 14 yedeklenmiş öneri doğrulandı. Canlı hesaplara yazılmadı.
Özel bağlantı ayarları, venv ve işletim sistemi bu arşiv dışındadır.

Dört BTC/ETH spot/vadeli, bir yıllık saatlik giriş filtresi deneyi tamamlandı;
hiçbiri uygun değil. Sonuçlar Strateji önerileri menüsünde. 171 yerel unittest
üretim modüllerinin salt okunur bağımlılığıyla geçti; Linux'ta 23 odaklı test geçti.
30 günlük yeni veri gözlemi sürüyor, 9 Kasım 23:00 İstanbul'da biter.

Kalan kabul: kontrollü reboot raporu, 24 saat çalışma, özel ayarlar/venv ile
tam servis geri dönüşü ve dış bildirim kanalı. Gerçek emir izni verilmedi.

## İlk hazırlık günlüğü — aşağıdaki eksik durumlar eski kayıttır

Ubuntu 24.04.5 LTS, 4 CPU, yaklaşık 16 GB RAM doğrulandı.
Kod paketi SHA256: ef0f5a9dabee90ea44c001eff993d5acd29ab55de0272954a42d84ea32dea139.
Bağımlılıklar kuruldu, pip check başarılı; servis tanımları systemd-analyze
verify ile kontrol edildi. ZİTAR servisleri henüz etkinleştirilmedi.

Yerel proje kapsamındaki 150 unittest sunucuda geçti. Eski üretim kaynaklarıyla
birlikte geniş discovery: 460 test, 22 hata, 2 başarısızlık, 1 skip.
Bu sonuç başarılı tam sürüm kabulü değildir. Hatalar Windows mutlak yolları,
eksik taşınmamış durum/fixture dosyaları ve Windows DPAPI bağımlılığını içerir.
İki başarısız test: API hata etiketi beklentisi ve strateji arşivi sayısı
beklentisi. Roster kodu hem ilk seçim hem roster değişimi için arşiv oluşturur;
yalnızca bir arşiv bekleyen eski testin sürüm uyumu incelenmelidir.

hosting.validate_restore gerçek arşivi geçici ortamda açtı; SQLite
integrity_check, satır verisi, bakiye, registry, checksum ve .env dışlama geçti.
Gerçek hesap veya veritabanı değiştirilmedi. Bu deneme gerçek hesaplarla servis
geri dönüşünün yerine geçmez.

Eksikler: seçilecek bulut hesabında encrypted remote bağlantısı ve round-trip,
bildirim kanalı, tam durum aktarımı, Linux API kasası, Ollama 7B kurulumu ve
yük testi, gerçek servis yeniden başlatma / 24 saat koşusu.
Windows DPAPI verisi Linux'a doğrudan taşınamaz; anahtarlar özel taşıma ve
uygun Linux şifreli saklama olmadan kullanılmamalıdır. Gerçek emir kapalıdır.

Güncelleme: kullanıcı Google Drive drive.file iznini verdi. zitarcrypt
üzerinden izole SQLite deneme yedeği yüklendi, yeniden indirildi, SHA256 ve
integrity_check başarılı oldu. Kurtarma yapılandırmasının özel yerel kopyası
alındı. Gerçek hesap yedeği, günlük timer ve dış bildirim henüz devrede değil.
