# KVM4 yedekleme ve kabul şartları

Hedef KVM4: 4 vCPU, 16 GB RAM, 200 GB NVMe. Gerçek sunucu yük testi bekliyor.

Günlük yedek 03:30 İstanbul saatinde alınır. Aynı anda ikinci yedek çalışamaz.
Kaynak boyutu + 2 GiB boş alan yoksa başlamaz. Motorlar tutarlı görüntü için
durdurulur; hata durumunda yeniden başlatma denenir. Arşiv geçici dosyada
yazılır, tamamı okunarak doğrulanır ve ancak sonra tamamlanmış adını alır.
SHA256 ve şifreli dış kopyanın indirerek içerik karşılaştırması gerekir.
Aktarım öncesinde motorlar yeniden çalıştırılır.

## Dış hedef bağlantısı

Kurulum sırasında ayrı depolama hesabı / NAS / ikinci sunucu seçilecek.
Root'a özel `/etc/zitar/rclone.conf` içinde `zitarcrypt` adlı rclone crypt
remote kurulur. Şifre ve kurtarma anahtarı sunucu dışında güvenli saklanır;
anahtar kaybolursa şifreli yedek açılamaz. Bu dosyalar GitHub'a eklenmez.
`/etc/zitar/backup.env` root sahibi ve 0600 izinli olmalıdır:

```sh
ZITAR_BACKUP_REMOTE='zitarcrypt:zitar-backups'
ZITAR_RCLONE_CONFIG='/etc/zitar/rclone.conf'
```

Bağlantı yoksa servis başarı bildirmez, eski yedekleri silmez.
Yedi yerel kopya tutulur; yalnızca doğrulanmış dış kopya makbuzu olan eski
arşivler temizlenir. Başarısız/eksik yedekler otomatik silinmez.
Dış depolamada otomatik silme henüz yoktur; kapasite ve saklama süresi hedef
seçilince belirlenmelidir. Geçmiş veriler / modeller kaynakta bu işlemle silinmez.
Disk ihtiyacı yaklaşık: uygulama/veri + 7 sıkıştırılmış yedek + yeni yedek alanı.

Başarısızlık systemd journal ve BACKUP_FAILED dosyasına yazılır; başarı zamanı
BACKUP_LAST_SUCCESS dosyasında tutulur. Bunlar kayıt mekanizmasıdır;
telefona/e-postaya bildirim henüz bağlı değildir. Sunucu izleyicisi disk %80,
başarısız servis ve 26 saatten eski başarı durumunda bildirim vermelidir.
Bu izleyici ve bildirim hedefi kurulmadan gözetimsiz üretim kabulü verilmez.

## Geri yükleme ve gerçek emir güvenliği

Yedek boş staging dizinine açılır; canlı hesap üzerine yazılmaz. SQLite
integrity_check, registry/model dosyaları ve bakiyeler kontrol edilir.
Gizli bağlantı ayarları bu yedeğe dahil değildir, ayrıca güvenli taşınır.
Önce paper ortamda gerçek servis geri dönüşü ve yeniden başlatma denenir.
Eski PC'deki süreçler tekrar sahip olmaz. Gerçek emir döneminde eski yedekten
kalkış otomatik işlem başlatmamalıdır: borsa bakiye/pozisyon/emirleriyle
mutabakat ve yeni insan onayı gerekir. Mevcut paket paper-only'dir.

Hostinger haftalık yedek ek korumadır; dış uygulama yedeğinin yerini tutmaz.
Kaynak: https://www.hostinger.com/support/1583232-how-to-back-up-or-restore-a-vps-at-hostinger/
