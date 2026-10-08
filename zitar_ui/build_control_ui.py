import ast
from pathlib import Path

root = Path(__file__).resolve().parent
tree = ast.parse((root / 'ui_reference/zitar_control_center_v2_3_1_test.py').read_text(encoding='utf-8-sig'))
html = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'HTML' for t in n.targets))

html = html.replace('<title>ZİTAR Control Center</title>', '<title>ZİTAR · Birleşik Kontrol Merkezi</title>')
html = html.replace('<button class="btn disabled" data-i18n="navMarkets">', '<button class="btn" id="marketsBtn" data-i18n="navMarkets">')
html = html.replace('<button class="btn disabled" data-i18n="navExperiments">', '<button class="btn" id="experimentsBtn" data-i18n="navExperiments">')
html = html.replace('<button class="btn disabled" data-i18n="navSystem">', '<button class="btn" id="systemBtn" data-i18n="navSystem">')
html = html.replace('<div class="nav">', '<div class="nav" aria-label="Ana bölümler">')
html = html.replace('<button class="btn" id="researchBtn"', '<button class="btn" id="masterBtn">Master</button><button class="btn" id="researchBtn"')
html = html.replace('<span class="badge red" data-i18n="realoff">', '<span class="badge" data-i18n="v3off">V3 WRITE OFF</span><span class="badge" data-i18n="futuresoff">FUTURES OFF</span><span class="badge red" data-i18n="realoff">')
html = html.replace('class="btn disabled" title="Preview only"', 'class="btn disabled" disabled title="Salt okunur kontrol merkezi"')
html = html.replace('<div id="dashboardView">', '<div id="connectionAlert" class="controlnote" role="status"></div><div id="dashboardView">')

# Existing hero now shows the Master; preserve all three V3 strategy cards below.
for old, new in [('totalEquity','masterEquity'),('totalPnl','masterPnl'),('totalReturn','masterReturn'),('totalPositions','masterPositionCount')]:
    html = html.replace('id="' + old + '"', 'id="' + new + '"', 1)
