# ZİTAR — Hostinger KVM4 geçiş paketi

Hedef: Ubuntu 24.04, Python 3.12, aynı sunucuda mevcut ZİTAR paper motoru,
RSI14 + PPO birleşik öğrenme, FinRL-X raporları ve tek dashboard girişi.
Bu paket henüz sunucuya kurulmuş değildir. Linux ve kaynak yükü kabul testleri,
sunucu satın alınıp SSH bağlantısı sağlandığında yapılacaktır.

## Hazır olanlar

`/` mevcut ZİTAR paneli; `/zitar-next/` öğrenme ve öneriler.
Gateway aynı origin ve CSRF kontrolünü korur. Tarayıcı geçerli insan onayı
vermeyen adayları etkinleştiremez. Birleşik karar sadece onaylanan bağımsız
paper hesapta yürütülür; mevcut ana hesabın işlem kararını değiştirmez.

Ana ekranın mevcut 5017 V3 veri bağımlılığı salt okunur `zitar-v3-data`
servisiyle sağlanır. Eski Windows saatlik V3 görevi sunucuda `zitar-v3.timer`
ve tek sahip kilidiyle karşılanır; mevcut RSI14 ve diğer aktif sanal vadeli
motorlardan ayrı referans deneyidir. İlgili geçmiş JSON/CSV durumları taşıma
görüntüsünde korunmalıdır. Windows görev durumunun Linux'ta gerçek timer
durumuyla gösterilmesi için okuma adaptörü vardır.

Öğrenme her yeni kapanmış saatlik mumda çalışır. Spot ve 3x izole vadeli için
iki sabit PPO tohumu, doğrulamada ağırlık seçimi, üç önceki walk-forward
penceresi, maliyet stresi ve RSI14/PPO/nakit/SMA karşılaştırmaları vardır.
Önceden incelenen test dönemleri yeniden kullanılırsa aday uygun sayılmaz.
Yeni bağımsız test penceresi birikmesi zaman alır; saatlik eğitim bu şartı
ortadan kaldırmaz. Başarılı yatırım stratejisi elde edildiği henüz kanıtlanmadı.

## KVM4 kaynak planı

Hostinger KVM4: 4 vCPU, 16 GB RAM, 200 GB NVMe. Kaynak bilgisi:
https://www.hostinger.com/vps/ubuntu-hosting
Öğrenme tek iş parçacığı ve %50 CPU sınırıyla çalışır; paper motoru önceliklidir.
Bu bir kapasite garantisi değildir. Gerçek VPS'te bellek/CPU, veri erişimi,
yeniden başlatma ve saatlik eğitim süresi ölçülecektir.

Mevcut sohbet modeli `qwen2.5:7b` olarak korunur. Ollama ayrı kurulur;
`ollama-kvm2.conf` tek istek, küçük context ve yanıt sonrası bellek boşaltma
ayarları içerir. 7B model + öğrenme için 16 GB hedeflenir. Yük testinde
kararlılık sağlanamazsa aynı modeli korumak için daha büyük VPS gerekir veya
senin seçiminle daha küçük sohbet modeli denenir. Model sessizce değiştirilmez.
https://docs.ollama.com/faq

## Kurulum ve taşıma sırası

1. Kod paketindeki `runtime/` klasörünü `/srv/zitar/runtime` olarak aktar.
   Python paketleri `hosting/requirements.txt` içindedir. `hosting/install.sh`
   bağımlılıkları ve servis tanımlarını hazırlar; servisleri başlatmaz.
2. PC'deki sahip süreçler, mevcut denetleyiciler, Windows'taki
   `PortfolioAI_MultiStrategy_Live` görevi ve Next worker kontrollü
   durdurulur. Bu adım sunucu hazır olduğunda yapılır. Şimdilik çalışan PC
   hesapları taşınmadı ve durdurulmadı.
3. Durdurulmuş kaynak üzerinde aşağıdaki komutla tutarlı hesap/DB/model
   görüntüsü alınır. Komut kilitli motor tespit ederse işlemi reddeder.
   Bu özel yedek yalnızca SSH üzerinden aktarılır; GitHub'a eklenmez.

```text
python -m zitar_next.hosting backup --base SOURCE_ZITAR --next-root SOURCE_NEXT --output PRIVATE_BACKUPS
```

4. SHA256 kontrolünden sonra yedek yeni, boş bir staging klasöründe açılır.
   `runtime` içindeki hesap/config/geçmiş dosyaları yeni sunucudaki runtime'a,
   `next` içindeki işaretçi, registry, model ve raporlar `/srv/zitar/data/next`e
   yerleştirilir. Aynı dosyanın eski hesabın üstüne körlemesine yazılması yoktur.
   Kod paketindeki yeni sürüm korunur. Kullanılan gizli ayarlar ayrıca aktarılır;
   dosya adıyla dışlanan sırlar bu yedekten geri gelmez.
5. Operatör PC sahiplerinin kapalı olduğunu doğruladıktan sonra
   `/srv/zitar/runtime/HOSTING_HANDOFF.json` oluşturur:

```json
{"source_owners_stopped":true,"real_orders":false}
```

6. `python -m zitar_next.hosting check --base /srv/zitar/runtime --next-root
   /srv/zitar/data/next` ve mevcut master `--once` doğrulaması çalıştırılır.
   Paket bağımlılıklarının tüm aktif modülleri kapsadığı VPS'te doğrulanır.
   Ardından servisler etkinleştirilir. PC'deki ikinci sahip açılmaz.

```text
systemctl enable --now zitar-v3-data zitar-production zitar-learning zitar-console zitar-gateway
systemctl enable --now zitar-v3.timer
systemctl enable --now zitar-backup.timer zitar-backup-monitor.timer
ssh -N -L 8080:127.0.0.1:8080 USER@VPS_IP
```

Tarayıcı: `http://127.0.0.1:8080/`. Servis portları internete açılmaz.
Telefon/tarayıcı üzerinden doğrudan alan adı erişimi istenirse erişim denetimi
ve HTTPS ayrıca kurulup test edilir. SSH tüneli mevcut hazırlığın erişim yoludur.

## Yedekleme ve geri dönüş

Güncel yedekleme, şifreli dış kopya ve güvenli saklama politikası BACKUP_POLICY.md içindedir. Dış hedef bağlantısı ve gerçek sunucuda geri yükleme testi tamamlanmadan geçiş kabul edilmez. Gerçek emirler kapalıdır.