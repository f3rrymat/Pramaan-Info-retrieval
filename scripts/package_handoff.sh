#!/usr/bin/env bash
# Zip the repository for the next member. results/ ships (aggregates only, docs/results_scan.md). Excludes data/, .venv, .git and caches, then verifies the
# archive holds no parquet, pickle, npz/npy, index blob (.vb) or token/secret file; deletes the zip if it does.
# Usage: bash scripts/package_handoff.sh [output.zip]
set -euo pipefail
cd "$(dirname "$0")/.."
OUT="${1:-../ir-legal-handoff.zip}"
rm -f "$OUT"
zip -rq "$OUT" . \
  -x ".git/*" ".venv/*" "venv/*" "data/*" "results/*.npz" "results/*/*.npz" "results/*.npy" "results/*.pkl" "results/*.parquet" "*/__pycache__/*" "__pycache__/*" ".pytest_cache/*" ".mypy_cache/*" ".ruff_cache/*" \
     ".ipynb_checkpoints/*" ".DS_Store" "*/.DS_Store" ".env" "*/.env" "*.egg-info/*" "*.pyc" "*.db" "*.sqlite" "*.sqlite3"
# .env.<anything> is excluded too, except the empty template .env.example (D41)
for f in $(ls -a | grep -E '^\.env\.' | grep -v '^\.env\.example$' || true); do zip -dq "$OUT" "$f" >/dev/null 2>&1 || true; done
BAD=$(unzip -Z1 "$OUT" | grep -Ei '\.(parquet|pkl|pickle|npz|npy|vb|db|sqlite3?)$|(^|/)(\.env[^/]*|[^/]*(secret|credential)[^/]*|[^/]*\.pem|id_rsa[^/]*|\.?(hf_)?token(\.txt|\.json)?|[^/]*_token(\.txt|\.json)?)$' | grep -v '^\.env\.example$' || true)
# the template must stay empty: SARVAM_API_KEY= with nothing after it
if unzip -p "$OUT" .env.example 2>/dev/null | grep -E '^SARVAM_API_KEY=.+' >/dev/null; then BAD="$BAD .env.example has a value"; fi
# no Sarvam-style key anywhere in the text files of the archive
if unzip -p "$OUT" 2>/dev/null | grep -aE 'sk_[A-Za-z0-9]{16,}' >/dev/null; then BAD="$BAD a key-like string (sk_...) is inside a file"; fi
if [ -n "$BAD" ]; then
  echo "REFUSING: forbidden files in the archive:" >&2
  echo "$BAD" >&2
  rm -f "$OUT"
  exit 1
fi
echo "OK: $(unzip -Z1 "$OUT" | wc -l | tr -d ' ') files, $(du -h "$OUT" | cut -f1), no parquet/pickle/npz/npy/index blobs/tokens. Wrote $OUT"
