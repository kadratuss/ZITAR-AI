"""Narrow natural-language arithmetic planner; plans are untrusted data."""
import re
from collections import Counter
from decimal import Decimal


def candidate(question):
    from assistant_foundation.chat_tools import normalized
    q = normalized(question)
    # Documents, research and quoted instructions never select this tool.
    if any(word in q for word in ('belge', 'ozetle', 'rapor', 'arastir', 'talimat', 'http', '```')):
        return False
    if len(re.findall(r'\d+(?:[.,]\d+)?', q)) < 2:
        return False
    return any(word in q for word in ('kac', 'hesap', 'toplam', 'kaldi', 'kalan', 'carp', 'bol', 'cikar'))


def model_plan(question):
    from zitar_model_provider_v1 import chat
    return chat([
        {'role': 'system', 'content': 'Only translate this arithmetic question into a JSON object. Return exactly {"expression":"..."} using numbers in the question and + - * / parentheses. Never compute the answer. If ambiguous return {"clarify":true}. No other tools or commands. Example: 7 boxes with 12 pencils each, 9 used -> {"expression":"7*12-9"}.'},
        {'role': 'user', 'content': question}
    ], role='tool_planner', json_mode=True, temperature=0, max_tokens=100)


def route(base, session, question, planner=None):
    if not candidate(question): return None
    from assistant_foundation.chat_tools import expression, handle
    try:
        plan = (planner or model_plan)(question)
        if not isinstance(plan, dict) or set(plan) != {'expression'}:
            raise ValueError('INVALID_PLAN')
        text = plan['expression']
        if not isinstance(text, str) or len(text) > 300:
            raise ValueError('INVALID_PLAN')
        supplied = Counter(Decimal(x.replace(',', '.')) for x in re.findall(r'\d+(?:[.,]\d+)?', question))
        proposed = Counter(Decimal(x.replace(',', '.')) for x in re.findall(r'\d+(?:[.,]\d+)?', text))
        if not proposed or any(count > supplied.get(value, 0) for value, count in proposed.items()):
            raise ValueError('UNSUPPORTED_NUMBERS')
        expression(text)  # Validate grammar, finite numbers and zero division.
        result = handle(base, session, 'Hesapla: '+text)
        result.update(route='NATURAL_CALCULATION', planner='LOCAL_MODEL_UNVERIFIED_INTERPRETATION',
                      tool_expression=text, question=question)
        result['answer'] += '\nKullandığım hesap: '+text+'\nSorunun yorumunu kontrol et; hesap ifadesi doğruysa sonuç geçerlidir.'
        return result
    except (ValueError, TypeError, SyntaxError, ArithmeticError, OSError, TimeoutError):
        return dict(route='TOOL_CLARIFICATION', source='TOOL_PLANNER', grounded=False,
                    tool_status='PLAN_NOT_VERIFIED', answer='Hesap ifadesini güvenilir biçimde çıkaramadım. Sayıları ve işlemi netleştir veya “Hesapla: 7 * 12 - 9” biçimini kullan.')
