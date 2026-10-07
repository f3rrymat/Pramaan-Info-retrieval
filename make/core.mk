# Phase 0 core targets (frozen with contracts-v1).
PY ?= python3
export PYTHONPATH := src:.
HOST ?= 127.0.0.1
PORT ?= 8000
# Local demo convenience only: one-click role sign-in from this machine. Never enable on a shared or hosted server; not access control.
DEMO_QUICK_LOGIN ?= 1
export DEMO_QUICK_LOGIN

.PHONY: help install test demo
.DEFAULT_GOAL := help

help:  ## list targets
	@grep -hE '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

install:  ## install all workstream requirements
	$(PY) -m pip install -r requirements.txt

test:  ## run every test suite
	$(PY) -m pytest -q

demo:  ## start the API + UI on http://$(HOST):$(PORT)
	$(PY) -m uvicorn app.server:app --host $(HOST) --port $(PORT)
