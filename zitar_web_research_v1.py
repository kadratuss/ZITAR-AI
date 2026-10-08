"""Scheduled public-source discovery and evidence snapshots; never executes page content."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from zitar_source_policy_v1 import classify_source, REJECTED


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(); self.hidden=0; self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','noscript'): self.hidden+=1
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript') and self.hidden: self.hidden-=1
    def handle_data(self,data):
        if not self.hidden: self.parts.append(data)


def allowed(url, hosts):
    p=urllib.parse.urlsplit(url)
    if p.scheme!='https' or p.hostname not in hosts or p.username or p.password or p.port not in (None,443):
        raise ValueError('SOURCE_NOT_ALLOWLISTED')
    if any(part in p.path.lower().split('/') for part in ('my','account','login','register','trade','trading','wallet','markets')):
        raise ValueError('NON_RESEARCH_PATH')


class CheckedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self,hosts): self.hosts=hosts
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        allowed(newurl,self.hosts)
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def fetch(url,hosts):
    allowed(url,hosts)
    opener=urllib.request.build_opener(CheckedRedirect(hosts))
    request=urllib.request.Request(url,headers={'User-Agent':'ZITAR-Personal-Research/1.0','Accept':'text/html,application/rss+xml,application/xml,text/plain'})
    with opener.open(request,timeout=8) as response:
        raw=response.read(2_000_001)
        if len(raw)>2_000_000: raise ValueError('SOURCE_TOO_LARGE')
        charset=response.headers.get_content_charset() or 'utf-8'
        return raw,raw.decode(charset,errors='replace'),dict(response.headers),response.geturl()


def research(job,cache,fetcher=fetch):
    if job.get('public_query_authorized') is not True:
        raise ValueError('PUBLIC_QUERY_NOT_AUTHORIZED')
    query=job['public_query']
    if not isinstance(query,str) or not 3<=len(query)<=300: raise ValueError('INVALID_QUERY')
    hosts=set(job['allowed_hosts'])
    discovered=[]; errors=[]
    search_url='https://www.bing.com/search?'+urllib.parse.urlencode({'format':'rss','q':query})
    try:
        _,xml,_,_=fetcher(search_url,{'www.bing.com'})
        root=ET.fromstring(xml)
        for item in root.findall('.//item')[:10]:
            url=item.findtext('link') or ''
            try: allowed(url,hosts)
            except ValueError: continue
            if not any(part in urllib.parse.urlsplit(url).path.lower() for part in ('fees','faq','academy','article','support','blog','glossary')):
                continue
            discovered.append({'title':item.findtext('title'),'url':url})
    except Exception as exc:
        errors.append('DISCOVERY:'+str(exc))
    urls=list(dict.fromkeys(job.get('seed_urls',[])+[x['url'] for x in discovered]))[:5]
    cache.mkdir(parents=True,exist_ok=True)
    def one(url):
        try:
            raw,text,headers,final_url=fetcher(url,hosts)
            source_policy=classify_source(final_url)
            if source_policy.get('role') == REJECTED:
                raise ValueError('SOURCE_POLICY_REJECTED:' + str(source_policy.get('reason')))
            from zitar_article_extract_v1 import extract_article
            article=extract_article(text) if urllib.parse.urlsplit(final_url).hostname=='www.binance.tr' else None
            parser=VisibleText(); parser.feed(text)
            visible=re.sub(r'\s+',' ',' '.join(parser.parts)).strip()
            if article: visible=article['title']+'\n'+article['text']
            if len(visible)<200: raise ValueError('INSUFFICIENT_STATIC_TEXT')
            digest=hashlib.sha256(raw).hexdigest()
            path=cache/(digest+('-article-v1' if article else '')+'.json')
            evidence=dict(url=url,final_url=final_url,retrieved_utc=datetime.now(timezone.utc).isoformat(),
                response_sha256=digest,text_sha256=hashlib.sha256(visible.encode()).hexdigest(),
                role=source_policy['role'],provider_family=source_policy['provider_family'],
                policy_reason=source_policy['reason'],
                extraction=article['extraction'] if article else 'STATIC_VISIBLE_TEXT',
                article_metadata={k:v for k,v in article.items() if k!='text'} if article else None,
                text=visible,last_modified=headers.get('Last-Modified'),
                content_date_status='HTTP_HEADER_ONLY_NOT_VERIFIED_PUBLICATION_DATE')
            if not path.exists():
                # Immutable content-addressed snapshots; safe retry after a partial temp write.
                tmp=path.with_suffix('.tmp'); tmp.write_text(json.dumps(evidence,ensure_ascii=False),encoding='utf-8'); tmp.replace(path)
            return dict(url=url,final_url=final_url,status='FETCHED_NOT_FACT_CHECKED',response_sha256=digest,
                        role=source_policy['role'],provider_family=source_policy['provider_family'],
                        policy_reason=source_policy['reason'],
                        retrieved_utc=evidence['retrieved_utc'],snapshot=path.name,text_length=len(visible),
                        last_modified=evidence['last_modified'],extraction=evidence['extraction'],
                        article_title=article.get('title') if article else None,
                        content_warnings=['DYNAMIC_TABLE_NOT_AVAILABLE'] if 'Kayıt bulunamadı' in visible else [])
        except Exception as exc:
            return dict(url=url,status='ERROR',error=str(exc))
    with ThreadPoolExecutor(max_workers=3) as pool: sources=list(pool.map(one,urls))
    success=sum(s['status']=='FETCHED_NOT_FACT_CHECKED' for s in sources)
    complete=success==len(sources) and success>0 and not errors and not any(s.get('content_warnings') for s in sources)
    return dict(job_id=job['id'],topic=job['topic'],public_query=query,
                checked_utc=datetime.now(timezone.utc).isoformat(),sources=sources,discovered=discovered,
                errors=errors,status='EVIDENCE_COLLECTED' if complete else ('PARTIAL_EVIDENCE' if success else 'RETRY_REQUIRED'),
                verified_claims=[],learning_ready=False,
                reason='Retrieved pages are evidence candidates, not automatically corroborated facts.',
                execution_authority=False)
