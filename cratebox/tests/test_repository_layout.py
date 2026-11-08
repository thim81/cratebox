from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CRATEBOX_ROOT = REPOSITORY_ROOT / "cratebox"
sys.path.insert(0, str(CRATEBOX_ROOT))
from api.collection import CollectionMcp


def test_rekordbox_adapter_is_nested_under_cratebox():
    adapter = CRATEBOX_ROOT / "rekordbx-mcp"

    assert (adapter / "pyproject.toml").is_file()
    assert not (REPOSITORY_ROOT / "rekordbx-mcp" / "pyproject.toml").exists()
    assert (REPOSITORY_ROOT / "rekordbx-mcp" / ".cache").is_dir()
    assert CollectionMcp().project == adapter
