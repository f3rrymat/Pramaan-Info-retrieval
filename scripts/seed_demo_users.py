"""Create the three demo roles with random passwords (DECISIONS D37). Passwords are written ONCE to data/demo_credentials.txt
(git-ignored, mode 0600); only the file path is printed. Re-running regenerates passwords for these three users.
Usage: python scripts/seed_demo_users.py
"""
import os
import secrets
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
from app import security as sec  # noqa: E402

USERS = (("researcher", "researcher"), ("analyst", "analyst"), ("admin", "admin"))
con = sec.connect()
lines = ["# Demo credentials (local only; do not share, do not commit). Regenerate with scripts/seed_demo_users.py", ""]
for name, role in USERS:
    pw = secrets.token_urlsafe(12)
    con.execute("INSERT INTO users (username, role, pw_hash, created_at) VALUES (?,?,?,?) ON CONFLICT(username) DO UPDATE SET pw_hash=excluded.pw_hash, role=excluded.role",
                (name, role, sec.hash_password(pw), time.time()))
    lines.append(f"{name}  {pw}")
con.commit()
out = Path(os.environ.get("IRLEGAL_DEMO_CREDENTIALS") or ROOT / "data" / "demo_credentials.txt")
out.parent.mkdir(exist_ok=True)
fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    f.write("\n".join(lines) + "\n")
# prove that what was written signs in: re-read the file, verify each password against the stored hash (nothing secret is printed)
written = {l.split()[0]: l.split()[1] for l in out.read_text().splitlines() if l and not l.startswith("#")}
verified = sum(1 for name, _ in USERS if sec.verify_password(written[name], con.execute("SELECT pw_hash FROM users WHERE username=?", (name,)).fetchone()["pw_hash"]))
print(f"Demo users created. Credentials: {out}")
print(f"Database: {sec.db_path()}  (the server must use this same file; override with IRLEGAL_APP_DB)")
print(f"Verified {verified}/{len(USERS)} stored hashes against the credentials file.")
if verified != len(USERS):
    sys.exit("Verification failed: the credentials file does not match the database.")
