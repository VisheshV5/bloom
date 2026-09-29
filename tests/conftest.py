import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402


@pytest.fixture
def coffee_db(tmp_path):
    """Attach an exported copy of the dataset (as a data owner's node would), detach after."""
    from bloom.tools import sql
    from tasks.local_db import export

    path = export(tmp_path / "coffee.sqlite")
    sql.configure(str(path))
    yield path
    sql.configure(None)
