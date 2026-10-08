# ZİTAR Next — eksik analizi

İnceleme: 8 Ekim 2026. Kaynak: private kadratuss/ZITAR-AI deposunun main ağacı (526 dosya), aşağıda belirtilen seçili kaynaklar, açık PR #8 ve yerel araştırma sonuçları. Bu bir kaynak kodu incelemesidir; üretim makinesinin süreçleri, ayarları, veritabanları ve yedekleri doğrulanmadı. Hiçbir üretim dosyası değiştirilmedi veya çalıştırılmadı. 85 test sonucu yalnızca yeni araştırma hattının test kümesini kapsar; bütün ZİTAR'ın regresyon sonucu değildir.

## Doğrulananlar

- Depo private, varsayılan dal main. Veri adaptörü ve sınırlı PPO araştırma hattı main'de.
- PR #8 açık ve birleştirilmemiş: bağımsız dashboard, öğrenme eğrileri, karar izleri.
- PPO: BTCUSDT spot simülasyonu, 1h kapanmış mum, iki hedef (tam uzun / nakit), sonraki açılışta sanal uygulama. Short/kaldıraç yok.
- Son 8192 adımlık deney: 17 eğitim/doğrulama kontrolü, 14 tamamlanan eğitim bölümü, 189 test kararı; test getirisi -%2,7183. Al-tut -%2,6728; SMA -%0,6079; nakit %0. Başarı veya yatırım katkısı doğrulanmadı.
- Mevcut kodda yerel Ollama model sınırı, bilgi/öğrenme günlüğü, araştırma döngüsü, paper çalışma zamanı ve süreç gözetimi bulunuyor. Bunların üretimde etkin olduğu bu incelemede doğrulanmadı.

## Öncelikli eksikler ve bitiş ölçütleri

| Sıra | Eksik | Kanıt / kapsam | Tamamlanma ölçütü |
|---|---|---|---|
| 1 | Gerçek kurulumun envanteri | GitHub ağacı çalışan sürümü, süreçleri, zamanlanmış görevleri, yapılandırmayı ve DB durumunu kanıtlamaz. | Salt okunur süreç/port/görev, giriş noktası, sürüm/hash, veri yolu, bağımlılık ve yedek listesi. |
| 2 | Yeniden kurulabilir paket | Ağaçta main.py var; bütün uygulama için kurulum manifesti/README ve örnek ayarlar yok. Model config .gitignore'da. App manager Repair-Zitar.ps1 ve zitar_app varlıklarını bekliyor; bunlar ağaçta yok. | Sır içermeyen örnek ayarlar, eksiksiz varlık/başlatıcı listesi, bağımlılık kilidi, temiz ortamda deneme ve geri dönüş belgesi. DB ve sırlar GitHub'a konulmaz. |
| 3 | ZİTAR–PPO bağlantısı | PPO bağımsız runner; zitar_runtime_v1 sohbet/bellek/finans yönlendirmesi yapıyor. İncelenen akışta PPO karar/deney sonucu bağlantısı yok. | ZİTAR'ın salt okunur deney durumunu ve kanıtlı sonuçları alması; model başarısı hakkında uydurma iddia üretmemesi. |
| 4 | Otomatik model eğitimi | online_research_pipeline.run tek snapshot üzerinde learn çağırıp bitiyor. Eski araştırma runtime'ı bilgi/kaynak/maliyet akışı yürütüyor; yeni PPO eğitimi buna bağlı değil. | Yeni kapanmış veri tetikleyicisi, tek iş kilidi, kaynak/süre sınırı, hata/yeniden başlatma, durum kaydı; gerçek emir kapalı. |
| 5 | Aday model seçme ve geri alma | zitar_learning_progress_v1 measured_improvements=0, agent_linked_experiments=0, automatic_promotion=False döndürüyor. Seçim motoru likidite araştırma önceliği; PPO model seçici değil. | Eski/yeni model aynı veri ve maliyetle kıyaslanır; önceden tanımlı başarı eşiği, sürüm kaydı ve geri alma bulunur. İlk aşama paper onayıyla sınırlı. |
| 6 | Öneri–deney–sonuç bağlantısı | Öğrenme ilerleme kodu bu bağlantının tamamlanmadığını açıkça belirtiyor. | Her öneri için deney kimliği, veri kimliği, model/sürüm, başarısızlık ölçütü ve doğrulanmış sonuç zinciri. |
| 7 | FinRL-X entegrasyon kapsamı | FinRL uyumlu veri kayıtları ve SB3/Gymnasium ortamı hazır; bunlar tam FinRL-X kurulumu/entegrasyonu demek değil. | Seçilecek resmi sürüm, lisans/bağımlılık/ücretsiz kullanım incelemesi, API uyumu ve mevcut hattın kabul testleri. |
| 8 | OpenClaw gereksinim kararı | İncelenen yeni araştırma hattında entegrasyon yok. Mevcut supervisor/kuyruk bazı işleri zaten karşılıyor. | Hangi somut açığı kapatacağı ve ek erişim gereksinimi belgelenir; gerekmezse eklenmez. |
| 9 | Daha güçlü yatırım değerlendirmesi | Son deneme 1000 saatlik mum ve tek seed; mevcut PPO karşılaştırmaları geçemedi. | Daha uzun veri, farklı piyasa dönemleri, birden çok seed, yürüyen zaman pencereleri ve maliyet stresleri. Tekrarlı test seçimini engelleyen dönem protokolü. |
| 10 | Eğitim izlemenin canlı durumu | Eğriler tamamlanmış deney raporundan okunuyor; sürmekte olan eğitimin ilerleme kaydı/polling bağlantısı yok. | Kuyrukta/eğitiliyor/doğrulanıyor/bitti/hata durumları, adım/süre/son güncelleme ve atomik ilerleme dosyası; dashboard tetiklemesi olmadan arka plan çalışma. |
| 11 | Sade ana menüye entegrasyon | Yeni panel bağımsız; mevcut ana menüyle birleştirilmedi. | Ana ekranda kısa öğrenme durumu, ayrıntılar ayrı görünümde; mevcut kullanım akışının regresyon kontrolü. |
| 12 | Zaman aralığı ve piyasa kapsamı | PPO runner 1h kullanıyor. Veri adaptörü 1h/1d kabul ediyor; bu günlük PPO desteği değildir. Eski MTF kodlarının varlığı da yeni modele bağlantıyı kanıtlamaz. | Her sembol/aralık için ayrı veri ve deney tanımı. 4h/dakikalık ancak açık gereksinim ve uyumluluk testleriyle eklenir. TRY/USDT hesapları ve maliyetleri karıştırılmaz. |
| 13 | Sistem genelinde emir kapalı doğrulaması | Yeni hatta broker yok; incelenen paper runtime real_order kapalı koşullarını denetliyor. Üretim ayarları incelenmedi. | Gerçek çalışma ayarlarının salt okunur kontrolü ve bütün yürütme yollarında emir kapalı kabul testi. |
| 14 | Genel regresyon ve ücretsiz kullanım denetimi | Araştırma kümesindeki 85 test bütün depoyu kapsamaz. Yerel model sınırı Ollama istiyor; bütün kaynak sağlayıcıları incelenmedi. | Çalışan sürüm için izole regresyon, yerel model/donanım uyumu ve dış servis/ücretli anahtar gereksinimleri envanteri. |

