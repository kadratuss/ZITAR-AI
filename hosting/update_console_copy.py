from pathlib import Path
p=Path('zitar_next/dashboard.html')
s=p.read_text(encoding='utf-8')
s=s.replace('Ortak ekran hazır. Çalışan ZİTAR’a henüz bağlanmadı.','Tek giriş hazır: ana ZİTAR paneli ve bağımsız öğrenme ekranı birlikte açılır.')
s=s.replace('Ana menüde tek “Araştırma ve öğrenme” bağlantısı için montaj bileşeni hazırlandı. Kurulum son aşamada yapılacak.','Ana panelde Araştırma ve öğrenme bağlantısı gateway üzerinden sağlanır. Öneri onayı ana hesabın işlem kararını değiştirmez.')
s=s.replace('Üretime bağlantı ve kurulum en son aşama. Deneyler geçmiş verideki sonuçları gösterir.','Hosting paketi hazırlandı; sunucu kurulumu ve kaynak yükü testi bekleniyor. Deneyler geçmiş verideki sonuçları gösterir.')
s=s.replace('for(const r of b.seed_results){','for(const r of (b.combination?.seed_results||b.seed_results)){')
s=s.replace("+' · Araştırma testi; etkinleştirme kapalı.'", "+' · '+(r.eligible?'Kanıt eşiği geçti; insan onayı gerekli.':'Kanıt yetersiz; etkinleştirme kapalı.')")
p.write_text(s,encoding='utf-8')
