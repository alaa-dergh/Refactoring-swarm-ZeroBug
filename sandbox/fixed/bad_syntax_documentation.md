# Bad Syntax - Documentation

**Status**: Production Ready - All Tests Passed  
**File**: `bad_syntax.py`

---

## Overview
This Python module provides a simple function to calculate the sum of two numbers. It includes input validation to ensure both numbers are either integers or floats. The module is designed to be used in various mathematical operations where basic arithmetic is required.

---

## Functions

### `calculate_sum(a, b)`

**Description:**  
This function calculates the sum of two numbers, `a` and `b`. It first checks if both inputs are valid numbers (either integers or floats) and then returns their sum.

**Parameters:**
- `a` (int or float): The first number to be added.
- `b` (int or float): The second number to be added.

**Returns:**
- int or float: The sum of `a` and `b`.

**Examples:**
python
>>> calculate_sum(5, 7)
12
>>> calculate_sum(3.5, 2.8)
6.3


**Edge Cases:**
- If either `a` or `b` is not a number, the function raises a TypeError with the message "Both 'a' and 'b' must be numbers".
- The function does not handle non-numeric string inputs or other non-numeric types.
- Error handling is implemented through a TypeError exception.

---

## Summary

### Functions Included
- `calculate_sum`: Calculates the sum of two numbers, validating that both are integers or floats.

### Testing Status
✅ All functions tested and validated