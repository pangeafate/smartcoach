import os
import json
import sqlite3

# Set USE_SQLITE to true for local persistent testing.
USE_SQLITE = os.environ.get("USE_SQLITE", "true").lower() == "true"

if USE_SQLITE:
    # Use a custom database path if provided (e.g., on Render use a persistent disk path).
    db_path = os.environ.get("DB_PATH", "/data/test.db")
    # Connect to (or create) a local SQLite database file.
    conn = sqlite3.connect(db_path, check_same_thread=False)
    cursor = conn.cursor()
    # Create tables if they don't exist (do NOT drop them every time)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS workouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            user_id INTEGER,
            workout_type TEXT,
            details TEXT
        )
    ''')
    conn.commit()
else:
    # In-memory storage for local testing.
    workouts = []
    users = []
    next_workout_id = 1
    next_user_id = 1

def initialize_db():
    """Initialize the database if necessary."""
    if USE_SQLITE:
        # Tables are created above with CREATE TABLE IF NOT EXISTS
        conn.commit()
    else:
        global workouts, users, next_workout_id, next_user_id
        if not users and not workouts:
            workouts = []
            users = []
            next_workout_id = 1
            next_user_id = 1

def add_user(username):
    if USE_SQLITE:
        cursor.execute("INSERT INTO users (username) VALUES (?)", (username,))
        conn.commit()
        return cursor.lastrowid
    else:
        global next_user_id
        user = {"id": next_user_id, "username": username}
        users.append(user)
        next_user_id += 1
        return user["id"]

def get_users():
    if USE_SQLITE:
        cursor.execute("SELECT id, username FROM users")
        rows = cursor.fetchall()
        return [{"id": row[0], "username": row[1]} for row in rows]
    else:
        return users

def add_workout(date, user_id, workout_type, details):
    if USE_SQLITE:
        details_json = json.dumps(details)
        cursor.execute("INSERT INTO workouts (date, user_id, workout_type, details) VALUES (?, ?, ?, ?)",
                       (date, user_id, workout_type, details_json))
        conn.commit()
    else:
        global next_workout_id
        workout = {
            "id": next_workout_id,
            "date": date,
            "user_id": user_id,
            "workout_type": workout_type,
            "details": details
        }
        workouts.append(workout)
        next_workout_id += 1

def get_all_workouts():
    if USE_SQLITE:
        cursor.execute("SELECT id, date, user_id, workout_type, details FROM workouts")
        rows = cursor.fetchall()
        workouts_list = []
        for row in rows:
            workout = {
                "id": row[0],
                "date": row[1],
                "user_id": row[2],
                "workout_type": row[3],
                "details": json.loads(row[4])
            }
            workouts_list.append(workout)
        return workouts_list
    else:
        return workouts

def delete_workout(workout_id, workout_type=None):
    if USE_SQLITE:
        if workout_type:
            cursor.execute("DELETE FROM workouts WHERE id = ? AND workout_type = ?", (workout_id, workout_type))
        else:
            cursor.execute("DELETE FROM workouts WHERE id = ?", (workout_id,))
        conn.commit()
    else:
        global workouts
        workouts = [w for w in workouts if w["id"] != workout_id]
