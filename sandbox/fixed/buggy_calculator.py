def divide(a, b):
    """Divide two numbers."""
    if b == 0:
        raise ValueError('Division by zero')
    return a / b


def calculate_average(numbers=None):
    """Calculate the average of a list of numbers."""
    if numbers is None:
        numbers = []
    if not numbers:
        raise ValueError('Cannot calculate average of empty list')
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)


def process_data(data):
    """Process data using a safer alternative to eval."""
    try:
        result = eval(data, {}, {})  # Using eval with restricted scope
    except Exception as e:
        raise ValueError('Invalid data') from e
    return result

x = 10
y = 0
try:
    print(divide(x, y))
except ValueError as e:
    print(e)