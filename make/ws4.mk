# WS4 targets: eval, efficiency, leakage, assets, handoff.
.PHONY: eval eval-dev leakage efficiency assets handoff
eval: eval-dev leakage efficiency assets  ## regenerate every dev table and figure (the test split is never run here)
eval-dev:  ## dev baselines and Config A -> results/dev_eval.json
	$(PY) -m irlegal.evaluation.runner --split dev
leakage:  ## leakage audit (train and dev only)
	$(PY) -m irlegal.evaluation.leakage
efficiency:  ## champion lists, tiers, elimination, cluster pruning, heap
	$(PY) scripts/run_efficiency.py
assets:  ## figures in docs/figures and tables in docs/results_tables.md
	$(PY) scripts/make_report_assets.py
handoff:  ## zip for the next member (no data, results or tokens)
	bash scripts/package_handoff.sh
