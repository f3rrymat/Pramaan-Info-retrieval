"""Per-result explanation (spec 6, step 8; D21). Owner: WS3. No case text: only ids, tokens, numbers."""
from typing import Dict, List, Optional, Sequence

import numpy as np


def explain_result(doc_id: str, components: Dict[str, float], weights: Dict[str, float],
                   neighbours: Optional[List[Dict]] = None, shared_statutes: Optional[Sequence[str]] = None,
                   zone_cosines: Optional[Dict[str, float]] = None, zone_weights: Optional[Dict[str, float]] = None,
                   top_zones: int = 3) -> Dict:
    """components: normalised feature values in [0,1]; weights: the net-score weights.

    Returns the weighted component contributions (sorted), the neighbours that cite the document
    (ids and similarities), the statute tokens shared by prediction and document, and the strongest
    zone pairs (weight x cosine) when those are provided.
    """
    contrib = {f: round(float(weights.get(f, 0.0)) * float(v), 5) for f, v in components.items()}
    out = {
        "doc_id": doc_id,
        "net_score": round(sum(contrib.values()), 5),
        "contributions": dict(sorted(contrib.items(), key=lambda kv: -kv[1])),
        "neighbours": list(neighbours or []),
        "shared_statutes": sorted(shared_statutes or []),
    }
    if zone_cosines:
        zw = zone_weights or {}
        pairs = {k: round(float(zw.get(k, 1.0)) * float(v), 5) for k, v in zone_cosines.items()}
        out["zone_contributions"] = dict(sorted(pairs.items(), key=lambda kv: -kv[1])[:top_zones])
    return out


def shared_statute_tokens(bridge, predicted_rows: Sequence[int], doc_index: int) -> List[str]:
    """Tokens of the predicted provisions that the document's statute set contains."""
    held = set(bridge.doc_prov.getrow(doc_index).indices.tolist())
    return [bridge.prov_token[r] or bridge.prov_ids[r] for r in predicted_rows if r in held]