## Mevcut öğrenme türlerini ayırma

1. Kaynaklı bilgiyi öğrenme günlüğüne kaydetmek: mevcut kodda var; model ağırlık eğitimi değildir.
2. Yerel dil modeliyle anlatım: Ollama sınırı var; etkin model ayarı depoda yok. Eğitim taslakları ince ayar yapıldığını kanıtlamaz.
3. İşlem karar modelini eğitmek: PPO araştırma hattında var; şu anda elle başlatılan sınırlı deney.
4. Yatırım katkısına göre yeni modeli kabul etmek: yeni PPO için tamamlanmadı.

## Kaynaklar

- main.py: API girişleri ve zitar_runtime_v1 bağlantısı.
- zitar_runtime_v1.py: sohbet, proje belleği, öğrenme günlüğü, finans yönlendirmesi.
- zitar_model_provider_v1.py: yerel Ollama endpoint ve dışarıda tutulan ayar/kimlik dosyası beklentisi.
- zitar_training_data_v1.py: sentetik taslak veri; training_approved=False, trained=False manifesti.
- zitar_learning_progress_v1.py: öneri–deney bağlantısı ve bağımsız katkı eksikliği.
- zitar_research_runtime_v1.py: kontrollü öğrenme günlüğü ve 60 saniyelik araştırma döngüsü.
- zitar_paper_supervisor_v1.py: paper/araştırma/karşılaştırma süreç gözetimi.
- zitar_full_paper_runtime_v1.py: paper durum yazımı ve emir yetki kontrolleri.
- zitar_selection_engine_v1.py: araştırma önceliği; işlem izni/model seçimi değil.
- zitar_app_manager_v1.py ve .gitignore: depoda bulunmayan kurulum varlıkları ve dışarıda tutulan çalışma dosyaları.
- online_research_pipeline.py, research_environment.py, PR #8 ve LEARNING_RESULTS.md: yeni araştırma kapsamı ve sonuçları.

## Çalışma sırası

Önce çalışan sistemin salt okunur envanteri ve yeniden kurulabilirlik. Ardından öneri/deney sözleşmesi ile ZİTAR bağlantısı; sonra sınırlı otomatik eğitim, adil model kıyası ve geri alma. Son olarak sade menü entegrasyonu ve izole kabul denemesi. Üretim kurulumu ve gerçek emir bu raporun kapsamı değildir.

Kural uyumsuzluğu: kullanıcı Codex istemiyor; bu sohbet Codex uygulamasında yürütülüyor. Bu koşulun karşılandığı söylenemez; başka bir araçta devam tercihi teknik uygulama planından ayrı olarak çözülmelidir.
