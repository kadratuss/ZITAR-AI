"""Bounded HTTPS reader: connect only to a validated public IP, including redirects."""
import hashlib
import http.client
import ipaddress
import socket
import ssl
from datetime import datetime, timezone
from urllib.parse import urlsplit, urljoin
from zitar_web_research_v1 import VisibleText

class PublicHTTPS(http.client.HTTPSConnection):
    def connect(self):
        addresses = socket.getaddrinfo(self.host, 443, type=socket.SOCK_STREAM)
        ips = list(dict.fromkeys(a[4][0] for a in addresses))
        if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
            raise ValueError('NON_PUBLIC_ADDRESS')
        # Pin the address validated above; TLS still verifies the original hostname.
        raw = socket.create_connection((ips[0],443), self.timeout)
        try:
            self.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise

def validate_url(url):
    p = urlsplit(url)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.port not in (443,None):
        raise ValueError('PUBLIC_HTTPS_REQUIRED')
    return p

def read_page(url):
    original = url
    for _ in range(4):
        p = validate_url(url)
        connection = PublicHTTPS(p.hostname, timeout=8)
        try:
            path = p.path or '/'
            if p.query: path += '?' + p.query
            connection.request('GET', path, headers={'User-Agent':'ZITAR-Research/1.0','Accept':'text/html,text/plain'})
            response = connection.getresponse()
            if response.status in (301,302,303,307,308):
                url = urljoin(url, response.getheader('Location',''))
                continue
            if response.status != 200:
                raise ValueError('HTTP_'+str(response.status))
            content_type = response.getheader('Content-Type','')
            if not any(t in content_type for t in ('text/html','text/plain')):
                raise ValueError('UNSUPPORTED_CONTENT_TYPE')
            raw = response.read(1_000_001)
            if len(raw) > 1_000_000: raise ValueError('PAGE_TOO_LARGE')
            parser = VisibleText(); parser.feed(raw.decode('utf-8',errors='replace'))
            text = ' '.join(' '.join(parser.parts).split())
            if len(text) < 150: raise ValueError('INSUFFICIENT_PAGE_TEXT')
            return dict(url=original, final_url=url, text=text[:18000],
                        sha256=hashlib.sha256(raw).hexdigest(),
                        retrieved_utc=datetime.now(timezone.utc).isoformat(),
                        publication_date=None, status='READ_NOT_VERIFIED')
        finally:
            connection.close()
    raise ValueError('TOO_MANY_REDIRECTS')
