from app.db.session import check_db_connection

if __name__ == "__main__":
    if check_db_connection():
        print("Database connection successful.")
    else:
        print("Database connection failed.")
