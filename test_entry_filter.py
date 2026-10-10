import unittest
from unittest.mock import Mock
import gymnasium as gym
import numpy as np
from zitar_next.entry_filter import EntryFilterEnv, filtered_action, prepare_filter
from research_environment import TrainScaler
from zitar_next.worker import env_for
from stable_baselines3.common.env_checker import check_env
from datetime import datetime,timezone


class EntryTests(unittest.TestCase):
    def test_permission_only_filters_new_entries(self):
        self.assertEqual(filtered_action(1,0,0),0)
        self.assertEqual(filtered_action(1,0,1),1)
        self.assertEqual(filtered_action(1,1,0),1)
        self.assertEqual(filtered_action(0,1,1),0)
        self.assertEqual(filtered_action(2,1,0),0)
        self.assertEqual(filtered_action(2,1,1),2)
        self.assertEqual(filtered_action(2,2,0),2)

    def test_futures_position_and_rsi_exit_are_preserved(self):
        env=gym.Env()
        env.observation_space=gym.spaces.Box(-10,10,shape=(10,),dtype=np.float32)
        env.action_space=gym.spaces.Discrete(3)
        env.records=[dict(date='one')];env.index=0
        env.account=Mock(position=dict(direction=-1))
        env.step=Mock(return_value=(np.zeros(10,dtype=np.float32),0,False,False,{}))
        wrapper=EntryFilterEnv(env,{'one':2},'futures')
        obs,*_=wrapper.step(0)
        env.step.assert_called_with(2)
        self.assertEqual(obs[-1],-1)
        wrapper.rules['one']=0
        wrapper.step(1)
        env.step.assert_called_with(0)

    def test_invalid_permission_rejected(self):
        with self.assertRaises(ValueError): filtered_action(1,0,2)

    def test_real_environment_warmup_and_binary_learning_interface(self):
        records=[]
        start=1700000000000//3600000*3600000
        for i in range(1000):
            price=100+np.sin(i/10)*5
            records.append(dict(date=datetime.fromtimestamp((start+i*3600000)/1000,timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
                tic='BTCUSDT',open=float(price),high=float(price+1),low=float(price-1),close=float(price),volume=10.,day=0))
        snapshot=dict(records=records,server_time_ms=start+1000*3600000)
        parts,rules=prepare_filter(snapshot,'spot')
        self.assertGreater(parts['metadata']['partitions']['train']['signal_warmup_excluded'],0)
        scaler=TrainScaler().fit(parts['train'])
        check_env(EntryFilterEnv(env_for('spot',parts['train'],scaler),rules,'spot'),warn=True)


if __name__=='__main__': unittest.main()