html = html.replace('<div class="value" id="systemState">MONITORING</div>', '<div class="value" id="systemState">--</div>')
html = html.replace('<div class="health"><div', '<div class="health"><div class="healthitem"><span>Master runtime</span><strong id="runtimeHealth">--</strong></div><div class="healthitem"><span>MTM / Rollover</span><strong id="mtmHealth">--</strong></div><div', 1)
v3_summary = '''<div class="section"><div class="sectionhead"><h2 data-i18n="v3Title">V3 · Bağımsız strateji hesapları</h2><span class="muted small" data-i18n="v3Note">Master'dan ayrı · 3 × 10.000 TRY başlangıç</span></div><div class="grid v3summary"><div class="stat"><div class="label" data-i18n="v3Total">V3 toplam equity</div><div class="value" id="totalEquity">--</div></div><div class="stat"><div class="label" data-i18n="totalPnl">Toplam K/Z</div><div class="value" id="totalPnl">--</div></div><div class="stat"><div class="label" data-i18n="return">Getiri</div><div class="value" id="totalReturn">--</div></div><div class="stat"><div class="label" data-i18n="positions">Açık pozisyon</div><div class="value" id="totalPositions">--</div></div></div></div>'''
html = html.replace('<div class="section"><h2 data-i18n="strategyAccounts">', v3_summary + '<div class="section"><h2 data-i18n="strategyAccounts">', 1)
start = html.index('<div class="section"><h2 data-i18n="modules">')
end = html.index('<div class="section"><h2 data-i18n="activeSignals">', start)
html = html[:start] + '<div class="section"><h2 data-i18n="modules">ZİTAR Zeka Modülleri</h2><div class="modules" id="moduleCards"></div></div>' + html[end:]
html = html.replace("    document.getElementById('systemState').textContent = 'MONITORING';\n    document.getElementById('systemState').className = 'green';", '')
html = html.replace("    const response = await fetch('/api/dashboard', {cache:'no-store'});", "    const response = await fetch('/api/dashboard', {cache:'no-store',signal:AbortSignal.timeout(18000)});\n    if(!response.ok)throw Error('V3 veri servisi '+response.status);")
html = html.replace("    const d = await response.json();", "    const d = await response.json();\n    latestV3=d; renderMarkets();", 1)
html = html.replace("async function refresh(){\n  try {", "let v3Busy=false,latestV3=null;\nasync function refresh(){\n  if(v3Busy)return;v3Busy=true;\n  try {")
html = html.replace("    document.getElementById('status').className = 'value red';\n  }\n}", "    document.getElementById('status').className = 'value red';\n    document.getElementById('apiHealth').textContent='V3 BAĞLANTISI YOK';\n    document.getElementById('apiHealth').className='red';\n  } finally {v3Busy=false}\n}")
# Escape legacy string interpolation at the data boundary while preserving numbers.
html = html.replace('    latestV3=d; renderMarkets();', '    latestV3=d; renderMarkets();\n    sanitizeLegacy(d);')
html = html.replace("async function apiJson(url){const r=await fetch(url,{cache:'no-store'});", "async function apiJson(url){const r=await fetch(url,{cache:'no-store',signal:AbortSignal.timeout(18000)});")
html = html.replace("function showView(v){", "function legacyShowView(v){")
html = html.replace('applyLang();setInterval(refresh,5000);', '')
html = html.replace('</style>', '''
.sectionhead{display:flex;justify-content:space-between;align-items:center;gap:12px}.small{font-size:12px}.v3summary{margin-top:0}.nav .active{border-color:var(--blue);background:#172942}.module button{margin-top:12px}.module .badge{font-size:10px;padding:5px 7px}.detail-panel{margin-top:14px}.detail-row{padding:12px;border-bottom:1px solid var(--line);overflow-wrap:anywhere}.detail-row h4{margin:0 0 8px}.detail-row p{font-size:13px;line-height:1.65;margin:6px 0}.filedetail{white-space:pre-wrap;overflow-wrap:anywhere;max-height:500px;overflow:auto;font:12px/1.65 Consolas,monospace;color:#cbd5e1}.module-list{display:flex;gap:8px;flex-wrap:wrap}.summaryline{font-size:12px;color:var(--muted);line-height:1.7;margin:10px 0}.inline-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.market-filter{padding:10px;border-radius:10px;border:1px solid var(--line);background:#0b1220;color:var(--text);font:inherit;width:270px;max-width:100%;margin:12px 0}.runtime-cards{grid-template-columns:repeat(3,1fr)}.position .positem strong{overflow-wrap:anywhere}.masterpositions{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}#connectionAlert{margin:0 0 12px}#masterStats .value{font-size:20px}.module .modulehead{align-items:flex-start}button:focus-visible,a:focus-visible{outline:2px solid var(--blue);outline-offset:3px}.tablebox{max-height:530px}details>summary{cursor:pointer;color:var(--blue);padding:10px 0}a{color:var(--blue)}
@media(max-width:1100px){.masterpositions,.inline-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.strategies{grid-template-columns:repeat(3,minmax(0,1fr))}.card{padding:12px}.posgrid{grid-template-columns:repeat(2,1fr)}.position-title{flex-wrap:wrap}.metric .v{font-size:14px}}
.hero>*,.tables>*,.grid>*,.strategies>*,.modules>*{min-width:0}.health{grid-template-columns:repeat(2,minmax(0,1fr))}.healthitem{min-width:0;flex-wrap:wrap}.healthitem strong{overflow-wrap:anywhere;max-width:100%}.stat .value{overflow-wrap:anywhere}.modulehead h3{overflow-wrap:anywhere}
@media(max-width:800px){.strategies,.masterpositions,.runtime-cards{grid-template-columns:1fr}.inline-metrics{grid-template-columns:1fr 1fr}.sectionhead{align-items:flex-start;flex-direction:column}}
@media(max-width:650px){.nav{flex-wrap:wrap;overflow:visible}.health{grid-template-columns:1fr}.chat-compose{flex-wrap:wrap}.chat-compose textarea{min-width:0;width:100%}.tables{grid-template-columns:minmax(0,1fr)}.hero{grid-template-columns:minmax(0,1fr)}}
</style>''', 1)

