# Learning-curve trial

BTCUSDT spot simulation; closed 1h candles; seed 42; 8192 steps.
Snapshot SHA256: 593e5f83e70948c1719309e1545b55621bcc9da2d584881308509bda8f789f99.

Recorded 17 train/validation checkpoints and 14 completed training episode rewards.
Train deterministic return: -9.0720% at step 0 to -0.5779% at final step.
Validation return: -1.2902% to -0.7888%.
Final held-out test return: -2.7183%.
Buy-hold: -2.6728%; SMA20/50: -0.6079%; cash: 0%.

The final PPO remains below these baselines. The learning curve is not monotonic
and more steps do not demonstrate out-of-sample improvement. Earlier trials
used a different rolling snapshot, so their test returns are not a controlled
comparison with this run. No checkpoint selection or test-based tuning.

Test trace contains 189 hourly target decisions
and 6 simulated fills including terminal liquidation.
No ongoing training, model service, broker or real orders were started.
Artifacts remain local and are not included in the PR.

Validation: all 85 unittests passed. Browser verified old-run missing-history
states and new-run 17 checkpoint rows, 20 recent decision rows and no console errors.
