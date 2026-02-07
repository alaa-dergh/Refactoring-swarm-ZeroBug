import pytest
import sys
import os
import importlib.util

# Ajouter le dossier du module source au path
sys.path.insert(0, os.path.abspath(os.path.dirname(r'NEW\base2.py')))

def load_module():
    spec = importlib.util.spec_from_file_location("base2", r"NEW\base2.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

test_module = load_module()

def test_module_load():
    assert test_module is not None, 'Module should load without errors'
