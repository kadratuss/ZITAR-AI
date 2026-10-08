"""Public web discovery for chat. Snippets are not verified facts or live quotes."""
import re
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from zitar_web_research_v1 import fetch, VisibleText

def norm(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold().replace('ı','i')) if not unicodedata.combining(c))

FOLLOWUPS = {'sen arastir','arastir','sen incele','incele','peki ya o',
             'guncel durum','devam et','et o zaman','o zaman arastir',
             'tamam arastir','arastir o zaman','evet arastir','et ozaman'}
SMALLTALK = {'selam','merhaba','nasilsin','tesekkurler','sag ol','tamam','hey','selamlar','gunaydin','iyi aksamlar','iyi geceler','naber','ne haber','sagol','ordamisiniz','burada misin'}

def is_request(q):
    return bool(re.search(r'\b(arastir\w*|incele\w*|kaynak|guncel|borsa\w*|hisse\w*|fiyat\w*|piyasa\w*)\b',q)
                or re.search(r'\S+\s+(durumu|durumda|nasil gidiyor)\b',q))

def resolve(question, turns):
    q = norm(question).strip(' .!?')
    if q in SMALLTALK:
        return None
    if re.search(r'\b(espri|espiri|saka|mizah)\b',q) and not re.search(r'\b(arastir\w*|incele\w*|kaynak)\b',q):
        return None
    followup = q in FOLLOWUPS
    if followup:
        for turn in reversed(turns[-12:]):
            if turn.get('search_query'):
                return turn['search_query']
            previous = turn.get('question', '').strip()
            normalized = norm(previous).strip(' .!?')
            if normalized in FOLLOWUPS:
                continue
            if normalized in SMALLTALK:
                return ''
            if previous:
                return previous if is_request(normalized) or len(previous.split()) <= 3 else ''
        return ''
    explicit = is_request(q)
    # A short reply to an instrument clarification supplies the requested subject.
    clarification = bool(turns and turns[-1].get('route') == 'CLARIFICATION' and len(question.split()) <= 5)
    if explicit or clarification:
        return question.strip()
    return None

def search(query, fetcher=fetch):
    url = 'https://www.bing.com/search?' + urllib.parse.urlencode({'format':'rss','q':query[:300]})
    checked = datetime.now(timezone.utc).isoformat()
    try:
        _, xml, _, _ = fetcher(url, {'www.bing.com'})
        root = ET.fromstring(xml)
        sources = []
        stop = {'durumu','nedir','nasil','arastir','hissesini','hissesi','bist','borsa','borsasinda','guncel','fiyati','fiyat','sen','ve','icin','market','information','official','stock','investor','relations'}
        terms = set(re.findall(r'\w+', norm(query))) - stop
        rejected = 0
        for item in root.findall('.//item')[:5]:
            link = item.findtext('link') or ''
            if urllib.parse.urlsplit(link).scheme not in ('https','http'):
                continue
            parser = VisibleText(); parser.feed(item.findtext('description') or '')
            searchable = set(re.findall(r'\w+', norm((item.findtext('title') or '')+' '+link+' '+' '.join(parser.parts))))
            dialogue = 'conversational' in terms and 'dialogue' in terms
            relevant = bool(terms & searchable)
            if dialogue:
                relevant = bool(searchable & {'conversational','dialogue','chatbot','chatbots'}) and bool(searchable & {'ai','evaluation','research','model','models','memory','humor','context'})
            if not terms or not relevant:
                rejected += 1
                continue
            sources.append(dict(title=item.findtext('title') or link, url=link,
                                snippet=' '.join(parser.parts)[:700]))
        return dict(query=query, checked_utc=checked, sources=sources,
                    status='DISCOVERY_ONLY' if sources else 'NO_RELEVANT_RESULTS', rejected_count=rejected, verified=False)
    except Exception as exc:
        return dict(query=query, checked_utc=checked, sources=[], status='ERROR',
                    error=type(exc).__name__+': '+str(exc), verified=False)

def render(result):
    if result['status'] == 'ERROR':
        return 'Web aramasını denedim ancak kaynak erişimi başarısız oldu: '+result['error']
    if not result['sources']:
        return 'Web aramasında sonuç bulamadım. Şirketin tam adı, borsası veya işlem koduyla aramayı netleştirebiliriz.'
    lines = [f"{result['query']} için web kaynakları aradım (arama zamanı: {result['checked_utc']}).",
             'Aşağıdakiler arama sonuçlarıdır; içerikleri henüz doğrulanmadı ve canlı fiyat olarak kullanılamaz.']
    for source in result['sources']:
        lines.extend(['', source['title'], source['url'], source['snippet']])
    return '\n'.join(lines)
