import importlib

import pytest


@pytest.mark.parametrize("package", ["bootstrap", "extractors", "loaders", "simulator", "common"])
def test_package_imports(package):
    assert importlib.import_module(package)
