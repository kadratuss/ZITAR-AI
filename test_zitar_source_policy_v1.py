import unittest

from zitar_source_policy_v1 import (
    PRIMARY,
    INDEPENDENT,
    REJECTED,
    classify_source,
    corroboration_allowed,
)


class SourcePolicyTests(unittest.TestCase):

    def test_binance_research_source_is_primary(self):
        result = classify_source(
            "https://www.binance.tr/tr/support/faq/example"
        )
        self.assertEqual(result["role"], PRIMARY)
        self.assertEqual(result["provider_family"], "BINANCE")

    def test_binance_family_is_not_independent(self):
        primary = classify_source(
            "https://www.binance.tr/tr/support/faq/example"
        )
        other = classify_source(
            "https://academy.binance.com/en/article/example"
        )

        self.assertEqual(other["role"], PRIMARY)
        self.assertFalse(corroboration_allowed(primary, other))

    def test_unknown_source_fails_closed(self):
        result = classify_source(
            "https://random-example.invalid/article/test"
        )
        self.assertEqual(result["role"], REJECTED)
        self.assertEqual(result["reason"], "SOURCE_NOT_IN_POLICY")

    def test_non_https_rejected(self):
        result = classify_source(
            "http://www.binance.tr/tr/support/faq/example"
        )
        self.assertEqual(result["role"], REJECTED)

    def test_account_and_trade_paths_rejected(self):
        for url in (
            "https://www.binance.tr/tr/my/dashboard",
            "https://www.binance.com/en/trade/BTC_USDT",
            "https://www.binance.com/en/account/settings",
        ):
            self.assertEqual(
                classify_source(url)["role"],
                REJECTED,
                url,
            )

    def test_explicit_independent_provider_allowed(self):
        policy = {
            "research.example.org": "RESEARCH_EXAMPLE"
        }

        primary = classify_source(
            "https://www.binance.tr/tr/support/faq/example"
        )

        independent = classify_source(
            "https://research.example.org/article/market-costs",
            independent_hosts=policy,
        )

        self.assertEqual(independent["role"], INDEPENDENT)
        self.assertTrue(
            corroboration_allowed(primary, independent)
        )

    def test_same_family_cannot_corroborate(self):
        primary = {
            "role": PRIMARY,
            "provider_family": "BINANCE",
        }

        independent = {
            "role": INDEPENDENT,
            "provider_family": "BINANCE",
        }

        self.assertFalse(
            corroboration_allowed(primary, independent)
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

class RealProviderPolicyTests(unittest.TestCase):

    def test_real_independent_provider_families(self):
        cases = {
            "https://www.investor.gov/introduction-investing/investing-basics/glossary/ask-price": "SEC",
            "https://www.cmegroup.com/education/articles-and-reports/how-traders-measure-liquidity": "CME_GROUP",
            "https://www.finra.org/investors/insights/example": "FINRA",
        }

        for url, family in cases.items():
            result = classify_source(url)
            self.assertEqual(result["role"], INDEPENDENT)
            self.assertEqual(result["provider_family"], family)

    def test_real_independent_families_corroborate_binance_family(self):
        primary = classify_source(
            "https://www.binance.tr/tr/support/faq/example"
        )

        for url in (
            "https://www.investor.gov/introduction-investing/investing-basics/glossary/ask-price",
            "https://www.cmegroup.com/education/articles-and-reports/how-traders-measure-liquidity",
            "https://www.finra.org/investors/insights/example",
        ):
            independent = classify_source(url)
            self.assertTrue(
                corroboration_allowed(primary, independent),
                url,
            )

    def test_binance_academy_still_cannot_be_independent(self):
        primary = classify_source(
            "https://www.binance.tr/tr/support/faq/example"
        )
        academy = classify_source(
            "https://academy.binance.com/en/article/example"
        )

        self.assertEqual(academy["provider_family"], "BINANCE")
        self.assertEqual(academy["role"], PRIMARY)
        self.assertFalse(corroboration_allowed(primary, academy))
