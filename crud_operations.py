"""
crud_operations.py
OWNER: Person 2

Purpose: Give the user a menu-driven way to Create, Read, Update, and
Delete event records in Redis. This is worth the most points under
"Functionality" in the rubric, so make sure every option actually works
against real data, not just placeholder text.

Depends on the schema Person 1 defines in data_loader.py. Talk to them
before writing this so your key names match.

TODO:
    - Fill in each CRUD function below using the schema from data_loader.py
    - Build out run_crud_menu() so a user can pick an option and see
      the result printed clearly
    - Add input validation so bad input doesn't crash the program
"""

from redis_config import get_redis_connection


def create_record(r, event_id, fields):
    """
    Adds a new event record to Redis.
    fields should be a dictionary of field name -> value pairs.

    TODO: implement using r.hset(f"event:{event_id}", mapping=fields)
    and update any relevant index sets.
    """
    pass


def read_record(r, event_id):
    """
    Retrieves and returns one event record by its id.

    TODO: implement using r.hgetall(f"event:{event_id}")
    Return None (or a clear message) if the record doesn't exist.
    """
    pass


def update_record(r, event_id, fields):
    """
    Updates one or more fields on an existing event record.
    fields should be a dictionary of field name -> new value.

    TODO: implement using r.hset(). Check the record exists first
    with r.exists() and handle the case where it doesn't.
    """
    pass


def delete_record(r, event_id):
    """
    Removes an event record from Redis, including cleaning it out of
    any index sets it was added to in data_loader.py.

    TODO: implement using r.delete() and r.srem() as needed.
    """
    pass


def run_crud_menu():
    """
    Displays a text menu (Create / Read / Update / Delete / Quit) in a
    loop, takes user input, and calls the matching function above.
    This is the function main.py will call.

    TODO: build out the loop and menu prompts.
    """
    r = get_redis_connection()
    while True:
        print("\n1. Create  2. Read  3. Update  4. Delete  5. Back to Main Menu")
        choice = input("Choose an option: ").strip()

        if choice == "1":
            pass  # TODO: gather input, call create_record()
        elif choice == "2":
            pass  # TODO: gather input, call read_record()
        elif choice == "3":
            pass  # TODO: gather input, call update_record()
        elif choice == "4":
            pass  # TODO: gather input, call delete_record()
        elif choice == "5":
            break
        else:
            print("Not a valid option, try again.")


if __name__ == "__main__":
    # Lets Person 2 test this file on its own without running main.py
    run_crud_menu()
