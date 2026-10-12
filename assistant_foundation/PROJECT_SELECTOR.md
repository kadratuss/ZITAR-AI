# Aktif proje göstergesi — sınırlı entegrasyon

Bu kayıt yalnız aktif proje adı ve proje seçimi bileşenini içerir. Canlı panelde bileşen doğrulandı. Tam dashboard kaynakları bu commit ile yeniden yayımlanmaz.

## Bileşen
`project_selector.html` mevcut chatView içine proje başlığı ve seçim alanı ekler. Proje seçimi mevcut chat-proxy/chat akışındaki açık kullanıcı komutlarını kullanır. Finans, API anahtarı veya işlem kontrol kodu içermez.

## Geçmiş yanıtına proje bilgisi
Mevcut /api/chat-proxy/history yanıtının oluşturulduğu yerde:
```python
from assistant_foundation.project_memory import scope
session = (query.get('session_id') or ['default'])[0]
return self.send({'turns': history(base, session), 'project': scope(base, session), 'shared': session.startswith('project_')})
```

## Geçmiş yenilemesinde başlık
Geçmiş JSON yanıtı okunduktan sonra:
```javascript
const scopeLabel = document.getElementById('activeChatProject');
if (scopeLabel) scopeLabel.textContent = data.project
  ? 'Proje: ' + data.project + ' · Ortak sohbet'
  : 'Özel sohbet · Proje seçilmedi';
```

Bileşeni mevcut sohbet betiklerinden sonra yükle. Ortak geçmişi yenileyen restoreZitarHistory ve sharedHistorySignature önceki ortak sohbet değişikliğine aittir.

Doğrulama: iki farklı cihaz girişindeki test oturumları aynı dört mesajı okudu. Ekranda Proje: ZİTAR · Ortak sohbet başlığı doğrulandı. Kullanıcının önceki özel konuşmaları otomatik taşınmaz.
