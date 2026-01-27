def divide(a, b):
    """Divide two numbers.

    Args:
        a (float): The dividend.
        b (float): The divisor.

    Returns:
        float: The quotient.

    Raises:
        ZeroDivisionError: If the divisor is zero.
    """
    if b == 0:
        raise ZeroDivisionError('Division by zero')
    return a / b


def calculate_average(numbers=None):
    """Calculate the average of a list of numbers.

    Args:
        numbers (list): A list of numbers.

    Returns:
        float: The average of the numbers.

    Raises:
        ValueError: If the input list is empty.
    """
    if numbers is None:
        numbers = []
    if not numbers:
        raise ValueError('Cannot calculate average of empty list')
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)


def process_data(data):
    """Process data using a safer method.

    Args:
        data (str): The data to process.

    Returns:
        float: The result of the processed data.

    Raises:
        ValueError: If the data is invalid.
    """
    try:
        result = eval(data, {'__builtins__': {'abs': abs, 'all': all, 'any': any, 'bool': bool, 'complex': complex, 'dict': dict, 'float': float, 'int': int, 'len': len, 'list': list, 'max': max, 'min': min, 'range': range, 'reversed': reversed, 'round': round, 'set': set, 'str': str, 'sum': sum, 'tuple': tuple}})
        return result
    except Exception as e:
        raise ValueError('Invalid data') from e