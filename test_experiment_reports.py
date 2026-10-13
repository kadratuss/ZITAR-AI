import importlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

class ReportTests(unittest.TestCase):
 def check_report(self,module_name,normal,paused):
  module=importlib.import_module(module_name)
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);(root/'zitar_futures_only.flag').touch()
   if paused:(root/'zitar_comparison_supervisor.pause').touch()
   books={k:dict(market=market,closed=[],execution_policy={'slippage_rate':'.0002'}) for market in ('spot','futures') for k in [market+'_'+normal,market+'_STRESS']}
   (root/module.STATE).write_text(json.dumps(dict(books=books,heartbeat_ms=int(__import__('time').time()*1000)-1000 if paused else 0,state='RUNNING')),encoding='utf-8')
   def metric(b,ms):return dict(net=10 if b is books.get('none') else 0,issues=[],verdict='KANIT_YETERSIZ')
   with patch.object(module,'metrics',side_effect=metric): result=module.overview(root)
   self.assertEqual(set(result['books']),{'futures_'+normal,'futures_STRESS'})
   self.assertIn('net_difference_vs_normal_slip',result['evaluation']['futures_STRESS'])
   if paused:
    self.assertEqual(result['state'],'RUNNING');self.assertNotIn('supervisor_paused',result)
    self.assertFalse(result['evaluation']['futures_STRESS']['automatic_promotion'])
   else:self.assertEqual(result['state'],'STALE')
 def test_research_running(self):self.check_report('zitar_research_experiment_v1','REGIME',True)
 def test_momentum_running(self):self.check_report('zitar_momentum_experiment_v2','GUARD',True)
 def test_research_stale(self):self.check_report('zitar_research_experiment_v1','REGIME',False)
 def test_momentum_stale(self):self.check_report('zitar_momentum_experiment_v2','GUARD',False)
if __name__=='__main__':unittest.main()
