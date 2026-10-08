# ZITAR AI — FinRL Entegrasyon Tasarımı v1

Durum: TASLAK / SADECE PLAN. Çalışan sistem ve main dalı değiştirilmedi.

## Doğrulanan mevcut dosyalar
- `main.py`: FastAPI uygulaması ve API router'ları.
- `zitar_runtime_v1.py`: sohbet, hafıza ve finans köprüsü.
- `zitar_research_runtime_v1.py`: kanıt/öğrenme adayı denetimleri.
- `zitar_research_council_v1.py`: araştırma görevleri; işlem yazma yetkisi olmadan tasarlanmış.
- `zitar_strategy_lab_v1.py`: kontrol ve aday strateji kıyaslaması; otomatik terfi yok.
- `multistrategy_risk_engine_v3.py`: risk politikası değerlendirmesi.
- `zitar_strategy_selection_v1.py`: paper strateji seçimi ve arşivleme.
- `zitar_full_paper_runtime_v1.py`: tek yazıcılı Master paper adaptörü; real_orders=False.
- `zitar_master_execution_bridge_v1.py`: olayların Master paper motoruna aktarılması.
- `zitar_master_paper_engine_v1.py`: sanal portföy ve işlem muhasebesi.
- `zitar_futures_paper_runtime_v1.py`: halka açık veri ile futures paper worker.

## Hedef mimari
ZİTAR (tek ana koordinatör) -> Araştırma Konseyi / FinRL (öneri üretimi) -> Değişmez deney kayıtları -> Strateji Laboratuvarı (out-of-sample değerlendirme) -> Risk politikası -> YALNIZCA ONAYLI paper deneyi.

FinRL hiçbir koşulda borsa emri, API anahtarı, canlı portföy durumu veya Master state dosyalarına yazma yetkisi almaz. OpenClaw gibi ajan araçları ileride eklense bile aynı sınır geçerlidir.

## Uygulama sırası ve kabul kapıları
1. **Envanter ve bağımlılık haritası**: aktif giriş noktası, scheduler, gerçek çağrı zinciri ve testleri tespit et. Tarihsel backup dosyalarını aktif modül sanma.
2. **Salt-okunur araştırma veri sözleşmesi**: zaman damgası, kaynak, sembol, ücret, slippage, eğitim/test dönemi, veri sızıntısı kontrolleri. JSON schema ve fixture testleri.
3. **FinRL ayrı ortam**: lisans ve bağımlılık denetimi; yalnızca lokal ve ücretsiz kullanım; ana Python ortamına paket yükleme yok.
4. **Aday çıktı adaptörü**: FinRL önerisi -> versiyonlanmış araştırma artefaktı; emir sinyali veya yürütme yetkisi değil.
5. **Deney kapısı**: baseline karşılaştırması, out-of-sample, walk-forward, ücret/slippage, drawdown, aşırı uyum ve veri sızıntısı testleri. Başarısız aday reddedilir.
6. **Paper pilot**: ayrı test durumu, kilit/tek-yazıcı güvenceleri ve açık kullanıcı onayı; üretim Master state'ine yazma yok.
7. **Arayüz**: yeni deney menüleri açmadan tek 'AI Araştırma' özet ekranı. Ayrıntılar yalnızca isteğe bağlı.
8. **Güvenli Git eşitleme**: sadece incelenmiş kaynak dosyaları; secrets, db, logs, state ve model çıktıları hariç. Otomatik push varsayılan olarak kapalı.

## Güvenlik ve gerçekçilik
- Gerçek emirler kapalı kalır. Read-only Binance erişimi değiştirilmez.
- Kâr, günlük yüzde hedefi veya öğrenme başarısı garanti edilemez. Ödül sinyali net risk-ayarlı sonuçları ölçer; kendini koruma ya da para kazanma zorunluluğu tanımlamaz.
- Bağımsız testlerden geçmeden hiçbir aday otomatik terfi ettirilmez.
- Bu belge uygulama kodu değildir; henüz entegrasyon testi çalıştırılmamıştır.
