
inventory = []

def add_item(name, quantity, price):
    inventory.append({"name": name, "quantity": quantity, "price": price})
    print("Item added")

def remove_item(name):
    for item in inventory:
        if item["name"] == name:
            inventory.remove(item)
    print("Item removed")

def get_total_value():
    total = 0
    for item in inventory:
        total += item["quantity"] * item["price"]
    return total

def find_item(name):
    for item in inventory:
        if item["name"] == name:
            return item
    return "Not found"

def update_quantity(name, quantity):
    for item in inventory:
        if item["name"] == name:
            item["quantity"] = quantity
    print("Quantity updated")

def load_inventory(filename):
    f = open(filename, "r")
    lines = f.readlines()
    for line in lines:
        parts = line.split(",")
        add_item(parts[0], int(parts[1]), float(parts[2]))
    f.close()

def save_inventory(filename):
    f = open(filename, "w")
    for item in inventory:
        f.write(item["name"] + "," + str(item["quantity"]) + "," + str(item["price"]) + "\n")
    f.close()

def clear_inventory():
    global inventory
    inventory = []
    print("Inventory cleared")
