def divide(a, b):
    """
    Divide two numbers.

    Args:
        a (float): The dividend.
        b (float): The divisor.

    Returns:
        float: The quotient.

    Raises:
        ZeroDivisionError: If the divisor is zero.
    """
    if b == 0:
        raise ZeroDivisionError("Cannot divide by zero")
    return a / b


def calculate_average(numbers=None):
    """
    Calculate the average of a list of numbers.

    Args:
        numbers (list): A list of numbers.

    Returns:
        float: The average of the numbers.

    Raises:
        ValueError: If the input list is empty.
    """
    if numbers is None:
        numbers = []
    if len(numbers) == 0:
        raise ValueError("Cannot calculate average of empty list")
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)


def process_data(data):
    """
    Process data using a safer method of evaluation.

    Args:
        data (str): The data to process.

    Returns:
        float: The result of the evaluation.
    """
    # For simplicity, we will use a simple whitelist of allowed functions
    allowed_functions = {
        "add": lambda x, y: x + y,
        "subtract": lambda x, y: x - y,
        "multiply": lambda x, y: x * y,
        "divide": lambda x, y: x / y if y != 0 else float("inf")
    }
    parts = data.split()
    if len(parts) != 3:
        raise ValueError("Invalid data format")
    num1, func, num2 = parts
    try:
        num1 = float(num1)
        num2 = float(num2)
    except ValueError:
        raise ValueError("Invalid number format")
    if func in allowed_functions:
        return allowed_functions[func](num1, num2)
    else:
        raise ValueError("Invalid function")

x = 10
y = 0
try:
    print(divide(x, y))
except ZeroDivisionError as e:
    print(e)