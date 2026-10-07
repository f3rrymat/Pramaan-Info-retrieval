# WS2 targets: query benchmarks, crawl simulation, decomposition, README assembly.
.PHONY: bench-and crawl-sim decompose readme
bench-and:  ## AND order benchmark on the real index -> results/and_benchmark.json
	$(PY) scripts/bench_and.py
crawl-sim:  ## crawl simulation on the citation graph (no network) -> results/crawl_sim.json
	$(PY) scripts/run_crawl_sim.py
decompose:  ## issue decomposition experiment on dev -> results/decompose_dev.json
	$(PY) scripts/run_decompose.py
readme:  ## assemble README.md from docs/ws*.md and results/
	$(PY) scripts/make_readme.py
