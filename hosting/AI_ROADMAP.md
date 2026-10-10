# ZİTAR AI: ölçülebilir gelişim yol haritası

Amaç: sabit bir AI sürümünün, RSI14'e göre komisyon ve risk sonrası katkısını
bağımsız verilerde göstermek. Altyapı testleri yatırım başarısının kanıtı değildir.
Hiçbir aşama otomatik gerçek emir veya otomatik strateji etkinleştirme açmaz.

## 1. Kanıt envanteri — uygulandı

`python -m zitar_next.evidence_audit` çalışan panelden salt okunur veriler alır.
Aday sayısı, uygunluk, sıfır işlem, eğitim başlangıçları arasında getiri işareti
uyuşmazlığı, yeniden kullanılan test dönemleri ve mevcut eşikler raporlanır.
Token, API anahtarı veya hesap bakiyesi dışarı aktarılmaz.
Bu ölçüm modeli eğitmez, üretim hesaplarını veya registry'yi değiştirmez.
UI artık anlaşılır gerekçeleri, uygunluk rengini ve sanal test aşamalarını gösterir.

## 2. Deney protokolünü sabitle — ilk kayıt uygulandı

10 Ekim 2026: `comparison_protocol` aracı ve 3 kontrol testi eklendi.
Spot/vadeli son iki adayın tam rapor, veri, scaler ve model kimlikleri doğrulandı.
Sunucuda `/srv/zitar/data/study-20261010-v1/protocol.json` ve `comparison.md`
ayrı araştırma çıktısı oluşturuldu; 8 envanter/protokol testi başarılı.
Mevcut geçmiş sonuçlar yeni bağımsız kanıt sayılmaz ve hiçbir aday etkinleştirilmedi.
Bu kayıt seçilen dosyaların hash'lerini sabitler; henüz bütün yazılım bağımlılıkları
ve üretim motoruyla eşlik için tam tekrar üretim kabulü değildir.

Önceden kayıtlı tek protokol: RSI14, AI, birleşik karar, nakit, al/tut ve SMA;
aynı veri, sermaye, komisyon, kayma ve vadeli funding varsayımları.
Tek tek eğitim başlangıçlarıyla birlikte gerçekten kullanılan oybirliği modeli
raporlanır. En iyi tohum seçilip başarı diye sunulmaz.
Veri/sinyal/kod/model kimliği ve deney bütçesi sürümlenir.
Mevcut eşikler gevşetilmez; eşik değişirse yeni protokol sürümü gerekir.
Çıkış ölçütü: karşılaştırmalar aynı koşullarda, yeniden üretilebilir ve hash bağlı.

## 3. Yeni test dönemi ve daha geniş veri

10 Ekim 2026: `forward_study` ayrı salt okunur model araştırması olarak kuruldu.
`zitar-forward-study.timer` her saat UTC dakika 12'de çalışır. İlk çalışması
başarılı; yeni mum bekliyor. Model kimlikleri ve AI ağırlığı sabittir; yeni
verilerle yeniden eğitim yapılmaz. Çalışma kaydının oluşturulmasından sonraki
ilk tam saatten başlayan 30 günlük veri penceresi kullanılır.
Kayıtlar Next yedek kapsamındaki `studies/20261010-v1` dizinindedir.
Bu düzen adayları kabul etmez ve bağımsız paper hesabı etkinleştirmez.
Uygun olmayan sabit adayların davranışı yalnızca tanı amaçlı gözlemlenir.
Ara sonuçlarda her yeniden değerlendirmede son mumda sanal kapanış vardır;
ara raporlar kalıcı açık pozisyonlu canlı hesap performansı diye sunulmaz.
Süre sonunda tam 720 saatlik mum yoksa eksik veri olarak işaretlenir.
Sıfır işlem tanısı: son spot ve vadeli adaylarda iki seed de 589 kararın
tamamında nakit seçmiştir; veto uyuşmazlığı sıfırdır. Bu öğrenme davranışının
nedeni hâlâ ayrı eğitim deneyi gerektirir. 11 odaklı kontrol testi geçti.

Saatlik araştırma ile uygunluk değerlendirmesi ayrılır. Örtüşen testler yalnızca
araştırma sayılır. Sabit aday, seçildikten sonra biriken yeni veride değerlendirilir;
yeni veri eğitim veya ağırlık seçiminde kullanılmaz. 150 mum şartı tek başına
başarı değildir; işlem sayısı ve diğer koşullar da gerekir.
Gelecek veri olmadan bağımsız ileri test bugün tamamlandı denemez.
Önce BTCUSDT ve ETHUSDT; spot/vadeli veri ayrı. Daha uzun geçmiş için sayfalama,
funding kapsamı ve veri kalite kontrolleri genişletilir. Eksik funding reddedilir.
Yükseliş/düşüş/yatay dönemler önceden tanımlanır; test sonucuna göre seçilmez.
Çıkış ölçütü: tarihleri ayrık, verisi eksiksiz ve seçimden bağımsız testler.