views = '''
<div id="masterView" style="display:none"><div class="section"><div class="sectionhead"><h2 data-i18n="masterTitle">Master · Ana paper portföy</h2><span class="badge green">PAPER ONLY</span></div><div class="grid" id="masterStats"></div><div class="section"><h2 data-i18n="masterPositions">Master pozisyonları</h2><div class="masterpositions" id="masterPositions"></div></div><div class="section"><h2 data-i18n="masterEvents">Master olayları</h2><div class="tablebox" id="masterEvents"></div></div><div class="section"><h2 data-i18n="rollover">Günlük muhasebe / Rollover</h2><div class="tablebox" id="dailyArchive"></div></div></div></div>
<div id="marketsView" style="display:none"><div class="section"><h2 data-i18n="marketTitle">Piyasalar · V3 pozisyonlarının canlı fiyatları</h2><p class="summaryline" data-i18n="marketNote">V3'te açık pozisyon taşıyan pariteler. Kaynak: mevcut Control Center'ın public bookTicker görünümü.</p><input class="market-filter" id="marketFilter" aria-label="Parite filtrele" placeholder="Parite ara · BTC, ETH…"><div class="tablebox" id="marketTable"></div></div></div>
<div id="experimentsView" style="display:none"><div class="section"><h2 data-i18n="experimentsTitle">Deneyler ve regression kayıtları</h2><p class="summaryline" data-i18n="experimentsNote">Kaydedilmiş test sonuçları; bu ekran testleri veya paper işlemleri tetiklemez. Tarihler kayıt zamanıdır.</p><div class="modules" id="experimentCards"></div></div></div>
<div id="systemView" style="display:none"><div class="section"><h2 data-i18n="systemTitle">Sistem · Runtime ve pipeline</h2><div class="grid" id="pipelineStats"></div><div class="section"><div class="tables"><div><h2 data-i18n="runtimeSteps">Runtime adımları</h2><div class="tablebox" id="runtimeSteps"></div></div><div><h2 data-i18n="lastErrors">Son hatalar</h2><div class="tablebox" id="runtimeErrors"></div></div></div></div><div class="section"><h2 data-i18n="services">Bağlı servisler</h2><div class="modules" id="serviceCards"></div></div><div class="section"><h2 data-i18n="memoryTitle">Memory → Learning → Research → Evidence</h2><div class="modules" id="memoryCards"></div></div></div></div>
<div id="moduleDetailView" style="display:none"><div class="section"><button class="btn" id="backModule" data-i18n="back">← Geri</button><div class="panel detail-panel"><h2 id="moduleTitle"></h2><div id="moduleInfo" class="summaryline"></div><div id="moduleContent"></div></div></div></div>
'''
html = html.replace('<div class="footer">', views + '<div class="footer">', 1)
extra = (root / 'control_ui_extra.js').read_text(encoding='utf-8')
html = html.replace('</script>', extra + '\n</script>', 1)
html = html.replace('JSON.stringify({question:q,use_qwen:true})', 'JSON.stringify({question:q,use_qwen:true,session_id:zitarSession})')
html = html.replace('</body>', '<script>' + (root / 'unified_chat_ui.js').read_text(encoding='utf-8') + '</script></body>')
for old, new in {'Grounded Research Conversation': 'Sohbet ve hafıza', '5016: --': 'Ortak Chat: --', "'5016: '+(h.ok?'ONLINE':'ERROR')+' · '+String(h.symbols||0)+' symbols'": "'Ortak Chat: '+(h.ok?'BAĞLI':'HATA')", "'5016: OFFLINE'": "'Ortak Chat: BAĞLANTI YOK'", 'Deterministic evidence is authoritative. Qwen is narration-only. Failed semantic validation falls back to canonical evidence. No execution authority, no real orders, no V3 write.': 'Sohbet yanıtları ZİTAR model profiliyle oluşturulur. Sohbet geçmişi saklanır; model yanıtları doğrulanmış öğrenme sayılmaz. Finans kayıtları ayrı sunulur. Gerçek işlem yetkisi yoktur.'}.items():
    html = html.replace(old, new)
