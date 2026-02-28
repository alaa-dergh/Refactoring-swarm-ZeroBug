def count_down(n):
	"""
	Counts down from the given positive integer n and prints each number.
	
	Args:
		n (int): The starting number for the countdown. It must be a positive integer.
	
	Raises:
		TypeError: If n is not an integer.
		ValueError: If n is not a positive integer.
	"""
	if not isinstance(n, int):
		raise TypeError("n must be an integer")
	if n <= 0:
		raise ValueError("n must be a positive integer")
	for i in range(n, 0, -1):
		print(i)