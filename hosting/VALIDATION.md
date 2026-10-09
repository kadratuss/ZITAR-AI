# Yerel kabul sonuçları — 9 Ekim 2026

- 141 unittest testi geçti: eğitim, registry onayı, paper yürütme, veri,
  FinRL-X, birleştirme, gateway, yedekten registry dönüşü ve vadeli kâr stopu.
- Gerçek Binance BTCUSDT saatlik spot ve vadeli snapshot'larıyla iki PPO
  tohumu, 2048 eğitim adımı ve üç ayrı önceki walk-forward penceresi çalıştı.
- Aktif normal ZİTAR'ın RSI14 kuralı birleşik adayın referansıdır. Karşılaştırma
  bağımsız USDT simülatöründedir; mevcut TRY master muhasebesinin veya bütün
  üretim motorunun eşdeğeri değildir.

| Piyasa | RSI14 | PPO | Birleşik |
|---|---:|---:|---:|
| Spot | -4,3746% | -5,3230% | -4,3746% |
| Vadeli 3x izole | -2,5306% | 0,0000% | 0,0000% |

Vadeli modelin sıfır getirisi işlem üretmemesinden kaynaklanır; başarılı
yatırım stratejisi kanıtı değildir. İki aday da uygunsuz: benchmark avantajı,
pozitif maliyet stresi ve walk-forward kanıtı eksik; önceki test dönemiyle
örtüşme var. Spot düşüş sınırını da aşıyor. Hiçbiri kabul/etkinleştirilmedi.

Örtüşen saatlik denemeler artık fresh-holdout sınırını ileri taşımıyor.
Bağımsız yeni test dönemi biriktiğinde ayrı değerlendirme mümkün olacak.

Tek giriş `http://127.0.0.1:8080/` üzerinde mevcut ana panel, öğrenme bağlantısı
ve Next API erişimi doğrulandı. Gateway üzerinden fixture kabul/etkinleştirme,
CSRF ve yabancı origin reddi test edildi; gerçek adaylarda onay yapılmadı.

Python bağımlılık kontrolü başarılı. KVM2 henüz satın alınmadı. Linux servis
başlatma/reboot, gerçek kaynak yükü, Ollama 7B performansı, veri bölgesi erişimi,
24 saat koşusu ve sunucudaki yedekten servis dönüşü henüz doğrulanmadı.
Gerçek emir bağlantısı yoktur; bu paket o bağlantıyı eklemez.
