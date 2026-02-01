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
        raise ValueError("Input list is empty")
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)


def process_data(data):
    """
    Process the given data.

    Args:
        data (str): The data to process.

    Returns:
        float: The result of the processed data.
    """
    # For simplicity, let's assume the data is a simple arithmetic expression
    # In a real-world scenario, you would use a parsing library or write a custom parser
    try:
        result = eval(data)
    except Exception as e:
        raise ValueError("Failed to process data: " + str(e))
    return result

x = 10
y = 0
try:
    print(divide(x, y))
except ZeroDivisionError as e:
    print(str(e))