# Telefonla özel izleme

Sunucuya Tailscale kuruldu. Hesap eşleştirmesi tamamlanmadan uzaktan erişim hazır sayılmaz.
Telefonun Tailscale uygulamasında sunucuyla aynı hesaba giriş gerekir.

`zitar-mobile-monitor` yalnızca 127.0.0.1:8081 üzerinde dinler. GET isteklerini
mevcut gateway'e aktarır, POST/PUT/PATCH/DELETE işlemlerini reddeder.
Telefon izleme girişi mevcut yerel kontrol panelinden ayrıdır.

Eşleştirmeden sonra sunucuda:

```sh
tailscale serve --bg --https=443 http://127.0.0.1:8081
tailscale serve status
```

Serve'ın HTTPS izni istenirse hesabın sahibi verilen bağlantıdan etkinleştirir.
Funnel kullanılmaz. Sunucunun genel IP'sine panel portları açılmaz.
Serve arka plan yapılandırması yeniden başlatmada korunur.
Adres, eşleştirme sonrası Tailscale'ın verdiği HTTPS adresidir; tahmin edilmez.
Telefonda bu adres tarayıcıda açılıp ana ekrana kısayol olarak eklenebilir.
Bu kısayol ayrı bir yerel mobil uygulama değildir.

Sunucu cihazının anahtar süresi ve tailnet erişim kuralları hesap yönetiminde
kontrol edilmelidir. Telefonda başka VPN kullanılıyorsa Tailscale ile çakışabilir.
