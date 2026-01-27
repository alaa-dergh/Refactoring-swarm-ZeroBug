# File: buggy_calculator.py
# This file has multiple bugs for testing

def divide(a, b):
    return a / b  # Bug: No check for division by zero!

def calculate_average(numbers=[]):  # Bug: Mutable default argument!
    total = 0
    for n in numbers
        total += n  # Bug: Missing colon!
    return total / len(numbers)

def process_data(data):
    result = eval(data)  # Bug: Dangerous use of eval!
    return result

x = 10
y = 0
print(divide(x, y))  # This will crash!