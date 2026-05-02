import pathlib
import pytest

PROJECT_ROOT = pathlib.Path(__file__).parent.parent

@pytest.fixture
def damodaran_data_dir():
    """Path to the Damodaran datasets directory.

    Checks two locations:
    1. Inside repo: data/damodaran/ (for CI)
    2. Sibling dir: ../2. Damodaran_Data/ (for local dev)
    """
    in_repo = PROJECT_ROOT / "data" / "damodaran"
    sibling = PROJECT_ROOT.parent / "2. Damodaran_Data"
    if in_repo.exists():
        return in_repo
    if sibling.exists():
        return sibling
    pytest.skip(f"Damodaran data not found at {in_repo} or {sibling}")

@pytest.fixture
def examples_dir():
    """Path to example valuation spreadsheets."""
    path = PROJECT_ROOT.parent / "3. Valuation examples"
    if not path.exists():
        pytest.skip(f"Examples not found at {path}")
    return path
