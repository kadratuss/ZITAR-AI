import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
import numpy as np
from stable_baselines3.common.env_checker import check_env
from test_causal_indicators import rows
from research_environment import TrainScaler
from online_research_pipeline import prepare
from zitar_next.market import HOUR,fetch,parse,get
from zitar_next.futures import IsolatedAccount,FuturesEnv,evaluate
from zitar_next.store import Registry,WorkerLock,init,workspace,digest
from zitar_next.worker import assess,train_round,walk_forward
from zitar_next.finrl_bridge import ZitarWeightStrategy
from zitar_next.dashboard import handler
from zitar_next.paper import tick,vote,approved
from zitar_next.preflight import inspect
from unittest.mock import Mock


def snapshot(market='futures',count=300):
    records = rows([100+np.sin(i/5)*5+i*.03 for i in range(count)])
    for r in records:
        r.update(mark_open=r['open'],mark_high=r['high'],mark_low=r['low'],mark_close=r['close'],funding=[])
    return dict(market=market,interval='1h',records=records,server_time_ms=count*HOUR,closed_before_ms=count*HOUR)


def proposal(eligible=True):
    return dict(market='futures',symbol='BTCUSDT',interval='1h',paper_only=True,real_orders=False,
                eligible=eligible,issues=[] if eligible else ['INSUFFICIENT_EVIDENCE'],version=1)


class NextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = init(Path(self.temp.name)/'next')

    def test_workspace_never_claims_existing_directory(self):
        with self.assertRaises(FileExistsError):
            init(self.root)
        with self.assertRaises(ValueError):
            workspace(self.temp.name)

    def test_human_gate_reject_activate_rollback(self):
        registry = Registry(self.root)
        body = proposal()
        one = registry.propose(body)
        self.assertEqual(one,registry.propose(body))
        with self.assertRaises(ValueError):
            registry.decide(one,'ACTIVATE','no prior approval')
        self.assertEqual(registry.decide(one,'ACCEPT','human test acceptance'),'ACCEPTED')
        self.assertEqual(registry.all()['active'],[])
        registry.decide(one,'ACTIVATE','human paper test activation')
        two = registry.propose(dict(body,version=2))
        registry.decide(two,'ACCEPT','approve fixture v2')
        registry.decide(two,'ACTIVATE','activate fixture v2')
        self.assertEqual(registry.all()['active'][0]['proposal'],two)
        registry.decide(one,'ROLLBACK','return to approved fixture v1')
        self.assertEqual(registry.all()['active'][0]['proposal'],one)

    def test_ineligible_and_rejected_never_activate(self):
        registry = Registry(self.root)
        bad = registry.propose(proposal(False))
        with self.assertRaises(ValueError):
            registry.decide(bad,'ACCEPT','try invalid')
        registry.decide(bad,'REJECT','insufficient evidence')
        for decision in ('ACCEPT','ACTIVATE','ROLLBACK'):
            with self.assertRaises(ValueError):
                registry.decide(bad,decision,'cannot bypass review')

    def test_tamper_requires_new_approval(self):
        registry = Registry(self.root)
        identity = registry.propose(proposal())
        with registry.connect() as db:
            db.execute('UPDATE proposals SET body=? WHERE id=?',(json.dumps(dict(proposal(),version=9)),identity))
        with self.assertRaises(ValueError):
            registry.decide(identity,'ACCEPT','tampered')

    def test_worker_lock_rejects_second_writer(self):
        with WorkerLock(self.root):
            with self.assertRaises(RuntimeError):
                with WorkerLock(self.root):
                    pass
        with WorkerLock(self.root):
            pass

    def test_isolated_loss_does_not_spend_reserve(self):
        account = IsolatedAccount(fee=0,slippage=0)
        account.target(1,100)
        reserve = account.cash
        self.assertAlmostEqual(reserve,9000)
        account.bar(dict(mark_low=1,mark_high=110,mark_close=2,funding=[]))
        self.assertEqual(account.cash,reserve)
        self.assertEqual(account.liquidations,1)
        self.assertIsNone(account.position)

    def test_short_profit_and_funding_sign(self):
        account = IsolatedAccount(fee=0,slippage=0)
        account.target(-1,100)
        account.bar(dict(mark_low=90,mark_high=101,mark_close=90,
                         funding=[dict(markPrice='100',fundingRate='.001')]))
        self.assertAlmostEqual(account.funding_total,3)
        account.close(90)
        self.assertAlmostEqual(account.cash,10303)

    def test_repeated_target_no_fill_and_reversal_two_fills(self):
        account = IsolatedAccount()
        account.target(1,100);account.target(1,101)
        self.assertEqual(account.trades,1)
        account.target(-1,100)
        self.assertEqual(account.trades,3)
        self.assertEqual(account.position['direction'],-1)

    def test_futures_env_contract_and_terminal(self):
        parts = prepare(snapshot())
        scaler = TrainScaler().fit(parts['train'])
        env = FuturesEnv(parts['test'],scaler)
        check_env(env,warn=True)
        result = evaluate(env,lambda obs,row:2,True)
        self.assertTrue(np.isfinite(result['return_pct']))
        self.assertIsNone(env.account.position)
        self.assertTrue(result['decisions'][-1]['terminal'])
        self.assertEqual(result['trades'],sum(r['fills'] for r in result['decisions']))

    def test_funding_at_open_charged_only_to_carried_position(self):
        data = snapshot()
        parts = prepare(data);scaler = TrainScaler().fit(parts['train'])
        series = copy.deepcopy(parts['test'][:3])
        for row in series:
            from datetime import datetime,timezone
            ms = int(datetime.strptime(row['date'],'%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).timestamp()*1000)
            row['funding']=[dict(fundingTime=ms,markPrice='100',fundingRate='.001')]
        env = FuturesEnv(series,scaler)
        env.reset();env.step(1)
        self.assertEqual(env.account.funding_total,0)
        env.step(0)
        self.assertLess(env.account.funding_total,0)

    def test_futures_public_data_not_spot_fallback(self):
        with patch('zitar_next.market.get',side_effect=RuntimeError('unavailable')),patch('zitar_next.market._get_json') as spot:
            with self.assertRaises(RuntimeError):
                fetch('futures')
            spot.assert_not_called()

    def test_candle_parse_rejects_gaps_and_nonfinite(self):
        good = [[0,'100','101','99','100','1',HOUR-1]]
        self.assertEqual(len(parse(good,0,1,'BTCUSDT')),1)
        for field,value in ((0,1),(4,'NaN'),(6,HOUR)):
            bad=copy.deepcopy(good);bad[0][field]=value
            with self.assertRaises(ValueError):
                parse(bad,0,1,'BTCUSDT')

    def test_assessment_all_seeds_and_unseen_period(self):
        metric = dict(return_pct=5.,max_drawdown_pct=2.,trades=30)
        result = dict(test=metric,stress=dict(return_pct=1.))
        series = [dict(date='2026-10-01')]*150
        self.assertEqual(assess([result,result],{'cash':dict(return_pct=0.)},series),[])
        bad=dict(result,test=dict(metric,return_pct=-1.))
        issues=assess([result,bad],{'cash':dict(return_pct=0.)},series,previous_test_end='2026-10-02')
        self.assertIn('BASELINE_ADVANTAGE_NOT_MET',issues)
        self.assertIn('TEST_PERIOD_OVERLAPS_PREVIOUS_ROUND',issues)

    def test_short_training_records_proposal_without_activation(self):
        snap = snapshot()
        with patch('zitar_next.worker.fetch',return_value=snap) as get:
            body=train_round(self.root,'futures','BTCUSDT',128,seeds=(42,73))
            self.assertIsNone(train_round(self.root,'futures','BTCUSDT',128,seeds=(42,73)))
            self.assertEqual(get.call_count,2)
        self.assertEqual(len(body['seed_results']),2)
        self.assertFalse(body['eligible'])
        self.assertEqual(Registry(self.root).all()['active'],[])
        changed=copy.deepcopy(snap);changed['records'][0]['volume']=99
        with self.assertRaises(ValueError):
            train_round(self.root,'futures','BTCUSDT',128,snapshot=changed)

    def test_finrl_x_contract_signed_exposure(self):
        for market,action,weight in [('spot',1,1.),('futures',1,.3),('futures',2,-.3),('futures',0,0.)]:
            result=ZitarWeightStrategy(market).generate_weights(dict(symbol='BTCUSDT',date='2026-10-01',action=action))
            self.assertEqual(result.weights.iloc[0]['weight'],weight)
            self.assertFalse(result.metadata['real_orders'])
        with self.assertRaises(ValueError):
            ZitarWeightStrategy('spot').generate_weights(dict(symbol='BTCUSDT',date='2026-10-01',action=2))

    def test_http_origin_token_and_human_decision(self):
        registry=Registry(self.root);identity=registry.propose(proposal())
        server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.root,0))
        server.RequestHandlerClass=handler(self.root,server.server_port)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(server.server_port)
        try:
            with urlopen(base+'/api/state') as response:
                state=json.load(response)
            payload=json.dumps(dict(id=identity,decision='ACCEPT',note='disposable fixture human approval test')).encode()
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(base+'/api/decision',data=payload,headers={'Content-Type':'application/json'}))
            self.assertEqual(error.exception.code,403)
            headers={'Content-Type':'application/json','Origin':base,'X-Next-CSRF':state['csrf']}
            with urlopen(Request(base+'/api/decision',data=payload,headers=headers)) as response:
                self.assertEqual(json.load(response)['state'],'ACCEPTED')
            self.assertEqual(registry.all()['active'],[])
        finally:
            server.shutdown();server.server_close();thread.join()

    def test_unapproved_paper_never_loads_model(self):
        with patch('zitar_next.paper.PPO.load') as load:
            result=tick(self.root,'futures','BTCUSDT',snapshot())
        self.assertEqual(result['state'],'WAITING_HUMAN_APPROVAL')
        load.assert_not_called()
        self.assertFalse(list(self.root.glob('paper-*.json')))

    def test_approved_shadow_waits_then_applies_next_bar_once(self):
        snap=snapshot()
        scaler=TrainScaler().fit(prepare(snap)['train'])
        model=Mock();model.predict.return_value=(np.array(1),None)
        item=dict(id='fixture-approved-version')
        with patch('zitar_next.paper.approved',return_value=(item,scaler,[model,model])):
            first=tick(self.root,'futures','BTCUSDT',snap)
            self.assertEqual(first['account']['trades'],0)
            self.assertEqual(first['events'],[])
            new=snapshot(count=301)
            second=tick(self.root,'futures','BTCUSDT',new)
            self.assertEqual(second['account']['trades'],1)
            self.assertEqual(len(second['events']),1)
            third=tick(self.root,'futures','BTCUSDT',new)
            self.assertEqual(third['account']['trades'],1)
            self.assertEqual(len(third['events']),1)

    def test_seed_disagreement_targets_cash(self):
        a,b=Mock(),Mock()
        a.predict.return_value=(np.array(1),None);b.predict.return_value=(np.array(2),None)
        self.assertEqual(vote([a,b],np.zeros(10)),0)

    def test_static_inventory_does_not_import_application(self):
        source=Path(self.temp.name)/'fixture';source.mkdir()
        (source/'main.py').write_text('raise RuntimeError("must not execute")\nimport requests\n')
        result=inspect(source)
        self.assertIn('requests',result['import_roots'])
        self.assertFalse(result['services_touched'])
        self.assertFalse(result['database_opened'])

    def test_walk_forward_windows_never_use_final_test(self):
        snap=snapshot(count=1500)
        final_start=prepare(snap)['test'][0]['date']
        model=Mock();model.predict.return_value=(np.array(0),None)
        with patch('zitar_next.worker.PPO',return_value=model):
            result=walk_forward(self.root,'futures',snap,128,(42,73),final_start)
        self.assertEqual(len(result['folds']),3)
        previous=None
        for fold in result['folds']:
            self.assertLess(fold['train_end'],fold['validation_start'])
            self.assertLess(fold['validation_end'],fold['test_start'])
            self.assertLess(fold['test_end'],final_start)
            if previous:self.assertLess(previous,fold['test_start'])
            previous=fold['test_end']

    def test_spot_history_pages_share_fixed_cutoff(self):
        calls=[]
        def response(path,params=None):
            calls.append((path,params))
            if path.endswith('/time'):return dict(serverTime=2000*HOUR+123)
            return [[t,'100','101','99','100','1',t+HOUR-1] for t in range(params['startTime'],params['endTime']+1,HOUR)]
        with patch('zitar_next.market._get_json',side_effect=response):
            result=fetch('spot',count=1200)
        self.assertEqual(len(result['records']),1200)
        self.assertEqual(result['closed_before_ms'],2000*HOUR)
        self.assertEqual([p['limit'] for _,p in calls[1:]],[1000,200])

    def test_ensemble_does_not_count_as_another_seed(self):
        metric=dict(return_pct=5.,max_drawdown_pct=1.,trades=30)
        seeded=dict(seed=42,test=metric,stress=dict(return_pct=1.))
        ensemble=dict(test=metric,stress=dict(return_pct=1.))
        issues=assess([seeded,ensemble],{'cash':dict(return_pct=0.)},[dict(date='2026-10-01')]*150)
        self.assertIn('AT_LEAST_TWO_SEEDS_REQUIRED',issues)

    def test_public_client_retries_503_and_rejects_order_endpoint(self):
        opener=Mock()
        response=Mock();response.read.return_value=b'{"serverTime":123}'
        context=Mock();context.__enter__=Mock(return_value=response);context.__exit__=Mock(return_value=False)
        opener.open.side_effect=[HTTPError('https://fapi.binance.com',503,'unavailable',{},None),context]
        with patch('zitar_next.market.build_opener',return_value=opener),patch('zitar_next.market.time.sleep') as sleep:
            self.assertEqual(get('/fapi/v1/time')['serverTime'],123)
            self.assertEqual(opener.open.call_count,2)
            sleep.assert_called_once_with(1)
        with self.assertRaises(ValueError):
            get('/fapi/v1/order')

    def test_rate_limit_does_not_retry_this_cycle(self):
        opener=Mock();opener.open.side_effect=HTTPError('https://fapi.binance.com',429,'rate limited',{},None)
        with patch('zitar_next.market.build_opener',return_value=opener),patch('zitar_next.market.time.sleep') as sleep:
            with self.assertRaisesRegex(RuntimeError,'429'):
                get('/fapi/v1/time')
            sleep.assert_not_called()
            self.assertEqual(opener.open.call_count,1)


if __name__=='__main__':
    unittest.main()
