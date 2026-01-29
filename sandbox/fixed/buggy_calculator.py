def divide(a, b):
    """Divide two numbers."""
    if b == 0:
        raise ZeroDivisionError('Division by zero')
    return a / b


def calculate_average(numbers=None):
    """Calculate the average of a list of numbers."""
    if numbers is None:
        numbers = []
    if len(numbers) == 0:
        raise ValueError('Cannot calculate average of empty list')
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)


def process_data(data):
    """Process data using a safer method."""
    try:
        result = eval(data, {'__builtins__': {}}, {})  # Restrict eval to prevent code injection
    except Exception as e:
        raise ValueError('Invalid data') from e
    return result