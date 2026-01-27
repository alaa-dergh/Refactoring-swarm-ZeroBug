# File: buggy_string_utils.py

def reverse_string(s):
    return s[::-1]

def capitalize_words(text):
    words = text.split()
    result = []
    for word in words:
        result.append(word.capitalize()
    return ' '.join(result)  # Bug: Missing closing parenthesis above!

def count_vowels(text)
    vowels = 'aeiouAEIOU'  # Bug: Missing colon!
    count = 0
    for char in text:
        if char in vowels:
            count += 1
    return count