import sqlite3


# Create the database and tables
def create_tables():
    conn = sqlite3.connect("mentor_connect.db")
    cursor = conn.cursor()

    # Users table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'mentor', 'mentee')),
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL
        );
    """
    )

    # Mentor profiles table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS mentor_profiles (
            user_id INTEGER PRIMARY KEY,
            department TEXT,
            bio TEXT,
            expertise TEXT,
            mobile_no TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
    """
    )

    # Mentee profiles table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS mentee_profiles (
            user_id INTEGER PRIMARY KEY,
            department TEXT,
            semester TEXT,
            roll_no TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
    """
    )

    # Connections table
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS connections (
        mentor_id INTEGER,
        mentee_id INTEGER,
        status TEXT CHECK(status IN ('PENDING', 'ACCEPTED', 'REJECTED', 'TERMINATED')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- Added column
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- Optional: for tracking updates
        PRIMARY KEY (mentor_id, mentee_id),
        FOREIGN KEY(mentor_id) REFERENCES users(id),
        FOREIGN KEY(mentee_id) REFERENCES users(id)
    );
"""
    )

    # Posts table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
    """
    )

    # Comments table
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER,
        user_id INTEGER,
        content TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- Added column
        FOREIGN KEY(post_id) REFERENCES posts(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
"""
    )

    # Activities table
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS activities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        related_user_id INTEGER,  -- Added column
        activity_type TEXT,
        description TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(related_user_id) REFERENCES users(id)  -- Added foreign key
    );
"""
    )
    # Academic records table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS academic_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mentee_id INTEGER,
            semester TEXT NOT NULL,
            subject TEXT NOT NULL,
            grade TEXT NOT NULL,
            FOREIGN KEY(mentee_id) REFERENCES users(id)
        );
    """
    )

    # Meetings table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mentor_id INTEGER,
            mentee_id INTEGER,
            meeting_time TIMESTAMP,
            title TEXT,
            duration INTEGER,
            agenda TEXT,
            description TEXT,
            status TEXT CHECK(status IN ('SCHEDULED', 'COMPLETED', 'CANCELLED')) DEFAULT 'SCHEDULED',
            FOREIGN KEY(mentor_id) REFERENCES users(id),
            FOREIGN KEY(mentee_id) REFERENCES users(id)
        );
    """
    )

    # Ensure the 'created_at' column is added to posts if missing (already handled in app.py, but here for schema completeness)
    cursor.execute("PRAGMA table_info(posts);")
    columns = cursor.fetchall()
    if not any(column[1] == "created_at" for column in columns):
        cursor.execute(
            """ALTER TABLE posts ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;"""
        )

    # Ensure the mentee_profiles table has the mobile_no column
    cursor.execute("PRAGMA table_info(mentee_profiles);")
    columns = [column[1] for column in cursor.fetchall()]

    if "mobile_no" not in columns:
        cursor.execute("ALTER TABLE mentee_profiles ADD COLUMN mobile_no TEXT;")
    if "address" not in columns:
        cursor.execute("ALTER TABLE mentee_profiles ADD COLUMN address TEXT;")

    conn.commit()
    conn.close()


# Run the function to create tables
create_tables()

# Insert dummy mentee data into the users table
conn = sqlite3.connect("mentor_connect.db")
cursor = conn.cursor()
# hehe
from werkzeug.security import generate_password_hash
admin_password = generate_password_hash("admin123")
cursor.execute(
            "INSERT INTO users (email, password, role, first_name, last_name) VALUES (?, ?, ?, ?, ?)",
            (
                "admin@mentorconnect.com",
                admin_password,
                "admin",
                "System",
                "Administrator",
            ),
        )

cursor.executemany(
    """
    INSERT INTO users (email, password, role, first_name, last_name)
    VALUES (?, ?, ?, ?, ?);
    """,
    [
        ("john.doe@example.com", "hashed_password_1", "mentee", "John", "Doe"),
        ("jane.smith@example.com", "hashed_password_2", "mentee", "Jane", "Smith"),
        (
            "alice.johnson@example.com",
            "hashed_password_3",
            "mentee",
            "Alice",
            "Johnson",
        ),
    ],
)

# Get the auto-incremented IDs of the inserted users
cursor.execute(
    "SELECT id FROM users WHERE email IN (?, ?, ?);",
    ("john.doe@example.com", "jane.smith@example.com", "alice.johnson@example.com"),
)
user_ids = [row[0] for row in cursor.fetchall()]

# Insert corresponding data into the mentee_profiles table
cursor.executemany(
    """
    INSERT INTO mentee_profiles (user_id, department, semester, roll_no, mobile_no)
    VALUES (?, ?, ?, ?, ?);
    """,
    [
        (user_ids[0], "Computer Science", "6th", "CS2021001", "1234567890"),
        (user_ids[1], "Mechanical Engineering", "4th", "ME2021002", "9876543210"),
        (user_ids[2], "Electrical Engineering", "8th", "EE2021003", "5556667777"),
    ],
)

# Insert dummy data into the meetings table
cursor.executemany(
    """
    INSERT INTO meetings (mentor_id, mentee_id, meeting_time, title, duration, agenda, description, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """,
    [
        (
            1,
            2,
            "2025-05-15 10:00:00",
            "Project Discussion",
            60,
            "Discuss project milestones",
            "Meeting to discuss the progress of the mentee's project.",
            "SCHEDULED",
        ),
        (
            1,
            3,
            "2025-05-16 14:00:00",
            "Career Guidance",
            45,
            "Provide career advice",
            "Session to guide the mentee on career opportunities.",
            "SCHEDULED",
        ),
        (
            2,
            1,
            "2025-05-17 09:30:00",
            "Exam Preparation",
            30,
            "Discuss exam strategies",
            "Help the mentee prepare for upcoming exams.",
            "SCHEDULED",
        ),
        (
            3,
            1,
            "2025-05-18 11:00:00",
            "Skill Development",
            90,
            "Discuss skill-building activities",
            "Plan activities to improve technical and soft skills.",
            "SCHEDULED",
        ),
    ],
)

conn.commit()
conn.close()
