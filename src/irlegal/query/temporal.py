"""Temporal filter helper (spec 9.6): keep only candidates strictly older than the query.

Owner: WS2. Not a separate module: the temporal filter is applied as a candidate mask (see evaluation/runner.py and evaluation/leakage.py).
"""
