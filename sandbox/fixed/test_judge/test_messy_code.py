import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from messy_code import is_within_range


def test_is_within_range_positive():
    assert is_within_range(50) == True

def test_is_within_range_negative():
    assert is_within_range(-50) == False

def test_is_within_range_zero():
    assert is_within_range(0) == False

def test_is_within_range_hundred():
    assert is_within_range(100) == False

def test_is_within_range_non_integer():
    with pytest.raises(TypeError):
        is_within_range('a')
