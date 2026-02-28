import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bad_syntax import calculate_sum


def test_calculate_sum_integers():
    assert calculate_sum(1, 2) == 3

def test_calculate_sum_floats():
    assert calculate_sum(1.5, 2.5) == 4.0

def test_calculate_sum_mixed_types():
    assert calculate_sum(1, 2.5) == 3.5

def test_calculate_sum_error_handling_non_numeric_input():
    with pytest.raises(TypeError):
        calculate_sum('a', 2)

def test_calculate_sum_error_handling_non_numeric_input_both_args():
    with pytest.raises(TypeError):
        calculate_sum('a', 'b')