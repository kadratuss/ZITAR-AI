"""Deterministic tools for the future assistant; no IO, eval or shell access."""
from decimal import Decimal, InvalidOperation
import json


def calculate(operation, operands):
    if operation not in ('add', 'subtract', 'multiply', 'divide'):
        raise ValueError('UNKNOWN_OPERATION')
    if not isinstance(operands, list) or not 2 <= len(operands) <= 50:
        raise ValueError('INVALID_OPERANDS')
    try:
        values = [Decimal(str(v)) for v in operands]
    except InvalidOperation as exc:
        raise ValueError('INVALID_NUMBER') from exc
    if any(not v.is_finite() or len(str(v)) > 100 for v in values):
        raise ValueError('INVALID_NUMBER')
    result = values[0]
    for value in values[1:]:
        if operation == 'add': result += value
        elif operation == 'subtract': result -= value
        elif operation == 'multiply': result *= value
        elif value == 0: raise ValueError('DIVISION_BY_ZERO')
        else: result /= value
    if not result.is_finite(): raise ValueError('NONFINITE_RESULT')
    return {'tool': 'calculate', 'result': str(result), 'executed': True}


def validate_json(text):
    if not isinstance(text, str) or len(text) > 100000:
        raise ValueError('INVALID_INPUT_SIZE')
    def invalid_constant(value): raise ValueError('NONFINITE_JSON')
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise ValueError('DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    value = json.loads(text, parse_constant=invalid_constant,
                       object_pairs_hook=unique_pairs)
    return {'tool': 'validate_json', 'valid': True,
            'root_type': type(value).__name__, 'executed': True}
