import sqlite3

DB_PATH = 'bot_memory.db'

def show_user_facts():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, fact FROM facts ORDER BY id')
    rows = c.fetchall()
    conn.close()
    if not rows:
        print("No user facts saved yet.")
        return
    print("\n=== FACTS ABOUT THE USER ===")
    for row in rows:
        print(f"[{row[0]}] {row[1]}")
    print()

def show_bot_facts():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, fact FROM bot_facts ORDER BY id')
    rows = c.fetchall()
    conn.close()
    if not rows:
        print("No bot facts saved yet.")
        return
    print("\n=== FACTS ABOUT THE BOT ===")
    for row in rows:
        print(f"[{row[0]}] {row[1]}")
    print()

def delete_user_fact(fact_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM facts WHERE id = ?', (fact_id,))
    conn.commit()
    conn.close()
    print(f"Deleted user fact #{fact_id}")

def delete_bot_fact(fact_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM bot_facts WHERE id = ?', (fact_id,))
    conn.commit()
    conn.close()
    print(f"Deleted bot fact #{fact_id}")

def add_user_fact(fact):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute('INSERT INTO facts (fact) VALUES (?)', (fact,))
        conn.commit()
        print(f"Added user fact: {fact}")
    except sqlite3.IntegrityError:
        print("That fact already exists.")
    conn.close()

def add_bot_fact(fact):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute('INSERT INTO bot_facts (fact) VALUES (?)', (fact,))
        conn.commit()
        print(f"Added bot fact: {fact}")
    except sqlite3.IntegrityError:
        print("That fact already exists.")
    conn.close()

def clear_history():
    confirm = input("Are you sure you want to wipe ALL conversation history? (yes/no): ")
    if confirm.lower() == 'yes':
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('DELETE FROM history')
        conn.commit()
        conn.close()
        print("History cleared.")

def main():
    while True:
        print("\n=== MEMORY MANAGER ===")
        print("1. View facts about the user")
        print("2. View facts about the bot")
        print("3. Delete a fact about the user")
        print("4. Delete a fact about the bot")
        print("5. Add a fact about the user manually")
        print("6. Add a fact about the bot manually")
        print("7. Clear conversation history")
        print("8. View conversation history")
        print("9. View memory summaries")
        print("10. Exit")
        choice = input("\nChoice: ").strip()

        if choice == '1':
            show_user_facts()
        elif choice == '2':
            show_bot_facts()
        elif choice == '3':
            show_user_facts()
            fact_id = input("Enter fact ID to delete: ").strip()
            if len(fact_id.split("-")) <= 1:
                fact_id = fact_id.split(" ")
                for id in fact_id:
                    delete_user_fact(int(id))
            else:
                for id in range(int(fact_id.split("-")[0]), int(fact_id.split("-")[1]) + 1):
                    delete_user_fact(id)
        elif choice == '4':
            show_bot_facts()
            fact_id = input("Enter fact ID to delete: ").strip()
            if len(fact_id.split("-")) <= 1:
                fact_id = fact_id.split(" ")
                for id in fact_id:
                    delete_bot_fact(int(id))
            else:
                for id in range(int(fact_id.split("-")[0]), int(fact_id.split("-")[1]) + 1):
                    delete_bot_fact(id)
        elif choice == '5':
            fact = input("Enter fact to add: ").strip()
            add_user_fact(fact)
        elif choice == '6':
            fact = input("Enter fact to add about the bot: ").strip()
            add_bot_fact(fact)
        elif choice == '7':
            clear_history()
        elif choice == '8':
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('SELECT role, content FROM history ORDER BY id')
            rows = c.fetchall()
            conn.close()
            print("\n=== CONVERSATION HISTORY ===")
            for row in rows:
                print(f"{row[0].capitalize()}: {row[1]}")
        elif choice == '9':
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('SELECT id, summary, timestamp FROM summaries ORDER BY id DESC')
            for row in c.fetchall():
                print(f"[{row[0]}] [{row[2]}]\n{row[1]}\n---")
            conn.close()
        elif choice == '10':
            break
        else:
            print("Invalid choice.")

if __name__ == "__main__":
    main()
