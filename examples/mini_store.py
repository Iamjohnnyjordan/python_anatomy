# Imports: Bring in JSON file tools and give ceil the clearer local name round_up.
import json
from math import ceil as round_up

# Dictionary: Connect each product name to its price.
prices = {"Milk": 2.99, "Bread": 1.50, "Eggs": 3.25}

# Set: Hold unique store categories without numbered positions.
categories = {"Dairy", "Bakery"}

# Tuple: Hold a fixed pair of location coordinates in order.
store_location = (2, 4)

# None: Show that no discount value has been provided yet.
discount = None

# Boolean: Remember whether the store is open with True or False.
store_open = True

# For loop: Visit every product key in the prices dictionary and print its price.
for product in prices:
    print(product, prices[product])

# List: Hold customer requests in the order they will be processed.
requests = ["Milk", "", "Bread", "Soap", "CHECKOUT", "Eggs"]

# List: Start an empty shopping cart that valid products can be added to.
cart = []

# Integer: Track the numbered position of the next request.
position = 0

# While loop: Process requests until the store closes, requests end, or checkout stops the loop.
while store_open and position < len(requests):
    product = requests[position]
    position += 1

    # If and continue: Skip a blank request and begin the next repetition.
    if not product:
        continue

    # If and break: Leave the loop when the customer requests checkout or quit.
    if product == "CHECKOUT" or product == "QUIT":
        break

    # If and continue: Skip products that are not keys in the prices dictionary.
    if product not in prices:
        continue

    # Method call: Add this valid product to the end of the cart list.
    cart.append(product)


# Function: Calculate and return the total price for a list of items.
def calculate_total(items, price_list):
    total = 0.0

    # For loop: Visit each cart item inside the function and add its known price.
    for product in items:
        if product in price_list:
            total = total + price_list[product]
    return total


# Function: Ask for a customer name and use Guest when the response is blank.
def ask_customer(default_name="Guest"):
    name = input("Your name: ")
    if not name:
        return default_name
    return name


# Class: Define the data and behavior shared by Receipt objects.
class Receipt:

    # __init__ method: Put the supplied items and total onto a new Receipt object.
    def __init__(self, items, total):
        self.items = items
        self.total = total

    # Method: Display this receipt object's items and total.
    def show(self):
        print("Items:", self.items)
        print("Total:", self.total)

    # Method: Save this receipt as JSON, read it back, and return the saved text.
    def save(self, filename="receipt.json"):

        # Raise: Signal an error when there are no receipt items to save.
        if not self.items:
            raise ValueError("Cannot save an empty receipt")

        # Dictionary: Prepare labeled receipt data for JSON output.
        payload = {"items": self.items, "total": self.total}

        # With and file output: Open the file safely and write the JSON data.
        with open(filename, "w", encoding="utf-8") as file:
            json.dump(payload, file)

        # With and file input: Open the file safely and read its text.
        with open(filename, "r", encoding="utf-8") as file:
            saved_text = file.read()
        return saved_text


# Function call and assignment: Calculate the cart total and store the returned value.
subtotal = calculate_total(cart, prices)

# If/elif/else: Choose one path based on whether a discount or cart total exists.
if discount is not None:
    subtotal = subtotal - discount
elif subtotal > 0:
    print("No discount applied")
else:
    print("Your cart is empty")

# Function call: Round the subtotal upward by using the imported round_up name.
rounded_total = round_up(subtotal)

# Object creation: Call the Receipt class to create one receipt object.
receipt = Receipt(cart, subtotal)

# Method call: Ask the receipt object to display itself.
receipt.show()

# Output: Print final store information for the customer.
print("Rounded up:", rounded_total)
print("Store location:", store_location)
print("Categories:", categories)

# Try/except/else/finally: Save safely, handle expected errors, and always finish checkout.
try:
    saved = receipt.save(filename="receipt.json")
except (OSError, ValueError) as error:
    print("Receipt could not be saved:", error)
else:
    print("Saved receipt:", saved)
finally:
    print("Checkout finished")
