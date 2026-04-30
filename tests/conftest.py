import pathlib
import pytest

PROJECT_ROOT = pathlib.Path(__file__).parent.parent

@pytest.fixture
def damodaran_data_dir():
    """Path to the Damodaran datasets directory (sibling to project root)."""
    path = PROJECT_ROOT.parent / "2. Damodaran_Data"
    if not path.exists():
        pytest.skip(f"Damodaran data not found at {path}")
    return path

@pytest.fixture
def examples_dir():
    """Path to example valuation spreadsheets."""
    path = PROJECT_ROOT.parent / "3. Valuation examples"
    if not path.exists():
        pytest.skip(f"Examples not found at {path}")
    return path
