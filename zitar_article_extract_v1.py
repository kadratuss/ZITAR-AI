"""Decode official embedded article data as JSON, never as executable script."""
from html.parser import HTMLParser
import json
import re

class ArticleData(HTMLParser):
    def __init__(self):
        super().__init__();self.capture=False;self.parts=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='script':self.capture=attrs.get('id')=='__APP_DATA' and attrs.get('type')=='application/json'
    def handle_endtag(self,tag):
        if tag=='script':self.capture=False
    def handle_data(self,data):
        if self.capture:self.parts.append(data)

def text_node(node,depth=0):
    if depth>40:raise ValueError('ARTICLE_TOO_DEEP')
    if isinstance(node,list):return ''.join(text_node(x,depth+1) for x in node)
    if not isinstance(node,dict):return ''
    kind=node.get('id','');cfg=node.get('config',{})
    if kind=='RichTextText':return cfg.get('content','') if isinstance(cfg.get('content'),str) else ''
    if kind=='RichTextTable':
        return '\n'.join(' | '.join(text_node(row.get(key,{}),depth+1) for key in cfg.get('header',[])) for row in cfg.get('data',[]))+'\n'
    if kind.startswith('RichText'):
        return text_node(cfg.get('content',[]),depth+1)+ ('\n' if kind in ('RichTextParagraph','RichTextListItem') else '')
    return ''

def extract_article(html):
    parser=ArticleData();parser.feed(html)
    if not parser.parts:return None
    app=json.loads(''.join(parser.parts))
    article=app.get('routeProps',{}).get('bbcd',{}).get('article')
    if not isinstance(article,dict) or not article.get('body'):return None
    body=json.loads(article['body'])
    layout,nodes=body.get('layout',{}),body.get('hash',{})
    seen=set()
    def walk(key):
        if key in seen:raise ValueError('ARTICLE_LAYOUT_CYCLE')
        seen.add(key)
        return text_node(nodes.get(key,{}))+''.join(walk(child) for child in layout.get(key,[]))
    text=''.join(walk(key) for key in layout.get('root',[])).strip()
    if len(text)<100:raise ValueError('ARTICLE_BODY_INCOMPLETE')
    return {'text':re.sub(r'[ \t]+',' ',text),'title':article.get('title'),
            'article_code':article.get('articleCode'),'released_time_ms':article.get('releasedTime'),
            'extraction':'OFFICIAL_EMBEDDED_ARTICLE_JSON'}
