import eob
import healthcore


def test_packages_import():
    assert eob.__version__ == "0.2.0"
    assert healthcore.__version__ == "0.2.0"
