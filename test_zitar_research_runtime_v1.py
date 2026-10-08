import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from decimal import Decimal
from unittest.mock import patch
import zitar_research_runtime_v1 as r


def fixture():
    statement = 'This is a controlled test statement.'
    sources = [dict(role=role, provider=host,url='https://'+host+'/test',snapshot_text=statement,
                    content_sha256=hashlib.sha256(statement.encode()).hexdigest(),http_status=200,error=None)
               for role,host in [('PRIMARY','primary.example'),('INDEPENDENT','secondary.example')]]
    ev = dict(question='Controlled test?',sources=sources,candidate_claims=[{'claim':statement}],
              learning_candidate_ready=True,corroborated=True,
              authorities={'real_order':False,'silent_code_rewrite':False,'memory_write':False})
    ev['bundle_sha256']=r.sha(ev)
    c = dict(domain='TEST',question=ev['question'],claims=ev['candidate_claims'],
             evidence_bundle_sha256=ev['bundle_sha256'],status='VALIDATED_CANDIDATE',
             next_required_stage='CONTROLLED_LEARNING_JOURNAL_WRITE',
             authorities={'real_order':False,'silent_code_rewrite':False,'persistent_memory_write':False},
             source_provenance=[{k:s[k] for k in ('role','provider','url','content_sha256')} for s in sources])
    c['candidate_sha256']=r.sha(c)
    return c,ev


