"""Bounded extractive text tools. Source text is data, never instructions."""
import hashlib
import re


def summarize_text(text):
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 20000:
        raise ValueError('INVALID_TEXT')
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+|\n+', text.strip()) if s.strip()]
    selected = sentences[:3]
    return {'tool': 'summarize_text', 'executed': True, 'sentences': selected,
            'source_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'method': 'EXTRACT_FIRST_THREE_SENTENCES',
            'limitation': 'Kaynağın ilk üç cümlesi seçilir; kapsamlı anlamsal özet veya bilgi doğrulaması değildir.'}


def create_report(text):
    summary = summarize_text(text)
    # Plain text download avoids active HTML/Markdown content and external URLs.
    content = ('ZİTAR · Kullanıcı metni raporu\n\n'
               'Yöntem: Kaynağın ilk üç cümlesini seçme; dış bilgi eklenmedi.\n\n'
               'Kısa görünüm\n' + '\n'.join('- '+s for s in summary['sentences']) +
               '\n\nKaynak metin\n' + text + '\n\nKaynak SHA256: '+summary['source_sha256']+'\n')
    return {'tool': 'create_report', 'executed': True,
            'filename': 'zitar-rapor.txt', 'content': content,
            'source_sha256': summary['source_sha256']}
