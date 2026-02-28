import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from logic_bug import count_down


def test_count_down_positive_integer():
    	# Test with a positive integer
    count_down(5)


def test_count_down_zero():
    	# Test with zero
    with pytest.raises(ValueError):
        count_down(0)


def test_count_down_negative_integer():
    	# Test with a negative integer
    with pytest.raises(ValueError):
        count_down(-5)


def test_count_down_non_integer():
    	# Test with a non-integer
    with pytest.raises(TypeError):
        count_down(5.5)


def test_count_down_string():
    	# Test with a string
    with pytest.raises(TypeError):
        count_down('5')
