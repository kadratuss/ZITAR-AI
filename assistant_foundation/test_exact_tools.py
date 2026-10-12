import unittest
from assistant_foundation.exact_tools import calculate, validate_json


class ExactToolsTests(unittest.TestCase):
    def test_baseline_problem(self):
        product = calculate('multiply', ['12', '7'])['result']
        self.assertEqual(calculate('subtract', [product, '9'])['result'], '75')

    def test_decimal_money(self):
        self.assertEqual(calculate('add', ['0.1', '0.2'])['result'], '0.3')

    def test_division_zero(self):
        with self.assertRaises(ValueError): calculate('divide', [1, 0])

    def test_nonfinite(self):
        with self.assertRaises(ValueError): calculate('add', ['NaN', 1])

    def test_no_code_execution(self):
        with self.assertRaises(ValueError): calculate('python', [1, 2])

    def test_valid_json(self):
        self.assertEqual(validate_json('{"items":[1,2]}')['root_type'], 'dict')

    def test_duplicate_keys(self):
        with self.assertRaises(ValueError): validate_json('{"a":1,"a":2}')

    def test_json_nonfinite(self):
        with self.assertRaises(ValueError): validate_json('{"a":NaN}')

if __name__ == '__main__': unittest.main()
