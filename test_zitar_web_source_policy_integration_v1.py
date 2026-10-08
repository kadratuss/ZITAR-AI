import json
from pathlib import Path
import tempfile
import unittest

from zitar_web_research_v1 import research


class WebSourcePolicyIntegrationTests(unittest.TestCase):

    def test_final_url_policy_and_snapshot_provenance(self):
        def fetch(url, hosts):
            if "bing.com" in url:
                return (
                    b"<rss><channel></channel></rss>",
                    "<rss><channel></channel></rss>",
                    {},
                    url,
                )

            html = "<html><body><p>" + ("public evidence " * 40) + "</p></body></html>"
            raw = html.encode("utf-8")

            return (
                raw,
                html,
                {},
                "https://www.binance.tr/tr/support/faq/example",
            )

        job = {
            "id": "policy-integration",
            "topic": "Policy integration test",
            "public_query_authorized": True,
            "public_query": "controlled public evidence",
            "allowed_hosts": ["www.binance.tr"],
            "seed_urls": ["https://www.binance.tr/tr/support/faq/start"],
        }

        with tempfile.TemporaryDirectory() as root:
            cache = Path(root)

            result = research(job, cache, fetch)

            self.assertEqual(len(result["sources"]), 1)
            source = result["sources"][0]

            self.assertEqual(source["status"], "FETCHED_NOT_FACT_CHECKED")
            self.assertEqual(source["final_url"],
                             "https://www.binance.tr/tr/support/faq/example")
            self.assertEqual(source["role"], "PRIMARY")
            self.assertEqual(source["provider_family"], "BINANCE")
            self.assertEqual(source["policy_reason"],
                             "APPROVED_PRIMARY_PROVIDER")

            snapshot = json.loads(
                (cache / source["snapshot"]).read_text(encoding="utf-8")
            )

            self.assertEqual(snapshot["role"], "PRIMARY")
            self.assertEqual(snapshot["provider_family"], "BINANCE")
            self.assertEqual(snapshot["policy_reason"],
                             "APPROVED_PRIMARY_PROVIDER")
            self.assertEqual(snapshot["final_url"],
                             "https://www.binance.tr/tr/support/faq/example")

            self.assertEqual(result["verified_claims"], [])
            self.assertFalse(result["learning_ready"])
            self.assertFalse(result["execution_authority"])

    def test_rejected_final_url_fails_closed(self):
        def fetch(url, hosts):
            if "bing.com" in url:
                return (
                    b"<rss><channel></channel></rss>",
                    "<rss><channel></channel></rss>",
                    {},
                    url,
                )

            html = "<html><body><p>" + ("public evidence " * 40) + "</p></body></html>"

            return (
                html.encode("utf-8"),
                html,
                {},
                "https://random-example.invalid/article/test",
            )

        job = {
            "id": "policy-rejection",
            "topic": "Policy rejection test",
            "public_query_authorized": True,
            "public_query": "controlled public evidence",
            "allowed_hosts": ["www.binance.tr"],
            "seed_urls": ["https://www.binance.tr/tr/support/faq/start"],
        }

        with tempfile.TemporaryDirectory() as root:
            cache = Path(root)

            result = research(job, cache, fetch)

            self.assertEqual(len(result["sources"]), 1)
            source = result["sources"][0]

            self.assertEqual(source["status"], "ERROR")
            self.assertIn("SOURCE_POLICY_REJECTED", source["error"])
            self.assertIn("SOURCE_NOT_IN_POLICY", source["error"])

            self.assertEqual(list(cache.glob("*.json")), [])
            self.assertEqual(result["verified_claims"], [])
            self.assertFalse(result["learning_ready"])
            self.assertFalse(result["execution_authority"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
