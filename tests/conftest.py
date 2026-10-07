import os
import tempfile

# API smoke tests run against the toy corpus on any machine, even one that holds the real data, without sign-in.
os.environ.setdefault("IRLEGAL_MODE", "toy")
os.environ.setdefault("AUTH_REQUIRED", "0")
_tmp = tempfile.mkdtemp(prefix="irl_app_")          # never touch data/app.db from tests
os.environ["IRLEGAL_APP_DB"] = os.path.join(_tmp, "app.db")
os.environ["IRLEGAL_APP_SECRET"] = os.path.join(_tmp, "secret.key")
