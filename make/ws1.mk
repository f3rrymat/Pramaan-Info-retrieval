# WS1 targets: data, index (and crawl stretch).
.PHONY: data index
data:  ## download + inspect the dataset (WS1)
	$(PY) scripts/inspect_data.py
index:  ## build the persisted index (WS1)
	$(PY) scripts/build_index.py
