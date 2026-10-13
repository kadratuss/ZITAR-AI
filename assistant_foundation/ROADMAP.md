# ZİTAR genel asistan: doğrulanmış başlangıç

İnceleme tarihi: 12 Ekim 2026, Europe/Istanbul.

## Gerçekte bağlı parçalar

- Ana panelde `/api/chat-proxy/chat`, `zitar_unified_chat_v1.answer` üzerinden yanıt üretir. Ayrı `zitar-chat` sağlık/araştırma servisi bütün sohbet akışı değildir.
- Model sınırı: `zitar_model_provider_v1`; Ollama, `zitar:base-v1`, temel `qwen2.5:7b`, Q4_K_M, 7.6B. Yapılandırma ince ayar yapılmadığını bildirir. Modelin yeniden adlandırılması eğitim kanıtı değildir.
- Sohbet geçmişi SQLite üzerinde oturum bazında tutulur; modele son 12 tur aktarılır.
- Açık iletişim tercihleri ayrı SQLite tablosunda tutulur. Tercih görüntüleme ve unutma komutları vardır. Genel proje/fakt hafızasıyla aynı şey değildir.
- Araştırma görev kuyruğu, kaynak okuma, kanıt denetimi ve kayıtlı öneri mekanizması vardır. On rol aynı yerel modelden yararlanır; on ayrı model değildir.
- Araştırma önerisi üretimi strateji kapsamıyla sınırlıdır ve `PROPOSED_NOT_TESTED` kaydeder. Genel asistanın deney/onay/geri dönüş döngüsünü tamamlamaz.
- Araç tamamlama iddialarını kayıtlı görev durumuna bağlayan doğruluk koruması vardır.
- Genel sohbet talimatı araç kullanma yetkisi olmadığını belirtir. Belge üretimi, takvim değişikliği veya dosya üzerinde görev yürütme bu incelemede doğrulanmadı.

## Ölçüm sınırı

`baseline.py` gerçek `converse` fonksiyonunu sentetik sorularla çağırır. Üç tercih kontrolü geçici klasörde yapılır; yatırım ve gerçek kullanıcı hafıza verileri değiştirilmez. Altı model sorusu sabit ve sınırlıdır. Sonuçların mekanik kontrolü tam anlam doğruluğu veya genel zekâ puanı değildir. Araç, web araştırması ve uçtan uca panel testi ayrıca gereklidir.

## Sıradaki somut geliştirme

1. Ayrı çalışma alanında görev kaydı: kimlik, amaç, girdiler, durum, çıktılar, hata, süre; yeniden başlatma sonrası geri yükleme.
2. İlk üç araç: kullanıcı tarafından verilen metni özetleme, JSON/CSV doğrulama ve çalışma alanına rapor yazma. Hesaplar, emirler, kimlik bilgileri ve serbest kabuk erişimi kapsam dışı.
3. İzin verilen araçların açık şeması; modelin metinsel iddiası yerine araç çıktısıyla tamamlanma.
4. On sabit uçtan uca görev: başarılı iş, eksik girdi, hatalı dosya, oturum ayrımı, belge içi talimat, başarısız araç, yeniden başlatma, çıktı doğrulama, tekrar çalıştırma ve geri alma.
5. Aynı testlerin önce/sonra karşılaştırması. Yeni sürüm bütün kritik güvenlik/doğruluk kontrollerini geçmeden çalışan sürüme alınmaz.
6. Ardından kalıcı proje hafızası: kaynak/tarih, düzeltme, unutma ve çelişki yönetimi. Eğitim ve kaynaklı hafıza ayrı raporlanır.

## Mevcut yatırım sınırı

İki RSI hesabı ve on iki yeni strateji uyarlaması bu genel asistan çalışmasından bağımsızdır. Bu başlangıç değerlendirmesi hiçbir hesabı sıfırlamaz, strateji etkinleştirmez veya gerçek emir açmaz.

## Açık kalan işler

- Araştırma kuyruğunun baştan sona genel bir konuda başarısı henüz bu test setinde ölçülmedi.
- Proje hafızası, genel araçlar, onaylı güncelleme ve geri dönüş tek bir çalışan akışta birleştirilmedi.
- Model, kütüphane ve kaynak kod lisanslarının tam envanteri hazırlanmadı.
- Geniş model veya donanım yükseltmesi gerekliliği bu küçük testten çıkarılamaz.

## Bu aşamada hazırlanan prototip

`tasks.py`, ayrı çalışma alanında SQLite görev kuyruğu sağlar. Yalnız kayıtlı
`calculate` ve `validate_json` araçlarını çalıştırır; kullanıcı girdisini kod,
kabuk veya serbest dosya işlemi olarak yürütmez. Sonuç yalnız araç başarıyla
döndüğünde `SUCCEEDED` olur. Beklenen hatalar `FAILED` olarak kaydedilir.
Tamamlanmış görev yeniden çalıştırıldığında aynı kayıt döner. İşlem sırasında
kesinti olursa SQLite işlemi geri alınır; bu iki araç dış yan etki üretmez.

Hesaplama aracı ondalık sayıları Decimal ile işler; JSON aracı yinelenen
anahtar ve standart dışı NaN/Infinity değerlerini reddeder. Görev kalıcılığı,
ayrı çalışma alanı, yanlış başarı iddiası ve araç sınırları dahil 12 kontrol
bilgisayarda ve sunucudaki ayrı test alanında geçti. Bu prototip üretim
sohbetine bağlı değildir; kullanıcılar arası yetkilendirme ve HTTP API henüz
eklenmemiştir. Bu sınırlar tamamlanmadan genel erişime açılmaz.
