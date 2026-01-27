# File: buggy_list_ops.py

def find_max(numbers):
    max_val = numbers[0]
    for num in numbers:
        if num > max_val
            max_val = num  # Bug: Missing colon!
    return max_val

def remove_duplicates(lst=[]):  # Bug: Mutable default!
    return list(set(lst))

def safe_get(lst, index):
    return lst[index]  # Bug: No bounds checking!