## 4. AI'ın görevini daralt ve eğitim bütçesini karşılaştır

10 Ekim: BTC/ETH, spot/vadeli dört giriş filtresi deneyi tamamlandı.
Her biri 8.760 saatlik mum; iki seed (42/73), 2.048/8.192 eğitim adımı.
Bütçe yalnızca doğrulamayla seçilip final testten önce kaydedildi; dördünde
8.192 seçildi. Test 1.742 mum, 30 Temmuz 06:00 → 10 Ekim 19:00 UTC.
AI yalnızca yeni RSI14 girişini filtreler, mevcut RSI tutma/çıkışını korur.

| Piyasa | RSI14 | Filtre oybirliği | Filtre maliyet stresi | Dolum |
|---|---:|---:|---:|---:|
| BTC spot | -15,77% | 0,00% | 0,00% | 0 |
| ETH spot | -12,66% | -1,32% | -3,66% | 12 |
| BTC vadeli 3x izole | -9,55% | -0,31% | -0,94% | 30 |
| ETH vadeli 3x izole | -6,63% | -5,37% | -7,56% | 112 |

Sonuçlar Strateji önerileri menüsündedir. RSI'a göre kaybı azaltmak pozitif
yatırım katkısı değildir; hiçbir aday uygun değil veya etkinleştirilmiş değil.
Bu ilk deney tamamlandı; farklı dönem, yeni veri ve üretim motoruyla eşlik
kanıtı gerekli. Küçük bütçenin bütün eğitim dönemini dolaşmaması raporlandı.

İlk deney: RSI14 girişini filtreleyen AI; ikinci ayrı deney: risk/pozisyon boyutu.
Aynı anda ikisi değiştirilmez. Eğitim bütçeleri doğrulama verisiyle karşılaştırılır;
daha çok adımın daha iyi olduğu varsayılmaz. Final test seçim için kullanılmaz.
Saatlik üretim motorunun risk kurallarıyla araştırma simülatörünün farkları
ayrı eşlik testinde incelenir; tam üretim eşliği kanıtlanmadan iddia edilmez.
Çıkış ölçütü: tüm model başlangıçları ve oybirliği sürümü için net katkı ve risk.

## 5. Sabit sürümle ileri sanal test

Geçmiş eşiklerini geçen adayı kullanıcı kabul eder; bağımsız Next paper alanında
etkinleştirir. RSI referansı aynı dönemde izlenir. Süreçte model değiştirilmez;
yeni modeller ayrı aday olur. Mevcut işlem motoru korunur.
En az 30 takvim günlük ilk gözlem planlanır; 30 gün başarı garantisi değildir.
Yeterli işlem, maliyet stresi, düşüş ve bağımsız dönem şartları ayrıca sağlanmalıdır.
Günlük getiriler, özkaynak, düşüş, işlem maliyeti ve veri kesintileri raporlanır.
Çıkış ölçütü: dondurulmuş sürümün referansa katkısını gösteren ileri test raporu.

## 6. Operasyon kabulü

10 Ekim: gerçek şifreli Drive arşivi ayrı alana indirildi/açıldı. SHA256,
35 SQLite integrity_check, 29 model arşivi ve 14 eski öneri kaydı doğrulandı.
Canlı hesaplara yazılmadı; özel ayarlar/venv ile tam servis dönüşü değildir.
Günlük 03:30 İstanbul yedeği ve 15 dakikalık sağlık kontrolü etkin;
dış bildirim kanalı henüz bağlı değil.

Kontrollü reboot geçti: 10 temel servis otomatik döndü; sıfırlama makbuzu,
öneri geçmişi, etkin strateji durumu ve giriş filtresi raporu korundu.
15 dakikalık operasyon gözlemi başladı; 24 saat henüz dolmadı. Beklenmeyen
kesinti, boot değişimi veya 30 dakikadan uzun örnekleme boşluğu süreyi sıfırlar.
Planlı yedek duruşu ayrı gösterilir. Bu örneklem kontrolü kesintisiz erişim
garantisi değildir; sonuç Strateji önerileri > Sunucu çalışma kontrolü içindedir.

24 saat çalışma, kontrollü yeniden başlatma, gerçek bulut yedeğinden ayrı alana
geri yükleme, disk/kota kontrolü ve seçilecek dış bildirim kanalı doğrulanır.
Servislerin aktif olması bunların tamamının geçtiği anlamına gelmez.
GitHub'da kod ile sunucuda çalışan sürümün eşliği ve açık PR'lar kayda alınır.
Gerçek emir konusu ayrı insan kararıdır; bu yol haritası o izni vermez.

Her aşama bir raporla kapanır: yapılan değişiklik, karşılaştırma, sınırlamalar
ve devam/geri dön kararı. Başarılı AI elde edilemezse RSI veya nakit referansını
korumak geçerli sonuçtur. Toplam süre yeni verinin birikmesine bağlıdır.
