from services.db_service import init_db, add_account

def main():
    init_db()
    add_account()

if __name__ == "__main__":
    main()