class ResearchTests(unittest.TestCase):
    def test_automatic_web_schedule_persists_and_avoids_repeat(self):
        with tempfile.TemporaryDirectory() as root:
            base=Path(root)
            (base/'zitar_research_automation_v1.json').write_text(json.dumps({'web_enabled':True,'web_job':{'id':'test'}}))
            response={'checked_utc':r.stamp(),'status':'EVIDENCE_COLLECTED','sources':[]}
            with patch('zitar_web_research_v1.research',return_value=response) as call:
                first=r.web_cycle(base); second=r.web_cycle(base)
                self.assertEqual(call.call_count,1)
                self.assertEqual(len(second['history']),1)
                self.assertEqual(second['refresh_seconds'],21600)

    def test_legacy_single_web_job_remains_supported(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            config = {
                'web_enabled': True,
                'web_job': {'id': 'legacy-primary'}
            }
            (base/'zitar_research_automation_v1.json').write_text(
                json.dumps(config), encoding='utf-8'
            )
            response = {
                'job_id': 'legacy-primary',
                'checked_utc': r.stamp(),
                'status': 'EVIDENCE_COLLECTED',
                'sources': []
            }
            with patch('zitar_web_research_v1.research',
                       return_value=response) as call:
                result = r.web_cycle(base)

            self.assertEqual(call.call_count, 1)
            self.assertEqual(result['status'], 'EVIDENCE_COLLECTED')
            self.assertEqual(result['job_id'], 'legacy-primary')

    def test_multiple_web_jobs_run_separately_and_are_aggregated(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            config = {
                'web_enabled': True,
                'web_jobs': [
                    {'id': 'primary', 'research_role': 'PRIMARY'},
                    {'id': 'independent', 'research_role': 'INDEPENDENT'},
                ]
            }
            (base/'zitar_research_automation_v1.json').write_text(
                json.dumps(config), encoding='utf-8'
            )

            def fake_research(job, cache):
                return {
                    'job_id': job['id'],
                    'checked_utc': r.stamp(),
                    'status': 'EVIDENCE_COLLECTED',
                    'sources': [{
                        'url': 'https://example.com/' + job['id'],
                        'status': 'FETCHED_NOT_FACT_CHECKED',
                        'response_sha256': job['id'] + '-hash',
                    }],
                    'learning_ready': False,
                }

            with patch('zitar_web_research_v1.research',
                       side_effect=fake_research) as call:
                result = r.web_cycle(base)

            self.assertEqual(call.call_count, 2)
            self.assertEqual(result['status'], 'EVIDENCE_COLLECTED')
            self.assertEqual(
                [j['job_id'] for j in result['jobs']],
                ['primary', 'independent']
            )
            self.assertEqual(len(result['sources']), 2)
            self.assertFalse(result['learning_ready'])

    def test_tampered_candidate_rejected(self):
        c,e=fixture(); c['domain']='CHANGED'
        with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'): r.verify_candidate(c,e)

    def test_tampered_evidence_rejected(self):
        c,e=fixture(); e['question']='changed'
        with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'): r.verify_candidate(c,e)

    def test_source_bytes_and_claim_support_required(self):
        for changed, expected in [('changed text','SOURCE_CONTENT_HASH'),('', 'SOURCE_SNAPSHOT')]:
            c,e=fixture(); e['sources'][0]['snapshot_text']=changed
            e.pop('bundle_sha256'); e['bundle_sha256']=r.sha(e)
            c['evidence_bundle_sha256']=e['bundle_sha256']; c.pop('candidate_sha256'); c['candidate_sha256']=r.sha(c)
            with self.assertRaisesRegex(ValueError,expected): r.verify_candidate(c,e)

    def test_unsupported_claim_rejected_even_rehashed(self):
        c,e=fixture(); e['candidate_claims']=[{'claim':'Unsupported conclusion.'}]
        e.pop('bundle_sha256'); e['bundle_sha256']=r.sha(e)
        c['claims']=e['candidate_claims']; c['evidence_bundle_sha256']=e['bundle_sha256']
        c.pop('candidate_sha256'); c['candidate_sha256']=r.sha(c)
        with self.assertRaisesRegex(ValueError,'CLAIM_LITERAL'): r.verify_candidate(c,e)

    def test_write_restart_duplicate_and_recall(self):
        with tempfile.TemporaryDirectory() as root:
            base=Path(root); c,e=fixture()
            self.assertEqual(r.promote(base,c,e),'RECORDED')
            first=(base/'zitar_core_learning_journal_v1.jsonl').read_bytes()
            self.assertEqual(r.promote(base,c,e),'ALREADY_RECORDED_NOT_REVALIDATED')
            self.assertEqual(first,(base/'zitar_core_learning_journal_v1.jsonl').read_bytes())
            records=r.rows(base/'zitar_core_learning_journal_v1.jsonl'); r.check_chain(records)
            self.assertEqual(records[0]['claims'],c['claims'])

    def test_failed_replace_preserves_journal(self):
        with tempfile.TemporaryDirectory() as root:
            base=Path(root); path=base/'zitar_core_learning_journal_v1.jsonl'; path.write_bytes(b'')
            c,e=fixture()
            with patch.object(r.os,'replace',side_effect=OSError('simulated failure')):
                with self.assertRaises(OSError): r.promote(base,c,e)
            self.assertEqual(path.read_bytes(),b'')
            self.assertEqual(r.promote(base,c,e),'RECORDED')

    def test_cost_formula_against_cash_flows(self):
        model=r.cost_model('.001','.001'); budget=Decimal('1000'); p=Decimal('100')
        q=budget/(p*Decimal('1.001')*Decimal('1.001'))
        proceeds=q*p*Decimal('.999')*Decimal('.999')
        loss=(budget-proceeds)/budget*100
        self.assertLess(abs(loss-Decimal(model['flat_reference_roundtrip_loss_pct'])),Decimal('1e-20'))
        rise=Decimal(model['reference_breakeven_rise_pct'])/100
        self.assertLess(abs(proceeds*(1+rise)-budget),Decimal('1e-20'))
        self.assertEqual(Decimal(r.cost_model(0,0)['flat_reference_roundtrip_loss_pct']),0)
        with self.assertRaises(ValueError): r.cost_model('NaN',0)

    def test_trade_costs_separate_spread_slippage_and_fee(self):
        trade=dict(trade_id='one',strategy='TEST',side='BUY',quantity='2',reference_price='101',
                   modeled_fill_price='102',fee_try='1',observed_bid='99',observed_ask='101')
        result=r.trade_costs([trade])['strategies']['TEST']
        self.assertEqual(result['modeled_slippage_try'],'2')
        self.assertEqual(result['spread_vs_mid_try'],'2')
        self.assertEqual(result['fee_try'],'1')
        with self.assertRaises(ValueError): r.trade_costs([trade,trade])

    def test_real_snapshot_two_cycles_idempotent(self):
        project=Path(r'C:\Users\pars_\Documents\PortfolioAI-Backend')
        names=['zitar_core_project_memory_v1.jsonl','zitar_core_learning_journal_v1.jsonl',
               'zitar_core_knowledge_gap_v1.jsonl','zitar_core_learning_candidate_v1.json',
               'zitar_core_real_research_evidence_v1.json','zitar_master_portfolio_v1.json',
               'zitar_master_paper_engine_v1.py','zitar_liquidity_profile_v1.json']
        with tempfile.TemporaryDirectory() as root:
            base=Path(root)
            for name in names: shutil.copy2(project/name,base/name)
            before=r.rows(base/'zitar_core_learning_journal_v1.jsonl')
            first=r.cycle(base); once=(base/'zitar_core_learning_journal_v1.jsonl').read_bytes()
            second=r.cycle(base)
            self.assertEqual(once,(base/'zitar_core_learning_journal_v1.jsonl').read_bytes())
            self.assertEqual(len(second['history']),len(first['history']))
            self.assertTrue(all(not j['evidence_sufficient'] for j in second['jobs']))
            after=r.rows(base/'zitar_core_learning_journal_v1.jsonl')
            self.assertEqual(after[:len(before)],before); r.check_chain(after)


if __name__=='__main__': unittest.main(verbosity=2)

# ---------------------------------------------------------------------------
# Provider-family corroboration gate tests
# ---------------------------------------------------------------------------

def family_fixture(independent_family='SEC'):
    c, e = fixture()

    e['source_policy_schema'] = 'ZITAR_SOURCE_POLICY_V1'

    e['sources'][0]['provider_family'] = 'BINANCE'
    e['sources'][0]['policy_reason'] = 'APPROVED_PRIMARY_PROVIDER'

    e['sources'][1]['provider_family'] = independent_family
    e['sources'][1]['policy_reason'] = 'APPROVED_INDEPENDENT_PROVIDER'

    e.pop('bundle_sha256')
    e['bundle_sha256'] = r.sha(e)

    c['evidence_bundle_sha256'] = e['bundle_sha256']

    c['source_provenance'] = [
        {
            'role': s['role'],
            'provider': s['provider'],
            'url': s['url'],
            'content_sha256': s['content_sha256'],
            'provider_family': s['provider_family'],
            'policy_reason': s['policy_reason'],
        }
        for s in e['sources']
    ]

    c.pop('candidate_sha256')
    c['candidate_sha256'] = r.sha(c)

    return c, e


class ProviderFamilyResearchTests(unittest.TestCase):

    def test_different_provider_families_allowed(self):
        c, e = family_fixture('SEC')
        self.assertTrue(r.verify_candidate(c, e))

    def test_same_provider_family_rejected(self):
        c, e = family_fixture('BINANCE')
        with self.assertRaisesRegex(ValueError, 'INDEPENDENT_PROVIDER_FAMILY_REQUIRED'):
            r.verify_candidate(c, e)

    def test_missing_provider_family_rejected_for_policy_v1(self):
        c, e = family_fixture('SEC')

        del e['sources'][1]['provider_family']

        e.pop('bundle_sha256')
        e['bundle_sha256'] = r.sha(e)

        c['evidence_bundle_sha256'] = e['bundle_sha256']
        c['source_provenance'][1].pop('provider_family')

        c.pop('candidate_sha256')
        c['candidate_sha256'] = r.sha(c)

        with self.assertRaisesRegex(ValueError, 'SOURCE_PROVIDER_FAMILY_REQUIRED'):
            r.verify_candidate(c, e)

    def test_policy_v1_provenance_tampering_rejected(self):
        c, e = family_fixture('SEC')

        c['source_provenance'][1]['provider_family'] = 'FINRA'

        c.pop('candidate_sha256')
        c['candidate_sha256'] = r.sha(c)

        with self.assertRaisesRegex(ValueError, 'PROVENANCE_MISMATCH'):
            r.verify_candidate(c, e)

    def test_legacy_fixture_remains_valid(self):
        c, e = fixture()
        self.assertNotIn('source_policy_schema', e)
        self.assertTrue(r.verify_candidate(c, e))

class WebClaimCorroborationTests(unittest.TestCase):

    def _source(self, role, family, text, url):
        return {
            'role': role,
            'provider_family': family,
            'policy_reason': (
                'APPROVED_PRIMARY_PROVIDER'
                if role == 'PRIMARY'
                else 'APPROVED_INDEPENDENT_PROVIDER'
            ),
            'url': url,
            'final_url': url,
            'status': 'FETCHED_NOT_FACT_CHECKED',
            'snapshot_text': text,
            'content_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
            'http_status': 200,
            'error': None,
        }

    def test_literal_claim_supported_by_different_families(self):
        claim = 'Bid-ask spread is a trading cost.'
        sources = [
            self._source(
                'PRIMARY', 'BINANCE',
                'Exchange information. ' + claim,
                'https://www.binance.tr/tr/support/faq/test'
            ),
            self._source(
                'INDEPENDENT', 'SEC',
                'Investor information. ' + claim,
                'https://www.investor.gov/test'
            ),
        ]

        result = r.corroborate_web_claim(claim, sources)

        self.assertTrue(result['corroborated'])
        self.assertEqual(result['status'], 'CORROBORATED')
        self.assertEqual(
            set(result['provider_families']),
            {'BINANCE', 'SEC'}
        )

    def test_same_provider_family_cannot_corroborate(self):
        claim = 'Bid-ask spread is a trading cost.'
        sources = [
            self._source(
                'PRIMARY', 'BINANCE', claim,
                'https://www.binance.tr/tr/support/faq/test'
            ),
            self._source(
                'INDEPENDENT', 'BINANCE', claim,
                'https://academy.binance.com/en/article/test'
            ),
        ]

        result = r.corroborate_web_claim(claim, sources)

        self.assertFalse(result['corroborated'])
        self.assertEqual(
            result['status'],
            'INDEPENDENT_PROVIDER_FAMILY_REQUIRED'
        )

    def test_primary_only_literal_support_is_not_enough(self):
        claim = 'Bid-ask spread is a trading cost.'
        sources = [
            self._source(
                'PRIMARY', 'BINANCE', claim,
                'https://www.binance.tr/tr/support/faq/test'
            ),
            self._source(
                'INDEPENDENT', 'SEC',
                'Different statement.',
                'https://www.investor.gov/test'
            ),
        ]

        result = r.corroborate_web_claim(claim, sources)

        self.assertFalse(result['corroborated'])
        self.assertEqual(
            result['status'],
            'INDEPENDENT_LITERAL_SUPPORT_REQUIRED'
        )

    def test_tampered_snapshot_is_rejected(self):
        claim = 'Bid-ask spread is a trading cost.'
        sources = [
            self._source(
                'PRIMARY', 'BINANCE', claim,
                'https://www.binance.tr/tr/support/faq/test'
            ),
            self._source(
                'INDEPENDENT', 'FINRA', claim,
                'https://www.finra.org/investors/test'
            ),
        ]

        sources[1]['snapshot_text'] = claim + ' tampered'

        with self.assertRaisesRegex(
            ValueError,
            'SOURCE_CONTENT_HASH_MISMATCH'
        ):
            r.corroborate_web_claim(claim, sources)

class WebSnapshotAdapterTests(unittest.TestCase):

    def test_load_web_snapshot_source_verifies_and_adapts_cache(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            cache = base / 'zitar_web_evidence_cache_v1'
            cache.mkdir()

            text = 'Bid-ask spread is a trading cost.'
            text_sha = hashlib.sha256(text.encode('utf-8')).hexdigest()

            snapshot = {
                'url': 'https://www.investor.gov/test',
                'final_url': 'https://www.investor.gov/test',
                'retrieved_utc': r.stamp(),
                'response_sha256': 'a' * 64,
                'text_sha256': text_sha,
                'role': 'INDEPENDENT',
                'provider_family': 'SEC',
                'policy_reason': 'APPROVED_INDEPENDENT_PROVIDER',
                'extraction': 'STATIC_VISIBLE_TEXT',
                'article_metadata': None,
                'text': text,
                'last_modified': None,
                'content_date_status': 'HTTP_HEADER_ONLY_NOT_VERIFIED_PUBLICATION_DATE',
            }

            name = 'test-snapshot.json'
            (cache / name).write_text(
                json.dumps(snapshot),
                encoding='utf-8'
            )

            web_source = {
                'url': snapshot['url'],
                'final_url': snapshot['final_url'],
                'status': 'FETCHED_NOT_FACT_CHECKED',
                'response_sha256': snapshot['response_sha256'],
                'snapshot': name,
                'role': 'INDEPENDENT',
                'provider_family': 'SEC',
                'policy_reason': 'APPROVED_INDEPENDENT_PROVIDER',
            }

            adapted = r.load_web_snapshot_source(base, web_source)

            self.assertEqual(adapted['snapshot_text'], text)
            self.assertEqual(adapted['content_sha256'], text_sha)
            self.assertEqual(adapted['role'], 'INDEPENDENT')
            self.assertEqual(adapted['provider_family'], 'SEC')
            self.assertEqual(
                adapted['policy_reason'],
                'APPROVED_INDEPENDENT_PROVIDER'
            )
            self.assertEqual(adapted['http_status'], 200)
            self.assertIsNone(adapted['error'])

    def test_load_web_snapshot_source_rejects_text_tampering(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            cache = base / 'zitar_web_evidence_cache_v1'
            cache.mkdir()

            original = 'Original evidence text.'

            snapshot = {
                'url': 'https://www.finra.org/test',
                'final_url': 'https://www.finra.org/test',
                'response_sha256': 'b' * 64,
                'text_sha256': hashlib.sha256(
                    original.encode('utf-8')
                ).hexdigest(),
                'role': 'INDEPENDENT',
                'provider_family': 'FINRA',
                'policy_reason': 'APPROVED_INDEPENDENT_PROVIDER',
                'text': 'Tampered evidence text.',
            }

            name = 'tampered.json'
            (cache / name).write_text(
                json.dumps(snapshot),
                encoding='utf-8'
            )

            web_source = {
                'url': snapshot['url'],
                'final_url': snapshot['final_url'],
                'status': 'FETCHED_NOT_FACT_CHECKED',
                'response_sha256': snapshot['response_sha256'],
                'snapshot': name,
                'role': 'INDEPENDENT',
                'provider_family': 'FINRA',
                'policy_reason': 'APPROVED_INDEPENDENT_PROVIDER',
            }

            with self.assertRaisesRegex(
                ValueError,
                'SNAPSHOT_TEXT_HASH_MISMATCH'
            ):
                r.load_web_snapshot_source(base, web_source)

    def test_load_web_snapshot_source_rejects_provenance_mismatch(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            cache = base / 'zitar_web_evidence_cache_v1'
            cache.mkdir()

            text = 'Evidence.'
            snapshot = {
                'url': 'https://www.investor.gov/test',
                'final_url': 'https://www.investor.gov/test',
                'response_sha256': 'c' * 64,
                'text_sha256': hashlib.sha256(
                    text.encode('utf-8')
                ).hexdigest(),
                'role': 'INDEPENDENT',
                'provider_family': 'SEC',
                'policy_reason': 'APPROVED_INDEPENDENT_PROVIDER',
                'text': text,
            }

            name = 'provenance.json'
            (cache / name).write_text(
                json.dumps(snapshot),
                encoding='utf-8'
            )

            web_source = {
                'url': snapshot['url'],
                'final_url': snapshot['final_url'],
                'status': 'FETCHED_NOT_FACT_CHECKED',
                'response_sha256': snapshot['response_sha256'],
                'snapshot': name,
                'role': 'INDEPENDENT',
                'provider_family': 'FINRA',
                'policy_reason': 'APPROVED_INDEPENDENT_PROVIDER',
            }

            with self.assertRaisesRegex(
                ValueError,
                'SNAPSHOT_PROVENANCE_MISMATCH'
            ):
                r.load_web_snapshot_source(base, web_source)
import unittest
import zitar_research_runtime_v1 as r


class WebControlledClaimExtractionTests(unittest.TestCase):

    def test_extract_general_market_structure_claims(self):
        text = (
            'The bid price will almost always be lower than the ask or “offer,” price. '
            'The difference between the bid price and the ask price is called the "spread."'
        )

        claims = r.extract_controlled_web_claims(
            text=text,
            provider_family="SEC",
            role="INDEPENDENT",
        )

        self.assertTrue(claims)
        self.assertTrue(
            any(c.get("claim_class") == "GENERAL_MARKET_STRUCTURE"
                for c in claims)
        )

        for claim in claims:
            self.assertIn(claim["claim"], text)
            self.assertEqual(claim["provider_family"], "SEC")
            self.assertEqual(claim["role"], "INDEPENDENT")


    def test_extract_exchange_specific_claims(self):
        text = (
            "Belirtilen bu komisyon oranına %20 KDV dahil olup "
            "herhangi bir ek ücret uygulanmamaktadır."
        )

        claims = r.extract_controlled_web_claims(
            text=text,
            provider_family="BINANCE",
            role="PRIMARY",
        )

        self.assertTrue(claims)
        self.assertTrue(
            any(c.get("claim_class") == "EXCHANGE_SPECIFIC"
                for c in claims)
        )

        for claim in claims:
            self.assertIn(claim["claim"], text)


    def test_no_model_generated_cross_domain_inference(self):
        text = (
            "The difference between the bid price and the ask price "
            'is called the "spread."'
        )

        claims = r.extract_controlled_web_claims(
            text=text,
            provider_family="SEC",
            role="INDEPENDENT",
        )

        forbidden = {
            "Spread is a trading cost.",
            "Spread is a liquidity cost.",
            "Lower liquidity causes higher trading costs.",
        }

        extracted = {c["claim"] for c in claims}

        self.assertTrue(extracted.isdisjoint(forbidden))


    def test_unknown_family_fails_closed(self):
        with self.assertRaisesRegex(
            ValueError,
            "UNAPPROVED_PROVIDER_FAMILY"
        ):
            r.extract_controlled_web_claims(
                text="Some market statement.",
                provider_family="UNKNOWN",
                role="INDEPENDENT",
            )


    def test_empty_text_produces_no_claims(self):
        claims = r.extract_controlled_web_claims(
            text="",
            provider_family="SEC",
            role="INDEPENDENT",
        )

        self.assertEqual(claims, [])


    def test_claim_must_be_literal_source_text(self):
        text = (
            "They're also subject to bid-ask spreads, which represent "
            "the difference between the highest price a buyer will pay "
            "and the lowest price at which a seller will sell shares."
        )

        claims = r.extract_controlled_web_claims(
            text=text,
            provider_family="FINRA",
            role="INDEPENDENT",
        )

        self.assertTrue(claims)

        for claim in claims:
            self.assertIn(claim["claim"], text)
            self.assertFalse(claim.get("inferred", True))


if __name__ == "__main__":
    unittest.main()
import unittest
import zitar_research_runtime_v1 as r


class WebClaimQualityGateTests(unittest.TestCase):

    def test_rejects_navigation_noise(self):
        bad = (
            "gov Main navigation Introduction to Investing Getting Started "
            "Understanding Fees Asset Allocation and Diversification"
        )
        self.assertFalse(
            r.web_claim_quality_allowed(
                bad,
                claim_class="GENERAL_MARKET_STRUCTURE"
            )
        )


    def test_accepts_sec_spread_definition(self):
        claim = (
            'The difference between the bid price and the ask price '
            'is called the "spread."'
        )
        self.assertTrue(
            r.web_claim_quality_allowed(
                claim,
                claim_class="GENERAL_MARKET_STRUCTURE"
            )
        )


    def test_accepts_finra_bid_ask_definition(self):
        claim = (
            "They're also subject to bid-ask spreads, which represent "
            "the difference between the highest price a buyer will pay "
            "and the lowest price at which a seller will sell shares "
            "of a stock at any given time."
        )
        self.assertTrue(
            r.web_claim_quality_allowed(
                claim,
                claim_class="GENERAL_MARKET_STRUCTURE"
            )
        )


    def test_accepts_binance_exchange_specific_statement(self):
        claim = (
            "Belirtilen bu komisyon oranına %20 KDV dahil olup "
            "herhangi bir ek ücret uygulanmamaktadır."
        )
        self.assertTrue(
            r.web_claim_quality_allowed(
                claim,
                claim_class="EXCHANGE_SPECIFIC"
            )
        )


    def test_rejects_heading_fragment(self):
        self.assertFalse(
            r.web_claim_quality_allowed(
                "Komisyon Seviyesi ?",
                claim_class="EXCHANGE_SPECIFIC"
            )
        )


    def test_rejects_broken_numeric_fragment(self):
        self.assertFalse(
            r.web_claim_quality_allowed(
                "Bronz (Standart) seviyesi Piyasa Alıcı komisyon oranı %0.",
                claim_class="EXCHANGE_SPECIFIC"
            )
        )


    def test_rejects_truncated_quote_fragment(self):
        self.assertFalse(
            r.web_claim_quality_allowed(
                'The difference between the bid price and the ask price '
                'is called the "spread.',
                claim_class="GENERAL_MARKET_STRUCTURE"
            )
        )


    def test_rejects_unknown_claim_class(self):
        with self.assertRaisesRegex(
            ValueError,
            "UNKNOWN_CLAIM_CLASS"
        ):
            r.web_claim_quality_allowed(
                "Some statement.",
                claim_class="CROSS_DOMAIN_INFERENCE"
            )


if __name__ == "__main__":
    unittest.main()
import hashlib
import unittest
import zitar_research_runtime_v1 as r


class WebControlledPipelineTests(unittest.TestCase):

    def _source(self, role, family, text):
        return {
            "role": role,
            "provider_family": family,
            "policy_reason": (
                "APPROVED_PRIMARY_PROVIDER"
                if role == "PRIMARY"
                else "APPROVED_INDEPENDENT_PROVIDER"
            ),
            "url": "https://example.invalid/" + family.lower(),
            "snapshot_text": text,
            "content_sha256": hashlib.sha256(
                text.encode("utf-8")
            ).hexdigest(),
            "http_status": 200,
            "status": "FETCHED_NOT_FACT_CHECKED",
            "error": None,
        }

    def test_pipeline_filters_noise(self):
        sources = [
            self._source(
                "INDEPENDENT",
                "SEC",
                'Main navigation Understanding Fees '
                'The difference between the bid price and the ask price '
                'is called the "spread."'
            )
        ]

        result = r.controlled_web_claim_pipeline(sources)

        self.assertTrue(result["claims"])

        for claim in result["claims"]:
            self.assertTrue(
                r.web_claim_quality_allowed(
                    claim["claim"],
                    claim["claim_class"]
                )
            )

    def test_pipeline_never_marks_single_family_corroborated(self):
        text = (
            'The difference between the bid price and the ask price '
            'is called the "spread."'
        )

        result = r.controlled_web_claim_pipeline([
            self._source("INDEPENDENT", "SEC", text)
        ])

        self.assertFalse(result["corroborated"])
        self.assertFalse(result["learning_ready"])

    def test_pipeline_same_family_cannot_corroborate(self):
        claim = "Controlled identical market statement about bid ask spread."

        result = r.controlled_web_claim_pipeline([
            self._source("PRIMARY", "BINANCE", claim),
            self._source("INDEPENDENT", "BINANCE", claim),
        ])

        self.assertFalse(result["corroborated"])
        self.assertFalse(result["learning_ready"])

    def test_pipeline_different_families_literal_match_can_corroborate(self):
        claim = (
            "The bid ask spread is the difference between the bid "
            "price and the ask price."
        )

        result = r.controlled_web_claim_pipeline([
            self._source("PRIMARY", "BINANCE", claim),
            self._source("INDEPENDENT", "SEC", claim),
        ])

        self.assertTrue(result["corroborated"])
        self.assertTrue(result["verified_claims"])
        self.assertTrue(result["learning_ready"])

    def test_pipeline_produces_no_inferred_claims(self):
        sec = (
            'The difference between the bid price and the ask price '
            'is called the "spread."'
        )
        finra = (
            "Liquidity Risk ETPs are exchange-traded, but they do "
            "carry some liquidity risk."
        )

        result = r.controlled_web_claim_pipeline([
            self._source("INDEPENDENT", "SEC", sec),
            self._source("INDEPENDENT", "FINRA", finra),
        ])

        for claim in result["claims"]:
            self.assertFalse(claim.get("inferred", True))

        self.assertFalse(result["learning_ready"])


class WebSemanticCorroborationTests(unittest.TestCase):

    def _source(self, role, family, text):
        return {
            "role": role,
            "provider_family": family,
            "policy_reason": (
                "APPROVED_PRIMARY_PROVIDER"
                if role == "PRIMARY"
                else "APPROVED_INDEPENDENT_PROVIDER"
            ),
            "url": "https://example.invalid/" + family.lower(),
            "snapshot_text": text,
            "content_sha256": hashlib.sha256(
                text.encode("utf-8")
            ).hexdigest(),
            "http_status": 200,
            "status": "FETCHED_NOT_FACT_CHECKED",
            "error": None,
        }

    def test_semantically_equivalent_spread_definitions_match(self):
        primary_text = (
            "The bid ask spread is the difference between "
            "the bid price and the ask price."
        )

        independent_text = (
            "The difference between the bid price and the ask price "
            'is called the "spread."'
        )

        result = r.corroborate_web_claim_semantically(
            primary_text,
            [
                self._source("PRIMARY", "BINANCE", primary_text),
                self._source("INDEPENDENT", "SEC", independent_text),
            ],
        )

        self.assertTrue(result["corroborated"])
        self.assertEqual(
            result["provider_families"],
            ["BINANCE", "SEC"],
        )

    def test_different_concepts_do_not_match(self):
        primary_text = (
            "The bid ask spread is the difference between "
            "the bid price and the ask price."
        )

        independent_text = (
            "Liquidity risk can affect the ability to trade."
        )

        result = r.corroborate_web_claim_semantically(
            primary_text,
            [
                self._source("PRIMARY", "BINANCE", primary_text),
                self._source("INDEPENDENT", "FINRA", independent_text),
            ],
        )

        self.assertFalse(result["corroborated"])

    def test_same_provider_family_cannot_semantically_corroborate(self):
        primary_text = (
            "The bid ask spread is the difference between "
            "the bid price and the ask price."
        )

        independent_text = (
            "The difference between the bid price and the ask price "
            'is called the "spread."'
        )

        result = r.corroborate_web_claim_semantically(
            primary_text,
            [
                self._source("PRIMARY", "BINANCE", primary_text),
                self._source("INDEPENDENT", "BINANCE", independent_text),
            ],
        )

        self.assertFalse(result["corroborated"])

    def test_primary_literal_support_is_still_required(self):
        claim = (
            "The bid ask spread is the difference between "
            "the bid price and the ask price."
        )

        independent_text = (
            "The difference between the bid price and the ask price "
            'is called the "spread."'
        )

        result = r.corroborate_web_claim_semantically(
            claim,
            [
                self._source(
                    "PRIMARY",
                    "BINANCE",
                    "A completely different primary statement.",
                ),
                self._source(
                    "INDEPENDENT",
                    "SEC",
                    independent_text,
                ),
            ],
        )

        self.assertFalse(result["corroborated"])
        self.assertEqual(
            result["status"],
            "PRIMARY_LITERAL_SUPPORT_REQUIRED",
        )

    def test_tampered_semantic_source_is_rejected(self):
        claim = (
            "The bid ask spread is the difference between "
            "the bid price and the ask price."
        )

        independent_text = (
            "The difference between the bid price and the ask price "
            'is called the "spread."'
        )

        source = self._source(
            "INDEPENDENT",
            "SEC",
            independent_text,
        )

        source["snapshot_text"] += " tampered"

        with self.assertRaisesRegex(
            ValueError,
            "SOURCE_CONTENT_HASH_MISMATCH",
        ):
            r.corroborate_web_claim_semantically(
                claim,
                [
                    self._source("PRIMARY", "BINANCE", claim),
                    source,
                ],
            )

    def test_semantic_match_is_deterministic_not_model_inferred(self):
        a = (
            "The bid ask spread is the difference between "
            "the bid price and the ask price."
        )

        b = (
            "The difference between the bid price and the ask price "
            'is called the "spread."'
        )

        first = r.web_claim_semantic_equivalent(a, b)
        second = r.web_claim_semantic_equivalent(a, b)

        self.assertIsInstance(first, bool)
        self.assertEqual(first, second)
        self.assertTrue(first)


if __name__ == "__main__":
    unittest.main()

class WebCycleControlledLearningIntegrationTests(unittest.TestCase):

    def test_apply_controlled_web_learning_builds_verified_result(self):
        claim = (
            "The bid ask spread is the difference between the bid "
            "price and the ask price."
        )

        def source(role, family):
            return {
                "status": "FETCHED_NOT_FACT_CHECKED",
                "role": role,
                "provider_family": family,
                "policy_reason": (
                    "APPROVED_PRIMARY_PROVIDER"
                    if role == "PRIMARY"
                    else "APPROVED_INDEPENDENT_PROVIDER"
                ),
                "url": "https://example.invalid/" + family.lower(),
                "snapshot_text": claim,
                "content_sha256": hashlib.sha256(
                    claim.encode("utf-8")
                ).hexdigest(),
                "http_status": 200,
                "error": None,
            }

        result = r.apply_controlled_web_learning([
            source("PRIMARY", "BINANCE"),
            source("INDEPENDENT", "SEC"),
        ])

        self.assertTrue(result["corroborated"])
        self.assertTrue(result["learning_ready"])
        self.assertTrue(result["verified_claims"])
        self.assertFalse(result["execution_authority"])

    def test_apply_controlled_web_learning_fails_closed_without_corroboration(self):
        text = (
            'The difference between the bid price and the ask price '
            'is called the "spread."'
        )

        source = {
            "status": "FETCHED_NOT_FACT_CHECKED",
            "role": "INDEPENDENT",
            "provider_family": "SEC",
            "policy_reason": "APPROVED_INDEPENDENT_PROVIDER",
            "url": "https://example.invalid/sec",
            "snapshot_text": text,
            "content_sha256": hashlib.sha256(
                text.encode("utf-8")
            ).hexdigest(),
            "http_status": 200,
            "error": None,
        }

        result = r.apply_controlled_web_learning([source])

        self.assertFalse(result["corroborated"])
        self.assertFalse(result["learning_ready"])
        self.assertEqual(result["verified_claims"], [])
        self.assertFalse(result["execution_authority"])

    def test_apply_controlled_web_learning_never_grants_execution_authority(self):
        result = r.apply_controlled_web_learning([])

        self.assertFalse(result["execution_authority"])


if __name__ == "__main__":
    unittest.main()

class WebSemanticPipelineIntegrationTests(unittest.TestCase):

    def _source(self, role, family, text):
        return {
            "status": "FETCHED_NOT_FACT_CHECKED",
            "role": role,
            "provider_family": family,
            "policy_reason": (
                "APPROVED_PRIMARY_PROVIDER"
                if role == "PRIMARY"
                else "APPROVED_INDEPENDENT_PROVIDER"
            ),
            "url": "https://example.invalid/" + family.lower(),
            "snapshot_text": text,
            "content_sha256": hashlib.sha256(
                text.encode("utf-8")
            ).hexdigest(),
            "http_status": 200,
            "error": None,
        }

    def test_pipeline_uses_semantic_fallback_for_market_structure(self):
        primary = (
            "The bid ask spread is the difference between "
            "the bid price and the ask price."
        )

        independent = (
            "The difference between the bid price and the ask price "
            'is called the "spread."'
        )

        result = r.controlled_web_claim_pipeline([
            self._source("PRIMARY", "BINANCE", primary),
            self._source("INDEPENDENT", "SEC", independent),
        ])

        semantic = [
            item
            for item in result["verified_claims"]
            if item.get("corroboration_mode")
            == "DETERMINISTIC_SEMANTIC"
        ]

        self.assertTrue(semantic)
        self.assertTrue(result["corroborated"])
        self.assertTrue(result["learning_ready"])

        for item in semantic:
            self.assertFalse(item.get("inferred", True))
            self.assertFalse(
                item["corroboration"].get("model_inference", True)
            )

    def test_exchange_specific_claim_does_not_use_semantic_fallback(self):
        primary = (
            "Belirtilen bu komisyon oranına %20 KDV dahil olup "
            "herhangi bir ek ücret uygulanmamaktadır."
        )

        independent = (
            "The difference between the bid price and the ask price "
            'is called the "spread."'
        )

        result = r.controlled_web_claim_pipeline([
            self._source("PRIMARY", "BINANCE", primary),
            self._source("INDEPENDENT", "SEC", independent),
        ])

        matched = [
            item
            for item in result["verified_claims"]
            if item.get("claim") == primary
        ]

        self.assertFalse(matched)

    def test_semantic_pipeline_never_grants_execution_authority(self):
        primary = (
            "The bid ask spread is the difference between "
            "the bid price and the ask price."
        )

        independent = (
            "The difference between the bid price and the ask price "
            'is called the "spread."'
        )

        controlled = r.apply_controlled_web_learning([
            self._source("PRIMARY", "BINANCE", primary),
            self._source("INDEPENDENT", "SEC", independent),
        ])

        self.assertFalse(controlled["execution_authority"])


if __name__ == "__main__":
    unittest.main()
