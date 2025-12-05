from utils import greet
from helpers.helper import add_numbers

def main():
    greet("Student")
    result = add_numbers(5, 10)
    print(result)

# Call at module level too
greet("World")
print(add_numbers(1, 2))

if __name__ == "__main__":
    main()
