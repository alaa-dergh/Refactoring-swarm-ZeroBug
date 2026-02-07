import time
import os
import sys

# Named constant for better readability
THRESHOLD = 10

# Variable name following PEP 8 conventions
data_data = []

# Function to update X
def update_x(a):
    global X
    if a:
        return 1
    else:
        return -1

# Function to update data_data
def update_data_data(b):
    global data_data
    if b > THRESHOLD:
        for i in range(b):
            if i % 2 == 0:
                data_data.append(i)
            else:
                data_data.append(i * 999)
    else:
        pass

# Main function
def do_stuff(a, b, c):
    global X
    X += update_x(a)
    update_data_data(b)

X = 0