html = html.replace("addChat('zitar',d.answer||'Cevap yok.');", "addChat('zitar',d.answer||'Cevap yok.'); if(d.council_job_id) watchCouncil(d.council_job_id);")
html = html.replace('</body>','<script>'+(root/'council_ui.js').read_text(encoding='utf-8')+'</script></body>')
html = html.replace('</body>','<script>'+(root/'team_dashboard.js').read_text(encoding='utf-8-sig')+'</script></body>')
# Explicit record age; connectivity never implies freshness.
html = html.replace('Cross-Timeframe Research Memory', 'Piyasa analiz hafızası')
html = html.replace('DATA CONFIDENCE', 'KAYITTAKİ VERİ KALİTESİ')
html = html.replace("'5012: '+(h.status||'UNKNOWN')+' · chain '+(h.chain_valid?'OK':'FAIL')", "'Servis: '+(h.status||'UNKNOWN')+' · Kayıt zinciri: '+(h.chain_valid?'tutarlı':'hatalı')+' · Güncellik göstergesi değildir'")
html = html.replace('<div class="value">Piyasa analiz hafızası</div>', '<div class="value">Piyasa analiz hafızası</div><p id="researchFreshness" role="status" style="color:#ffbf47;line-height:1.6">Kayıt tarihi kontrol ediliyor; güncellik doğrulanmadı.</p>')
html = html.replace("    document.getElementById('rShort').textContent=ctxObs(c,'SHORT');", "\n    const stamp=latest.source_generated_utc||latest.observed_utc;\n    const parsed=stamp?Date.parse(stamp):NaN;\n    const age=Date.now()-parsed;\n    const freshness=document.getElementById('researchFreshness');\n    freshness.textContent=Number.isFinite(parsed)&&age>=0?\n      'Analiz üretim zamanı: '+new Date(parsed).toLocaleString('tr-TR',{timeZone:'Europe/Istanbul'})+' (İstanbul) · Kayıt yaşı: '+Math.floor(age/3600000)+' saat '+Math.floor(age%3600000/60000)+' dakika. '+(age>86400000?'Eski kayıt (24 saatten eski). ':'')+'Canlı piyasa güncelliği doğrulanmadı. Veri kalitesi etiketi bu kayda aittir.':\n      'Geçerli analiz tarihi bulunamadı. Veri güncelliği bilinmiyor.';\n    document.getElementById('rShort').textContent=ctxObs(c,'SHORT');")
html = html.replace("    console.error('Research error',e);", "    document.getElementById('researchFreshness').textContent='Veri alınamadı. Görünen önceki kayıt güncel kabul edilmemeli.';\n    console.error('Research error',e);")
html = html.replace('async function loadResearch(){', "function researchLabel(v){return ({UP:'Yukarı yönlü',DOWN:'Aşağı yönlü',MIXED:'Karışık / net yön yok',HIGH:'Yüksek',MEDIUM:'Orta',LOW:'Düşük',OK:'Yeterli örnek',LIMITED:'Sınırlı örnek',INSUFFICIENT:'Yetersiz veri',MISSING:'Veri yok',INITIAL_OBSERVATION:'İlk kayıt',NO_MEANINGFUL_CHANGE:'Anlamlı yön değişimi yok'})[v]||v||'Bilinmiyor';}\nfunction researchDate(v){const n=typeof v==='number'?v:Date.parse(v);return Number.isFinite(n)?new Date(n).toLocaleString('tr-TR',{timeZone:'Europe/Istanbul'})+' İstanbul':'Tarih kaydedilmemiş';}\nfunction renderResearchExplanation(d,m,latest){\n const box=document.getElementById('researchExplanation');box.replaceChildren();\n const p=t=>{const e=document.createElement('p');e.textContent=t;box.appendChild(e);};\n p('Sonuç: '+d.symbol+' için kısa vade '+researchLabel(ctxObs(m.contexts,'SHORT')).toLowerCase()+', orta vade '+researchLabel(ctxObs(m.contexts,'MEDIUM')).toLowerCase()+', uzun vade '+researchLabel(ctxObs(m.contexts,'LONG')).toLowerCase()+'. Bunlar kayıtlı mumlardan hesaplanan gözlemlerdir.');\n const conflicts=m.explicit_conflicts||[];\n p(conflicts.length?'Uyuşmazlık: '+conflicts.map(x=>x.timeframe_a+' '+researchLabel(x.observation_a)+'; '+x.timeframe_b+' '+researchLabel(x.observation_b)).join(' | ')+'. Zaman dilimleri aynı yönde değil.':'Kayıtta açık yukarı/aşağı yön çatışması bulunmuyor; bu tek başına alım veya satım gerekçesi değildir.');\n const change=latest.change_from_previous||{},fields=change.changed_fields||[];\n p('Hafızaya kaydedilen değişim: '+(d.memory_versions<2?'Bu parite için yalnız ilk kayıt var; önceki kayıtla karşılaştırma yapılamıyor.':fields.length?fields.map(x=>(x.field||'Gösterge')+': '+JSON.stringify(x.old??x.before??null)+' → '+JSON.stringify(x.new??x.after??null)).join(' | '):'Gösterge veya kaynak ayrıntıları yenilenmiş olabilir; özet yön alanlarında değişim kaydı yok.'));\n const times=(m.evidence||[]).filter(x=>!x.last_open_time_ms).length;\n p('Veri kapsamı: '+(m.evidence||[]).length+' zaman dilimi. '+times+' zaman diliminde son mum tarihi eksik. Aşağıdaki zamanlar mumun açılış zamanıdır; kapanmış veya kesintisiz veri garantisi değildir.');\n const r=d.refresh_status;\n p(r?'Otomatik analiz: '+({UPDATED:'Son döngü tamamlandı',ERROR:'Son döngü hata verdi',RUNNING:'Çalışıyor',NOT_RUN:'Henüz çalışmadı'})[r.state]+' · Son başarılı çalışma: '+researchDate(r.last_success_utc)+' · Kontrol aralığı: 15 dakika.'+(r.error?' Hata: '+r.error:''):'Otomatik döngü durumu API’de henüz yok; servis yeni kodla başlatılmalı.');\n p('Bu panelin öğrendiği şey, kaydedilmiş piyasa gözlemleri ve aralarındaki farklardır. Model eğitimi veya kanıtlanmış strateji iyileşmesi göstermez. “Kayıtları yenile” yeni veri indirmez; son analiz kaydını ekrana getirir.');\n}\n\nasync function loadResearch(){")
html = html.replace('↻ Yenile / Refresh', '↻ Kayıtları yenile')
html = html.replace('Evidence / Provenance', 'Göstergeler ve veri kaynakları')
html = html.replace('Ne değişti? / What changed?', 'Kayıt geçmişi · ne değişti?')
html = html.replace('Explicit Conflicts', 'Zaman dilimleri arasındaki uyuşmazlıklar')
html = html.replace('Research Integrity', 'Bu analizin sınırları')
html = html.replace('MEMORY VERSION', 'HAFIZA SÜRÜMÜ')
html = html.replace('CONFLICTS', 'UYUŞMAZLIK SAYISI')
html = html.replace('AGREEMENT', 'YÖNLER ARASINDA UYUM')
html = html.replace('SHORT · 1M–30M', 'KISA VADE · 1dk–30dk')
html = html.replace('MEDIUM · 1H–4H', 'ORTA VADE · 1sa–4sa')
html = html.replace('LONG · 1D–1W', 'UZUN VADE · 1g–1hft')
html = html.replace('MONTHLY · AUX', 'AYLIK · EK BAĞLAM')
html = html.replace('<span id="researchApiStatus"', '<span id="researchApiStatus"')
html = html.replace('<div class="value">Piyasa analiz hafızası</div>', '<div class="value">Piyasa analiz hafızası</div><div id="researchExplanation" style="line-height:1.7;max-width:1100px"></div>')
html = html.replace('    const conflicts=m.explicit_conflicts||[];', "    renderResearchExplanation(d,m,latest);\n    ['rShort','rMedium','rLong','rMonthly','rAgree','rConfidence'].forEach(id=>{const e=document.getElementById(id);e.textContent=researchLabel(e.textContent);});\n    const conflicts=m.explicit_conflicts||[];")
html = html.replace('${esc(x.trend)} · RSI', '${esc(researchLabel(x.trend))} · RSI')
html = html.replace('${esc(x.source)} · quality=${esc(x.quality)} · n=${esc(x.candle_count)}', 'Kaynak: ${esc(x.source)} · ${esc(researchLabel(x.quality))} · ${esc(x.candle_count)} mum<br>Son mum açılışı: ${esc(researchDate(x.last_open_time_ms))}')
html = html.replace("${esc(ch.change_type||'--')}", '${esc(researchLabel(ch.change_type))}')
html = html.replace("${esc(x.observed_utc||'')}", '${esc(researchDate(x.observed_utc))}')
html = html.replace("UP:'Yukarı yönlü'", "CHANGED:'Özet gözlemler değişti',EVIDENCE_REFRESH:'Kaynaklar yenilendi; özet aynı',overall:'Genel görünüm',short:'Kısa vade',medium:'Orta vade',long:'Uzun vade',monthly:'Aylık',agreement:'Yön uyumu',confidence:'Veri kalitesi',positive_momentum:'Pozitif momentum görülen dönemler',negative_momentum:'Negatif momentum görülen dönemler',high_volume:'Yüksek hacimli dönemler',high_volatility:'Yüksek oynaklıklı dönemler',conflicts:'Yön uyuşmazlıkları',UP:'Yukarı yönlü'")
html = html.replace('function researchDate(v)', "function researchValue(v){if(Array.isArray(v))return v.length?v.map(x=>typeof x==='object'?x.timeframe_a+' '+researchLabel(x.observation_a)+' / '+x.timeframe_b+' '+researchLabel(x.observation_b):researchLabel(x)).join(', '):'Yok';return researchLabel(v);}\nfunction researchDate(v)")
html = html.replace("(x.field||'Gösterge')+': '+JSON.stringify(x.old??x.before??null)+' → '+JSON.stringify(x.new??x.after??null)", "researchLabel(x.field)+': '+researchValue(x.before)+' → '+researchValue(x.after)")
html = html.replace(".map(y=>y.field).join(', ')", ".map(y=>researchLabel(y.field)).join(', ')")
html = html.replace('SHORT · 1m–30m', 'KISA VADE · 1dk–30dk')
html = html.replace('MEDIUM · 1h–4h', 'ORTA VADE · 1sa–4sa')
html = html.replace('LONG · 1d–1w', 'UZUN VADE · 1g–1hft')
html = html.replace('Açık UP/DOWN çatışması yok.', 'Açık yukarı/aşağı yön çatışması yok.')
html = html.replace('Bu ekran betimleyici araştırmadır. BUY/SELL sinyali değildir. HIGH confidence yalnızca veri kalitesini ifade eder. Aylık 1M bağlam çekirdek agreement hesabına dahil edilmez. Eski hafıza sürümleri overwrite edilmez.', 'Bu ekran piyasa gözlemlerini açıklar; alım/satım sinyali üretmez. Yüksek veri kalitesi, fiyatın yükseleceği veya verinin güncel olduğu anlamına gelmez. Aylık gözlem ek bağlamdır; ana yön uyumu hesabına katılmaz. Önceki hafıza kayıtları korunur.')
html = html.replace('</body>', '<script>'+(root/'trade_context_ui.js').read_text(encoding='utf-8-sig')+'</script></body>')
html = html.replace('</body>', '<script>'+(root/'candidate_monitor_ui.js').read_text(encoding='utf-8-sig')+'</script></body>')
html = html.replace('</body>', '<script>'+(root/'futures_paper_ui.js').read_text(encoding='utf-8-sig')+'</script></body>').replace('FUTURES: KAPALI','VADELİ GERÇEK EMİR: KAPALI')
html = html.replace('</head>', '<style id="paper-card-layout">.paper-accounts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;align-items:start;margin-top:18px}.paper-accounts .card{min-width:0}.paper-accounts .posgrid{grid-template-columns:repeat(3,minmax(0,1fr))}.paper-accounts .positem strong{overflow-wrap:anywhere}.paper-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:16px 0}.paper-summary .stat{min-width:0}.paper-accounts h4{margin:14px 0 8px}.paper-accounts details{font-size:12px}.paper-accounts .position-title{flex-wrap:wrap}.paper-accounts p{line-height:1.5}@media(max-width:1100px){.paper-accounts{grid-template-columns:repeat(2,minmax(0,1fr))}.paper-summary{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:680px){.paper-accounts{grid-template-columns:1fr}.paper-accounts .posgrid{grid-template-columns:repeat(2,minmax(0,1fr))}}</style>'+'</head>')
html = html.replace('</body>', '<script>'+(root/'paper_home_ui.js').read_text(encoding='utf-8-sig')+'</script></body>')
html = html.replace('</body>', '<script>'+(root/'market_discovery_ui.js').read_text(encoding='utf-8-sig')+'</script></body>')
html = html.replace('</body>', '<script>'+(root/'spot_home_ui.js').read_text(encoding='utf-8-sig')+'</script></body>')
html = html.replace('</body>', '<script>'+(root/'confluence_ui.js').read_text(encoding='utf-8-sig')+'</script></body>')
html = html.replace('</body>', '<script>'+(root/'pivot_atr_ui.js').read_text(encoding='utf-8-sig')+'</script></body>')
html = html.replace('</body>', '<script>'+(root/'rsi_pages_ui.js').read_text(encoding='utf-8-sig')+'</script></body>')
html = html.replace('</body>', '<script>'+(root/'voice_controls_ui.js').read_text(encoding='utf-8-sig')+'</script></body>')
html = html.replace('</body>', '<script>'+(root/'simple_navigation_ui.js').read_text(encoding='utf-8-sig')+'</script></body>')
html = html.replace('</body>', '<script>'+(root/'api_connections_ui.js').read_text(encoding='utf-8-sig')+'</script></body>')
html = html.replace('</body>', '<script>'+(root/'indicator_lab_ui.js').read_text(encoding='utf-8')+'</script></body>')
html = html.replace('</body>', '<script>'+(root/'paper_reset_ui.js').read_text(encoding='utf-8')+'</script></body>')
html = html.replace('</body>', '<script>'+(root/'research_experiment_ui.js').read_text(encoding='utf-8-sig')+'</script></body>')
html = html.replace('</body>', '<script>'+(root/'learning_progress_ui.js').read_text(encoding='utf-8-sig')+'</script></body>')
html = html.replace('</body>', '<script>'+(root/'momentum_experiment_ui.js').read_text(encoding='utf-8-sig')+'</script></body>')
html = html.replace('</body>', '<script>'+(root/'rsi_timeframes_ui.js').read_text(encoding='utf-8-sig')+'</script></body>')
html = html.replace('</body>', '<script>'+(root/'rsi_repair_ui.js').read_text(encoding='utf-8-sig')+'</script></body>')
html = html.replace('</body>', '<script>'+(root/'bollinger_pair_ui.js').read_text(encoding='utf-8-sig')+'</script></body>')
html = html.replace('</body>', '<script>'+(root/'pa_v1_ui.js').read_text(encoding='utf-8-sig')+'</script></body>')
(root / 'stage/zitar_full_paper_dashboard_v1.html').write_text(html, encoding='utf-8')
print('Built reference-based HTML:', len(html))
