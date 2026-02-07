import pytest
import sys
import os
import importlib.util

# Ajouter le dossier du module source au path
sys.path.insert(0, os.path.abspath(os.path.dirname(r'NEW\bad1.py')))

def load_module():
    spec = importlib.util.spec_from_file_location("bad1", r"NEW\bad1.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

test_module = load_module()


def test_update_x_exists():
    assert hasattr(test_module, "update_x"), "Function 'update_x' should exist"
    assert callable(getattr(test_module, "update_x")), "'update_x' must be callable"

def test_update_x_call_basic():
    func_to_test = getattr(test_module, "update_x")
    try:
        result = func_to_test(1)
        # Si la fonction retourne quelque chose, on check juste qu'elle ne crash pas
        assert True
    except Exception as e:
        pytest.fail(f"Function 'update_x' raised an unexpected exception: {e}")

def test_update_data_data_exists():
    assert hasattr(test_module, "update_data_data"), "Function 'update_data_data' should exist"
    assert callable(getattr(test_module, "update_data_data")), "'update_data_data' must be callable"

def test_update_data_data_call_basic():
    func_to_test = getattr(test_module, "update_data_data")
    try:
        result = func_to_test(1)
        # Si la fonction retourne quelque chose, on check juste qu'elle ne crash pas
        assert True
    except Exception as e:
        pytest.fail(f"Function 'update_data_data' raised an unexpected exception: {e}")

def test_do_stuff_exists():
    assert hasattr(test_module, "do_stuff"), "Function 'do_stuff' should exist"
    assert callable(getattr(test_module, "do_stuff")), "'do_stuff' must be callable"

def test_do_stuff_call_basic():
    func_to_test = getattr(test_module, "do_stuff")
    try:
        result = func_to_test(1, 1, None)
        # Si la fonction retourne quelque chose, on check juste qu'elle ne crash pas
        assert True
    except Exception as e:
        pytest.fail(f"Function 'do_stuff' raised an unexpected exception: {e}")
