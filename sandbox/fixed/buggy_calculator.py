def divide(a, b):
    if b == 0:
        raise ZeroDivisionError("Cannot divide by zero")
    return a / b

def calculate_average(numbers=None):
    if numbers is None:
        numbers = []
    if not numbers:
        raise ValueError("Cannot calculate average of empty list")
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)

def process_data(data):
    # Removed eval() for security - implement proper validation if needed
    return data

x = 10
y = 0
try:
    print(divide(x, y))
except ZeroDivisionError as e:
    print(f"Error: {e}")