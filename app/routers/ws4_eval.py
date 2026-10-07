"""Evaluation endpoints. Owner: WS4. Serves JSON saved in results/ by the runners; never fabricates numbers."""
from fastapi import APIRouter

from . import _state

router = APIRouter(prefix="/api/eval", tags=["ws4-eval"])


def _serve(*names):
    for n in names:
        d = _state.results_file(n)
        if d is not None:
            return {"available": True, "file": n, "data": d}
    return {"available": False, "status": f"PLACEHOLDER: no saved run yet ({' / '.join(names)} missing). See docs/STATUS.md for the command."}


@router.get("/summary")
def summary():
    """Latest dev run, and the final test run when it exists (separate keys)."""
    dev, test = _serve("dev_eval.json"), _serve("test_eval.json")
    return {"available": dev["available"], "dev": dev.get("data"), "test": test.get("data"),
            "status": None if dev["available"] else dev["status"]}


@router.get("/ablation")
def ablation():
    return _serve("b2_ablation_dev.json")


@router.get("/leakage")
def leakage():
    return _serve("leakage_audit.json")


@router.get("/efficiency")
def efficiency():
    return _serve("efficiency.json")


@router.get("/zone_matrix")
def zone_matrix():
    r = _serve("zone_matrix.json")
    if r["available"]:
        r["note"] = "NEGATIVE RESULT: the learned matrix did not beat tf-idf on dev (see results/w_variant.json)."
    return r
