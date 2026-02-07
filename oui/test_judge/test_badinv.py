import pytest
import sys
import os
import importlib.util

# Ajouter le dossier du module source au path
sys.path.insert(0, os.path.abspath(os.path.dirname(r'oui\badinv.py')))

def load_module():
    spec = importlib.util.spec_from_file_location("badinv", r"oui\badinv.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

test_module = load_module()


def test_add_item_exists():
    assert hasattr(test_module, "add_item"), "Function 'add_item' should exist"
    assert callable(getattr(test_module, "add_item")), "'add_item' must be callable"

def test_add_item_call_basic():
    func_to_test = getattr(test_module, "add_item")
    try:
        result = func_to_test()
        # Si la fonction retourne quelque chose, on check juste qu'elle ne crash pas
        assert True
    except TypeError:
        pytest.skip("Function 'add_item' requires arguments, skipping basic call")
    except Exception as e:
        pytest.fail(f"Function 'add_item' raised an unexpected exception: {e}")

def test_remove_item_exists():
    assert hasattr(test_module, "remove_item"), "Function 'remove_item' should exist"
    assert callable(getattr(test_module, "remove_item")), "'remove_item' must be callable"

def test_remove_item_call_basic():
    func_to_test = getattr(test_module, "remove_item")
    try:
        result = func_to_test()
        # Si la fonction retourne quelque chose, on check juste qu'elle ne crash pas
        assert True
    except TypeError:
        pytest.skip("Function 'remove_item' requires arguments, skipping basic call")
    except Exception as e:
        pytest.fail(f"Function 'remove_item' raised an unexpected exception: {e}")

def test_get_total_value_exists():
    assert hasattr(test_module, "get_total_value"), "Function 'get_total_value' should exist"
    assert callable(getattr(test_module, "get_total_value")), "'get_total_value' must be callable"

def test_get_total_value_call_basic():
    func_to_test = getattr(test_module, "get_total_value")
    try:
        result = func_to_test()
        # Si la fonction retourne quelque chose, on check juste qu'elle ne crash pas
        assert True
    except TypeError:
        pytest.skip("Function 'get_total_value' requires arguments, skipping basic call")
    except Exception as e:
        pytest.fail(f"Function 'get_total_value' raised an unexpected exception: {e}")

def test_find_item_exists():
    assert hasattr(test_module, "find_item"), "Function 'find_item' should exist"
    assert callable(getattr(test_module, "find_item")), "'find_item' must be callable"

def test_find_item_call_basic():
    func_to_test = getattr(test_module, "find_item")
    try:
        result = func_to_test()
        # Si la fonction retourne quelque chose, on check juste qu'elle ne crash pas
        assert True
    except TypeError:
        pytest.skip("Function 'find_item' requires arguments, skipping basic call")
    except Exception as e:
        pytest.fail(f"Function 'find_item' raised an unexpected exception: {e}")

def test_update_quantity_exists():
    assert hasattr(test_module, "update_quantity"), "Function 'update_quantity' should exist"
    assert callable(getattr(test_module, "update_quantity")), "'update_quantity' must be callable"

def test_update_quantity_call_basic():
    func_to_test = getattr(test_module, "update_quantity")
    try:
        result = func_to_test()
        # Si la fonction retourne quelque chose, on check juste qu'elle ne crash pas
        assert True
    except TypeError:
        pytest.skip("Function 'update_quantity' requires arguments, skipping basic call")
    except Exception as e:
        pytest.fail(f"Function 'update_quantity' raised an unexpected exception: {e}")

def test_load_inventory_exists():
    assert hasattr(test_module, "load_inventory"), "Function 'load_inventory' should exist"
    assert callable(getattr(test_module, "load_inventory")), "'load_inventory' must be callable"

def test_load_inventory_call_basic():
    func_to_test = getattr(test_module, "load_inventory")
    try:
        result = func_to_test()
        # Si la fonction retourne quelque chose, on check juste qu'elle ne crash pas
        assert True
    except TypeError:
        pytest.skip("Function 'load_inventory' requires arguments, skipping basic call")
    except Exception as e:
        pytest.fail(f"Function 'load_inventory' raised an unexpected exception: {e}")

def test_save_inventory_exists():
    assert hasattr(test_module, "save_inventory"), "Function 'save_inventory' should exist"
    assert callable(getattr(test_module, "save_inventory")), "'save_inventory' must be callable"

def test_save_inventory_call_basic():
    func_to_test = getattr(test_module, "save_inventory")
    try:
        result = func_to_test()
        # Si la fonction retourne quelque chose, on check juste qu'elle ne crash pas
        assert True
    except TypeError:
        pytest.skip("Function 'save_inventory' requires arguments, skipping basic call")
    except Exception as e:
        pytest.fail(f"Function 'save_inventory' raised an unexpected exception: {e}")

def test_clear_inventory_exists():
    assert hasattr(test_module, "clear_inventory"), "Function 'clear_inventory' should exist"
    assert callable(getattr(test_module, "clear_inventory")), "'clear_inventory' must be callable"

def test_clear_inventory_call_basic():
    func_to_test = getattr(test_module, "clear_inventory")
    try:
        result = func_to_test()
        # Si la fonction retourne quelque chose, on check juste qu'elle ne crash pas
        assert True
    except TypeError:
        pytest.skip("Function 'clear_inventory' requires arguments, skipping basic call")
    except Exception as e:
        pytest.fail(f"Function 'clear_inventory' raised an unexpected exception: {e}")
