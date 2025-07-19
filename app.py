from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    jsonify,
)
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash
import json
from datetime import datetime, timedelta
import random
import secrets
from flask_mail import Mail, Message

app = Flask(__name__)
app.secret_key = "mentor_connect_secret_key"
app.config["DATABASE"] = "mentor_connect.db"

app.config['MAIL_SERVER'] = 'smtp.gmail.com'  # or your SMTP server
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your_email@gmail.com'
app.config['MAIL_PASSWORD'] = 'your_email_password'
app.config['MAIL_DEFAULT_SENDER'] = 'your_email@gmail.com'

mail = Mail(app)

# Database initialization
def get_db():
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    return conn

def init_db():



# Create database if it doesn't exist
def create_database():
    if not os.path.exists(app.config["DATABASE"]):
        from create_tables import create_tables
        create_tables()  # Use Python logic to create tables
        print("Database created successfully!")

        # Add admin user if not exists
        conn = get_db()
        cursor = conn.cursor()
        admin_password = generate_password_hash("admin123")
        cursor.execute(
            "INSERT OR IGNORE INTO users (email, password, role, first_name, last_name) VALUES (?, ?, ?, ?, ?)",
            (
                "admin@mentorconnect.com",
                admin_password,
                "admin",
                "System",
                "Administrator",
            ),
        )
        conn.commit()
        conn.close()
        print("Admin user created successfully!")


# Helper functions
def is_logged_in():
    return "user_id" in session


def get_user_role():
    return session.get("role", None)


def require_login(role=None):
    if not is_logged_in():
        flash("Please log in to access this page", "error")
        return redirect(url_for("login"))

    if role and session.get("role") != role:
        flash("You do not have permission to access this page", "error")
        return redirect(url_for("dashboard"))

@app.template_filter('datetimeformat')
def datetimeformat(value, format='%Y-%m-%d %H:%M'):
    if isinstance(value, str):
        try:
            # Try parsing with T separator first
            dt = datetime.strptime(value, "%Y-%m-%dT%H:%M")
        except ValueError:
            # Fallback to database format
            dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return dt.strftime(format)
    return value.strftime(format)
    
# Routes
@app.route("/")
def index():
    if is_logged_in():
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        role = request.form["role"]

        conn = get_db()
        cursor = conn.cursor()
        user = cursor.execute(
            "SELECT * FROM users WHERE email = ? AND role = ?", (email, role)
        ).fetchone()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["email"] = user["email"]
            session["role"] = user["role"]
            session["name"] = f"{user['first_name']} {user['last_name']}"

            # Log activity
            cursor.execute(
                "INSERT INTO activities (user_id, activity_type, description) VALUES (?, ?, ?)",
                (user["id"], "LOGIN", "User signed in"),
            )
            conn.commit()

            flash("You have been logged in successfully!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid credentials. Please try again.", "error")

        conn.close()

    role = request.args.get("role", "mentee")
    return render_template(f"auth/login_{role}.html", role=role)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        first_name = request.form["first_name"]
        last_name = request.form["last_name"]
        email = request.form["email"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]
        role = request.form["role"]

        if password != confirm_password:
            flash("Passwords do not match!", "error")
            return redirect(url_for("signup", role=role))

        conn = get_db()
        cursor = conn.cursor()

        # Check if email already exists
        existing_user = cursor.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()

        if existing_user:
            flash("Email already registered!", "error")
            conn.close()
            return redirect(url_for("signup", role=role))

        # Create new user
        hashed_password = generate_password_hash(password)
        cursor.execute(
            "INSERT INTO users (email, password, role, first_name, last_name) VALUES (?, ?, ?, ?, ?)",
            (email, hashed_password, role, first_name, last_name),
        )

        user_id = cursor.lastrowid

        # Create profile based on role
        if role == "mentor":
            department = request.form.get("department", "")
            cursor.execute(
                "INSERT INTO mentor_profiles (user_id, department) VALUES (?, ?)",
                (user_id, department),
            )
        elif role == "mentee":
            department = request.form.get("department", "")
            semester = request.form.get("semester", "")
            roll_no = request.form.get("roll_no", "")
            cursor.execute(
                "INSERT INTO mentee_profiles (user_id, department, semester, roll_no) VALUES (?, ?, ?, ?)",
                (user_id, department, semester, roll_no),
            )

        conn.commit()
        conn.close()

        flash("Account created successfully! You can now log in.", "success")
        return redirect(url_for("login", role=role))

    role = request.args.get("role", "mentee")
    return render_template(f"auth/signup_{role}.html", role=role)


@app.route("/mentee/meetings")
def mentee_meetings():
    if not is_logged_in() or session.get("role") != "mentee":
        flash("You do not have permission to access this page", "error")
        return redirect(url_for("index"))

    user_id = session.get("user_id")
    conn = get_db()
    cursor = conn.cursor()

    # Get all meetings
    meetings = cursor.execute(
        """
        SELECT m.*, u.first_name AS mentor_first_name, u.last_name AS mentor_last_name
        FROM meetings m
        JOIN users u ON m.mentor_id = u.id
        WHERE m.mentee_id = ?
        ORDER BY m.meeting_time DESC
        """,
        (user_id,),
    ).fetchall()

    # Separate into upcoming and past meetings
    upcoming_meetings = []
    past_meetings = []
    
    for meeting in meetings:
        # Handle both datetime formats
        meeting_time_str = meeting["meeting_time"]
        try:
            # Try parsing with T separator
            meeting_time = datetime.strptime(meeting_time_str, "%Y-%m-%dT%H:%M")
        except ValueError:
            # Fallback to space separator
            meeting_time = datetime.strptime(meeting_time_str, "%Y-%m-%d %H:%M:%S")
            
        if meeting_time > datetime.now():
            upcoming_meetings.append(meeting)
        else:
            past_meetings.append(meeting)

    conn.close()

    return render_template(
        "mentee/meetings.html",
        upcoming_meetings=upcoming_meetings,
        past_meetings=past_meetings,
    )
@app.route("/logout")
def logout():
    if is_logged_in():
        user_id = session.get("user_id")
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO activities (user_id, activity_type, description) VALUES (?, ?, ?)",
            (user_id, "LOGOUT", "User signed out"),
        )
        conn.commit()
        conn.close()

    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


@app.route("/dashboard")
def dashboard():
    if not is_logged_in():
        return redirect(url_for("login"))

    role = session.get("role")
    user_id = session.get("user_id")

    if role == "admin":
        return redirect(url_for("admin_dashboard"))
    elif role == "mentor":
        return redirect(url_for("mentor_dashboard"))
    elif role == "mentee":
        return redirect(url_for("mentee_dashboard"))

    return redirect(url_for("index"))


@app.route("/admin/dashboard")
def admin_dashboard():
    if not is_logged_in() or session.get("role") != "admin":
        flash("You do not have permission to access this page", "error")
        return redirect(url_for("index"))

    conn = get_db()
    cursor = conn.cursor()

    # Get counts
    mentor_count = cursor.execute(
        'SELECT COUNT(*) FROM users WHERE role = "mentor"'
    ).fetchone()[0]
    mentee_count = cursor.execute(
        'SELECT COUNT(*) FROM users WHERE role = "mentee"'
    ).fetchone()[0]
    connection_count = cursor.execute("SELECT COUNT(*) FROM connections").fetchone()[0]

    # Get recent activities
    activities = cursor.execute(
        """
        SELECT a.*, u.first_name, u.last_name, u.role 
        FROM activities a
        JOIN users u ON a.user_id = u.id
        ORDER BY a.timestamp DESC LIMIT 10
    """
    ).fetchall()

    conn.close()

    return render_template(
        "admin/dashboard.html",
        mentor_count=mentor_count,
        mentee_count=mentee_count,
        connection_count=connection_count,
        activities=activities,
    )


# new
def ensure_created_at_column():
    # ...existing code...
    pass


@app.route("/mentor/dashboard")
def mentor_dashboard():
    if not is_logged_in() or session.get("role") != "mentor":
        flash("You do not have permission to access this page", "error")
        return redirect(url_for("index"))

    user_id = session.get("user_id")
    conn = get_db()
    cursor = conn.cursor()

    # Get mentor's mentees
    mentees = cursor.execute(
        """
        SELECT u.id, u.first_name, u.last_name, mp.department, mp.semester, mp.roll_no
        FROM connections c
        JOIN users u ON c.mentee_id = u.id
        JOIN mentee_profiles mp ON u.id = mp.user_id
        WHERE c.mentor_id = ? AND c.status = 'ACCEPTED'
        """,
        (user_id,),
    ).fetchall()

    # Get pending mentorship requests
    pending_requests = cursor.execute(
        """
        SELECT u.id, u.first_name, u.last_name, mp.department, mp.semester, mp.roll_no
        FROM connections c
        JOIN users u ON c.mentee_id = u.id
        JOIN mentee_profiles mp ON u.id = mp.user_id
        WHERE c.mentor_id = ? AND c.status = 'PENDING'
        """,
        (user_id,),
    ).fetchall()

    # Get counts
    mentee_count = len(mentees)
    post_count = cursor.execute(
        "SELECT COUNT(*) FROM posts WHERE user_id = ?", (user_id,)
    ).fetchone()[0]
    comment_count = cursor.execute(
        "SELECT COUNT(*) FROM comments WHERE user_id = ?", (user_id,)
    ).fetchone()[0]

    # Fetch all scheduled meetings for this mentor
    all_meetings = cursor.execute(
        """
        SELECT m.id, m.meeting_time, u.first_name, u.last_name
        FROM meetings m
        JOIN users u ON m.mentee_id = u.id
        WHERE m.mentor_id = ? AND m.status = 'SCHEDULED'
        ORDER BY m.meeting_time
        """,
        (user_id,),
    ).fetchall()

    upcoming_meetings = []
    past_meetings = []
    now = datetime.now()

    for meeting in all_meetings:
        meeting_time_str = meeting["meeting_time"]
        try:
            mt = datetime.strptime(meeting_time_str, "%Y-%m-%dT%H:%M")
        except ValueError:
            mt = datetime.strptime(meeting_time_str, "%Y-%m-%d %H:%M:%S")
        if mt > now:
            upcoming_meetings.append(meeting)
        else:
            past_meetings.append(meeting)

    # Notification for next meeting within 15 minutes
    next_meeting_alert = None
    for meeting in upcoming_meetings:
        try:
            mt = datetime.strptime(meeting["meeting_time"], "%Y-%m-%dT%H:%M")
        except ValueError:
            mt = datetime.strptime(meeting["meeting_time"], "%Y-%m-%d %H:%M:%S")
        if 0 <= (mt - now).total_seconds() <= 900: # 15 minutes
            next_meeting_alert = f"You have a meeting with {meeting['first_name']} {meeting['last_name']} at {mt.strftime('%H:%M')}."
            break

    # Fetch activities from the last 7 days
    activities = cursor.execute(
        """
        SELECT activity_type, description, timestamp
        FROM activities
        WHERE user_id = ? AND timestamp >= datetime('now', '-7 days')
        ORDER BY timestamp DESC
        """,
        (user_id,),
    ).fetchall()

    # Prepare chart data
    chart_data = {
        "labels": ["Day 1", "Day 2", "Day 3", "Day 4", "Day 5", "Day 6", "Day 7"],
        "meetings": [2, 3, 1, 0, 4, 2, 1],  # Replace with actual data from the database
        "posts": [1, 0, 2, 1, 3, 0, 1],     # Replace with actual data from the database
        "comments": [0, 1, 0, 2, 1, 3, 0],  # Replace with actual data from the database
    }

    conn.close()

    return render_template(
        "mentor/dashboard.html",
        mentees=mentees,
        pending_requests=pending_requests,
        mentee_count=mentee_count,
        post_count=post_count,
        comment_count=comment_count,
        upcoming_meetings=upcoming_meetings,
        past_meetings=past_meetings,
        activities=activities,
        chart_data=chart_data,
        next_meeting_alert=next_meeting_alert,
    )


@app.route("/mentee/dashboard")
def mentee_dashboard():
    if not is_logged_in() or session.get("role") != "mentee":
        flash("You do not have permission to access this page", "error")
        return redirect(url_for("index"))

    user_id = session.get("user_id")
    conn = get_db()
    cursor = conn.cursor()

    # Get mentee's mentors
    mentors = cursor.execute(
        """
        SELECT u.id, u.first_name, u.last_name, mp.department
        FROM connections c
        JOIN users u ON c.mentor_id = u.id
        JOIN mentor_profiles mp ON u.id = mp.user_id
        WHERE c.mentee_id = ? AND c.status = 'ACCEPTED'
    """,
        (user_id,),
    ).fetchall()

    # Get counts
    mentor_count = len(mentors)
    post_count = cursor.execute(
        "SELECT COUNT(*) FROM posts WHERE user_id = ?", (user_id,)
    ).fetchone()[0]
    comment_count = cursor.execute(
        "SELECT COUNT(*) FROM comments WHERE user_id = ?", (user_id,)
    ).fetchone()[0]

    # Get upcoming meetings
    upcoming_meetings = cursor.execute(
        """
        SELECT m.id as id, m.*, u.first_name, u.last_name
        FROM meetings m
        JOIN users u ON m.mentor_id = u.id
        WHERE m.mentee_id = ? AND m.meeting_time > datetime('now')
        ORDER BY m.meeting_time
        LIMIT 5
    """,
        (user_id,),
    ).fetchall()

    # Get activities
    activities = cursor.execute(
        """
        SELECT a.*, u.first_name, u.last_name
        FROM activities a
        JOIN users u ON a.user_id = u.id
        WHERE (a.user_id = ? OR a.related_user_id = ?)
        ORDER BY a.timestamp DESC
        LIMIT 10
    """,
        (user_id, user_id),
    ).fetchall()

    # Get mentee profile and academic records
    profile = cursor.execute(
        """
        SELECT mp.*, u.first_name, u.last_name, u.email
        FROM mentee_profiles mp
        JOIN users u ON mp.user_id = u.id
        WHERE mp.user_id = ?
    """,
        (user_id,),
    ).fetchone()

    academic_records = cursor.execute(
        """
        SELECT * FROM academic_records
        WHERE mentee_id = ?
        ORDER BY semester
    """,
        (user_id,),
    ).fetchall()

    # Generate chart data for the last 30 days
    chart_data = {"labels": [], "meetings": [], "posts": [], "comments": []}

    for i in range(30, 0, -1):
        date = (datetime.now() - timedelta(days=i)).strftime("%d %b")
        chart_data["labels"].append(date)

        day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        # Get scheduled meetings
        scheduled_meetings = cursor.execute(
            """
        SELECT m.id as id, m.title, m.meeting_time, m.duration, u.first_name AS mentor_first_name, u.last_name AS mentor_last_name
        FROM meetings m
        JOIN users u ON m.mentor_id = u.id
        WHERE m.mentee_id = ? AND m.status = 'SCHEDULED'
        ORDER BY m.meeting_time
        """,
            (user_id,),
        ).fetchall()

        # Count meetings for the day
        meeting_count = cursor.execute(
            """
            SELECT COUNT(*) FROM meetings 
            WHERE mentee_id = ? AND date(meeting_time) = ?
        """,
            (user_id, day),
        ).fetchone()[0]
        chart_data["meetings"].append(meeting_count)

        # Count posts for the day
        post_count_day = cursor.execute(
            """
            SELECT COUNT(*) FROM posts 
            WHERE user_id = ? AND date(created_at) = ?
        """,
            (user_id, day),
        ).fetchone()[0]
        chart_data["posts"].append(post_count_day)

        # Count comments for the day
        comment_count_day = cursor.execute(
            """
            SELECT COUNT(*) FROM comments 
            WHERE user_id = ? AND date(created_at) = ?
        """,
            (user_id, day),
        ).fetchone()[0]
        chart_data["comments"].append(comment_count_day)

    # Get all meetings for the mentee with mentor names
    all_meetings = cursor.execute(
        """
        SELECT m.*, u.first_name AS mentor_first_name, u.last_name AS mentor_last_name
        FROM meetings m
        JOIN users u ON m.mentor_id = u.id
        WHERE m.mentee_id = ?
        ORDER BY m.meeting_time DESC
        """,
        (user_id,),
    ).fetchall()

    # Separate into upcoming and held meetings
    upcoming_meetings = []
    held_meetings = []
    now = datetime.now()
    for meeting in all_meetings:
        meeting_time_str = meeting["meeting_time"]
        try:
            meeting_time = datetime.strptime(meeting_time_str, "%Y-%m-%dT%H:%M")
        except ValueError:
            meeting_time = datetime.strptime(meeting_time_str, "%Y-%m-%d %H:%M:%S")
        if meeting_time > now:
            upcoming_meetings.append(meeting)
        else:
            held_meetings.append(meeting)

    conn.close()

    return render_template(
        "mentee/dashboard.html",
        mentors=mentors,
        mentor_count=mentor_count,
        post_count=post_count,
        comment_count=comment_count,
        upcoming_meetings=upcoming_meetings,
        held_meetings=held_meetings,
        activities=activities,
        profile=profile,
        academic_records=academic_records,
        chart_data=json.dumps(chart_data),
    )


@app.route("/mentor/mentees")
def mentor_mentees():
    if not is_logged_in() or session.get("role") != "mentor":
        flash("You do not have permission to view this page", "error")
        return redirect(url_for("index"))

    conn = get_db()
    cursor = conn.cursor()

    mentor_id = session.get("user_id")

    cursor.execute("""
        SELECT u.id, u.first_name, u.last_name, mp.department, mp.semester, 
               mp.roll_no, mp.mobile_no, c.status
        FROM users u
        JOIN mentee_profiles mp ON u.id = mp.user_id
        JOIN connections c ON c.mentee_id = u.id
        WHERE c.mentor_id = ? AND c.status = 'ACCEPTED'
    """, (mentor_id,))
    
    mentees = cursor.fetchall()
    conn.close()
    print(mentees)

    return render_template(
        "mentor/mentees.html",
        mentees=mentees,
        now=datetime.now()
    )


@app.route("/mentor/mentee/<int:mentee_id>")
def mentor_view_mentee(mentee_id):
    if not is_logged_in() or session.get("role") != "mentor":
        flash("You do not have permission to access this page", "error")
        return redirect(url_for("index"))

    user_id = session.get("user_id")
    conn = get_db()
    cursor = conn.cursor()

    # Check if mentor is connected to mentee
    connection = cursor.execute(
        """
        SELECT * FROM connections
        WHERE mentor_id = ? AND mentee_id = ?
    """,
        (user_id, mentee_id),
    ).fetchone()

    if not connection:
        flash("You do not have permission to view this mentee", "error")
        conn.close()
        return redirect(url_for("mentor_mentees"))

    # Get mentee details
    mentee = cursor.execute(
        """
        SELECT mp.*, u.first_name, u.last_name, u.email
        FROM mentee_profiles mp
        JOIN users u ON mp.user_id = u.id
        WHERE mp.user_id = ?
    """,
        (mentee_id,),
    ).fetchone()

    # Get academic records
    academic_records = cursor.execute(
        """
        SELECT * FROM academic_records
        WHERE mentee_id = ?
        ORDER BY semester
    """,
        (mentee_id,),
    ).fetchall()

    # Get meetings
    meetings = cursor.execute(
        """
        SELECT * FROM meetings
        WHERE mentor_id = ? AND mentee_id = ?
        ORDER BY meeting_time DESC
        """,
        (user_id, mentee_id),
    ).fetchall()

    # Convert meeting_time to datetime object for each meeting
    meetings = [
        dict(meeting, meeting_time=(
            datetime.strptime(meeting["meeting_time"], "%Y-%m-%dT%H:%M")
            if "T" in meeting["meeting_time"]
            else datetime.strptime(meeting["meeting_time"], "%Y-%m-%d %H:%M:%S")
        ))
        for meeting in meetings
    ]

    conn.close()

    return render_template(
        "mentor/view_mentee.html",
        mentee=mentee,
        academic_records=academic_records,
        meetings=meetings,
        now=datetime.now()
    )


@app.route("/mentee/mentors")
def mentee_mentors():
    if not is_logged_in() or session.get("role") != "mentee":
        flash("You do not have permission to access this page", "error")
        return redirect(url_for("index"))

    user_id = session.get("user_id")
    conn = get_db()
    cursor = conn.cursor()

    # Get current mentors
    current_mentors = cursor.execute(
        """
        SELECT u.id, u.first_name, u.last_name, mp.department, c.status, c.created_at
        FROM connections c
        JOIN users u ON c.mentor_id = u.id
        JOIN mentor_profiles mp ON u.id = mp.user_id
        WHERE c.mentee_id = ? AND c.status = 'ACCEPTED'
    """,
        (user_id,),
    ).fetchall()

    # Get available mentors (not already connected)
    connected_mentor_ids = [m["id"] for m in current_mentors]
    placeholder = (
        ",".join(["?" for _ in connected_mentor_ids]) if connected_mentor_ids else "0"
    )

    query = f"""
        SELECT u.id, u.first_name, u.last_name, mp.department, mp.bio
        FROM users u
        JOIN mentor_profiles mp ON u.id = mp.user_id
        WHERE u.role = 'mentor' AND u.id NOT IN ({placeholder})
    """

    available_mentors = cursor.execute(query, connected_mentor_ids).fetchall()

    conn.close()

    return render_template(
        "mentee/mentors.html",
        current_mentors=current_mentors,
        available_mentors=available_mentors,
    )


@app.route("/profile")
def profile():
    if not is_logged_in():
        return redirect(url_for("login"))

    role = session.get("role")
    user_id = session.get("user_id")

    conn = get_db()
    cursor = conn.cursor()

    # Get user details
    user = cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    # Get profile details based on role
    profile = None
    if role == "mentor":
        profile = cursor.execute(
            "SELECT * FROM mentor_profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
    elif role == "mentee":
        profile = cursor.execute(
            "SELECT * FROM mentee_profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
        academic_records = cursor.execute(
            "SELECT * FROM academic_records WHERE mentee_id = ? ORDER BY semester",
            (user_id,),
        ).fetchall()

    conn.close()

    if role == "admin":
        return render_template("admin/profile.html", user=user)
    elif role == "mentor":
        return render_template("mentor/profile.html", user=user, profile=profile)
    elif role == "mentee":
        return render_template(
            "mentee/profile.html",
            user=user,
            profile=profile,
            academic_records=academic_records,
        )

    return redirect(url_for("index"))


@app.route("/profile/edit", methods=["GET", "POST"])
def edit_profile():
    if not is_logged_in():
        return redirect(url_for("login"))

    user_id = session.get("user_id")
    role = session.get("role")

    if request.method == "POST":
        conn = get_db()
        cursor = conn.cursor()

        # Update user table
        first_name = request.form["first_name"]
        last_name = request.form["last_name"]
        email = request.form["email"]

        cursor.execute(
            """
            UPDATE users 
            SET first_name = ?, last_name = ?, email = ?
            WHERE id = ?
        """,
            (first_name, last_name, email, user_id),
        )

        # Update role-specific profile
        if role == "mentor":
            department = request.form["department"]
            bio = request.form.get("bio", "")
            expertise = request.form.get("expertise", "")
            mobile_no = request.form.get("mobile_no", "")

            cursor.execute(
                """
                UPDATE mentor_profiles
                SET department = ?, bio = ?, expertise = ?, mobile_no = ?
                WHERE user_id = ?
            """,
                (department, bio, expertise, mobile_no, user_id),
            )

        elif role == "mentee":
            department = request.form["department"]
            semester = request.form["semester"]
            roll_no = request.form["roll_no"]
            mobile_no = request.form.get("mobile_no", "")
            address = request.form.get("address", "")

            cursor.execute(
                """
                UPDATE mentee_profiles
                SET department = ?, semester = ?, roll_no = ?, mobile_no = ?, address = ?
                WHERE user_id = ?
            """,
                (department, semester, roll_no, mobile_no, address, user_id),
            )

        conn.commit()
        conn.close()

        flash("Profile updated successfully!", "success")
        return redirect(url_for("profile"))

    conn = get_db()
    cursor = conn.cursor()

    # Get user and profile data
    user = cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    profile = None
    if role == "mentor":
        profile = cursor.execute(
            "SELECT * FROM mentor_profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
    elif role == "mentee":
        profile = cursor.execute(
            "SELECT * FROM mentee_profiles WHERE user_id = ?", (user_id,)
        ).fetchone()

    conn.close()

    if role == "admin":
        return render_template("admin/edit_profile.html", user=user)
    elif role == "mentor":
        return render_template("mentor/edit_profile.html", user=user, profile=profile)
    elif role == "mentee":
        return render_template("mentee/edit_profile.html", user=user, profile=profile)

    return redirect(url_for("index"))


# Connection management routes
@app.route("/mentee/request_mentor/<int:mentor_id>", methods=["POST"])
def request_mentor(mentor_id):
    if not is_logged_in() or session.get("role") != "mentee":
        flash("You do not have permission for this action", "error")
        return redirect(url_for("index"))

    mentee_id = session.get("user_id")

    conn = get_db()
    cursor = conn.cursor()

    # Check if connection already exists
    existing = cursor.execute(
        """
        SELECT * FROM connections
        WHERE mentor_id = ? AND mentee_id = ?
    """,
        (mentor_id, mentee_id),
    ).fetchone()

    if existing:
        flash("You have already requested or connected with this mentor", "error")
        conn.close()
        return redirect(url_for("mentee_mentors"))

    # Create connection request
    cursor.execute(
        """
        INSERT INTO connections (mentor_id, mentee_id, status, created_at)
        VALUES (?, ?, 'PENDING', datetime('now'))
    """,
        (mentor_id, mentee_id),
    )

    # Add activity
    cursor.execute(
        """
        INSERT INTO activities (user_id, related_user_id, activity_type, description)
        VALUES (?, ?, 'CONNECTION_REQUEST', 'Requested mentorship connection')
    """,
        (mentee_id, mentor_id),
    )

    conn.commit()
    conn.close()

    flash("Mentorship request sent successfully!", "success")
    return redirect(url_for("mentee_mentors"))


@app.route("/mentor/accept_mentee/<int:mentee_id>", methods=["POST"])
def accept_mentee(mentee_id):
    if not is_logged_in() or session.get("role") != "mentor":
        flash("You do not have permission for this action", "error")
        return redirect(url_for("index"))

    mentor_id = session.get("user_id")

    conn = get_db()
    cursor = conn.cursor()

    # Update connection status
    cursor.execute(
        """
        UPDATE connections
        SET status = 'ACCEPTED', updated_at = datetime('now')
        WHERE mentor_id = ? AND mentee_id = ? AND status = 'PENDING'
    """,
        (mentor_id, mentee_id),
    )

    # Add activity
    cursor.execute(
        """
        INSERT INTO activities (user_id, related_user_id, activity_type, description)
        VALUES (?, ?, 'CONNECTION_ACCEPTED', 'Accepted mentorship connection')
    """,
        (mentor_id, mentee_id),
    )

    conn.commit()
    conn.close()

    flash("Mentee accepted successfully!", "success")
    return redirect(url_for("mentor_mentees"))


@app.route("/mentor/reject_mentee/<int:mentee_id>", methods=["POST"])
def reject_mentee(mentee_id):
    if not is_logged_in() or session.get("role") != "mentor":
        flash("You do not have permission to this action", "error")
        return redirect(url_for("index"))

    mentor_id = session.get("user_id")

    conn = get_db()
    cursor = conn.cursor()

    # Update connection status
    cursor.execute(
        """
        UPDATE connections
        SET status = 'REJECTED', updated_at = datetime('now')
        WHERE mentor_id = ? AND mentee_id = ? AND status = 'PENDING'
    """,
        (mentor_id, mentee_id),
    )

    # Add activity
    cursor.execute(
        """
        INSERT INTO activities (user_id, related_user_id, activity_type, description)
        VALUES (?, ?, 'CONNECTION_REJECTED', 'Rejected mentorship connection')
    """,
        (mentor_id, mentee_id),
    )

    conn.commit()
    conn.close()

    flash("Mentee rejected successfully", "success")
    return redirect(url_for("mentor_mentees"))


@app.route("/mentor/remove_mentee/<int:mentee_id>", methods=["POST"])
def remove_mentee(mentee_id):
    if not is_logged_in() or session.get("role") != "mentor":
        flash("You do not have permission to this action", "error")
        return redirect(url_for("index"))

    mentor_id = session.get("user_id")

    conn = get_db()
    cursor = conn.cursor()

    # Update connection status
    cursor.execute(
        """
        UPDATE connections
        SET status = 'TERMINATED', updated_at = datetime('now')
        WHERE mentor_id = ? AND mentee_id = ? AND status = 'ACCEPTED'
    """,
        (mentor_id, mentee_id),
    )

    # Add activity
    cursor.execute(
        """
        INSERT INTO activities (user_id, related_user_id, activity_type, description)
        VALUES (?, ?, 'CONNECTION_TERMINATED', 'Terminated mentorship connection')
    """,
        (mentor_id, mentee_id),
    )

    conn.commit()
    conn.close()

    flash("Mentee removed successfully", "success")
    return redirect(url_for("mentor_mentees"))


# Meeting management routes


# Existing route: Schedule a meeting with a specific mentee
@app.route("/mentor/schedule_meeting/<int:mentee_id>", methods=["GET", "POST"])
def schedule_meeting_with_mentee(mentee_id=0):
    if not is_logged_in() or session.get("role") != "mentor":
        flash("You do not have permission to this action", "error")
        flash("You do not have permission to this action", "error")
        return redirect(url_for("index"))

    mentor_id = session.get("user_id")
    conn = get_db()
    cursor = conn.cursor()

    # If mentee_id is 0, redirect to mentees list or show an error
    if mentee_id == 0:
        flash("Please select a mentee to schedule a meeting.", "error")
        conn.close()
        return redirect(url_for("mentor_mentees"))

    # Check if mentor is connected to mentee
    connection = cursor.execute(
        """
        SELECT * FROM connections
        WHERE mentor_id = ? AND mentee_id = ? AND status = 'ACCEPTED'
        """,
        (mentor_id, mentee_id),
    ).fetchone()

    if not connection:
        flash("You cannot schedule a meeting with this mentee", "error")
        conn.close()
        return redirect(url_for("mentor_mentees"))

    if request.method == "POST":
        title = request.form["title"]
        meeting_time = request.form["meeting_time"]
        duration = request.form["duration"]
        agenda = request.form.get("agenda", "")

        # Create meeting
        cursor.execute(
            """
            INSERT INTO meetings (mentor_id, mentee_id, title, meeting_time, duration, agenda, status)
            VALUES (?, ?, ?, ?, ?, ?, 'SCHEDULED')
            """,
            (mentor_id, mentee_id, title, meeting_time, duration, agenda),
        )

        # Add activity
        cursor.execute(
            """
            INSERT INTO activities (user_id, related_user_id, activity_type, description)
            VALUES (?, ?, 'MEETING_SCHEDULED', 'Scheduled a new meeting')
            """,
            (mentor_id, mentee_id),
        )

        conn.commit()
        conn.close()

        flash("Meeting scheduled successfully", "success")
        return redirect(url_for("mentor_view_mentee", mentee_id=mentee_id))

    # Get mentee information
    mentee = cursor.execute(
        """
        SELECT u.first_name, u.last_name, mp.department, mp.semester
        FROM users u
        JOIN mentee_profiles mp ON u.id = mp.user_id
        WHERE u.id = ?
        """,
        (mentee_id,),
    ).fetchone()

    conn.close()

    return render_template(
        "mentor/schedule_meeting.html", mentee=mentee, mentee_id=mentee_id
    )


# New route: Schedule a meeting with mentee selection
@app.route("/mentor/schedule_meeting", methods=["GET", "POST"])
def schedule_meeting():
    if not is_logged_in() or session.get("role") != "mentor":
        flash("You do not have permission to this action", "error")
        flash("You do not have permission to this action", "error")
        return redirect(url_for("index"))

    mentor_id = session.get("user_id")
    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        mentee_id = request.form.get("mentee_id") or request.args.get("mentee_id")
        title = request.form["title"]
        meeting_time = request.form["meeting_time"]
        duration = request.form["duration"]
        agenda = request.form.get("agenda", "")

        # Create meeting
        cursor.execute(
            """
            INSERT INTO meetings (mentor_id, mentee_id, title, meeting_time, duration, agenda, status)
            VALUES (?, ?, ?, ?, ?, ?, 'SCHEDULED')
            """,
            (mentor_id, mentee_id, title, meeting_time, duration, agenda),
        )

        conn.commit()
        conn.close()

        flash("Meeting scheduled successfully", "success")
        return redirect(url_for("mentor_dashboard"))

    # Fetch mentees connected to the mentor
    mentees = cursor.execute(
        """
        SELECT u.id, u.first_name, u.last_name, mp.department, mp.semester
        FROM connections c
        JOIN users u ON c.mentee_id = u.id
        JOIN mentee_profiles mp ON u.id = mp.user_id
        WHERE c.mentor_id = ? AND c.status = 'ACCEPTED'
        """,
        (mentor_id,),
    ).fetchall()

    mentee_id = request.args.get("mentee_id")
    mentee = None
    if mentee_id:
        mentee = cursor.execute(
            """
            SELECT u.first_name, u.last_name, mp.department, mp.semester
            FROM users u
            JOIN mentee_profiles mp ON u.id = mp.user_id
            WHERE u.id = ?
            """,
            (mentee_id,),
        ).fetchone()

    conn.close()

    return render_template(
        "mentor/schedule_meeting.html", mentees=mentees, mentee=mentee,mentee_id=mentee_id
    )


@app.route("/mentor/start_meeting/<int:meeting_id>")
def start_meeting(meeting_id):
    if not is_logged_in() or session.get("role") != "mentor":
        flash("You do not have permission to start this meeting", "error")
        return redirect(url_for("index"))

    conn = get_db()
    cursor = conn.cursor()
    meeting = cursor.execute(
        "SELECT * FROM meetings WHERE id = ? AND mentor_id = ?", (meeting_id, session["user_id"])
    ).fetchone()

    mentee = None
    if meeting:
        mentee = cursor.execute(
            "SELECT first_name, last_name FROM users WHERE id = ?", (meeting["mentee_id"],)
        ).fetchone()
    conn.close()

    if not meeting or not mentee:
        flash("Meeting not found or access denied.", "error")
        return redirect(url_for("mentor_dashboard"))

    mentee_name = f"{mentee['first_name']} {mentee['last_name']}"

    return render_template("mentor/start_meeting.html", meeting=meeting, mentee_name=mentee_name)


@app.route("/mentor/meeting/<int:meeting_id>/agenda", methods=["GET", "POST"])
def mentor_meeting_agenda(meeting_id):
    if not is_logged_in() or session.get("role") != "mentor":
        flash("You do not have permission to access this page", "error")
        return redirect(url_for("index"))

    conn = get_db()
    cursor = conn.cursor()
    meeting = cursor.execute(
        "SELECT * FROM meetings WHERE id = ? AND mentor_id = ?", (meeting_id, session["user_id"])
    ).fetchone()

    if not meeting:
        conn.close()
        flash("Meeting not found or access denied.", "error")
        return redirect(url_for("mentor_dashboard"))

    # Check if meeting is held (past)
    meeting_time_str = meeting["meeting_time"]
    try:
        mt = datetime.strptime(meeting_time_str, "%Y-%m-%dT%H:%M")
    except ValueError:
        mt = datetime.strptime(meeting_time_str, "%Y-%m-%d %H:%M:%S")
    if mt > datetime.now():
        conn.close()
        flash("You can only add agenda for held meetings.", "error")
        return redirect(url_for("mentor_dashboard"))

    if request.method == "POST":
        agenda = request.form.get("agenda", "")
        cursor.execute(
            "UPDATE meetings SET agenda = ? WHERE id = ?", (agenda, meeting_id)
        )
        conn.commit()
        conn.close()
        flash("Agenda updated successfully!", "success")
        return redirect(url_for("mentor_dashboard"))

    conn.close()
    return render_template("mentor/meeting_agenda.html", meeting=meeting)


@app.route("/mentee/meeting/<int:meeting_id>/agenda")
def mentee_meeting_agenda(meeting_id):
    if not is_logged_in() or session.get("role") != "mentee":
        flash("You do not have permission to access this page", "error")
        return redirect(url_for("index"))

    conn = get_db()
    cursor = conn.cursor()
    meeting = cursor.execute(
        "SELECT * FROM meetings WHERE id = ? AND mentee_id = ?", (meeting_id, session["user_id"])
    ).fetchone()
    conn.close()

    if not meeting:
        flash("Meeting not found or access denied.", "error")
        return redirect(url_for("mentee_dashboard"))

    return render_template("mentee/meeting_agenda.html", meeting=meeting)


# post route
@app.route("/mentor/posts", methods=["GET", "POST"])
def mentor_posts():
    if not is_logged_in() or session.get("role") != "mentor":
        flash("You do not have permission to access this page", "error")
        return redirect(url_for("index"))

    user_id = session.get("user_id")
    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        # Create a new post
        content = request.form["content"]
        cursor.execute(
            """
            INSERT INTO posts (user_id, content, created_at)
            VALUES (?, ?, datetime('now'))
            """,
            (user_id, content),
        )
        conn.commit()
        flash("Post created successfully!", "success")
        return redirect(url_for("mentor_posts"))

    # Fetch all posts created by the mentor
    posts = cursor.execute(
        """
        SELECT p.id, p.content, p.created_at, COUNT(c.id) AS comment_count
        FROM posts p
        LEFT JOIN comments c ON p.id = c.post_id
        WHERE p.user_id = ?
        GROUP BY p.id
        ORDER BY p.created_at DESC
        """,
        (user_id,),
    ).fetchall()

    # Fetch comments for each post (add this block)
    comments = cursor.execute(
        """
        SELECT c.post_id, c.content, c.created_at, u.first_name, u.last_name
        FROM comments c
        JOIN users u ON c.user_id = u.id
        ORDER BY c.created_at ASC
        """
    ).fetchall()

    # Fetch comments for each post (add this block)
    comments = cursor.execute(
        """
        SELECT c.post_id, c.content, c.created_at, u.first_name, u.last_name
        FROM comments c
        JOIN users u ON c.user_id = u.id
        ORDER BY c.created_at ASC
        """
    ).fetchall()

    conn.close()
    return render_template("mentor/posts.html", posts=posts, comments=comments)
    return render_template("mentor/posts.html", posts=posts, comments=comments)


@app.route("/mentee/posts", methods=["GET", "POST"])
def mentee_posts():
    if not is_logged_in() or session.get("role") != "mentee":
        flash("You do not have permission to access this page", "error")
        return redirect(url_for("index"))

    user_id = session.get("user_id")
    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        # Add a comment to a post
        post_id = request.form["post_id"]
        comment = request.form["comment"]
        cursor.execute(
            """
            INSERT INTO comments (post_id, user_id, content, created_at)
            VALUES (?, ?, ?, datetime('now'))
            """,
            (post_id, user_id, comment),
        )
        conn.commit()
        flash("Comment added successfully!", "success")
        return redirect(url_for("mentee_posts"))

    # Fetch all posts and their comments
    posts = cursor.execute(
        """
        SELECT p.id, p.content, p.created_at, u.first_name, u.last_name,
               (SELECT COUNT(*) FROM comments WHERE post_id = p.id) AS comment_count
        FROM posts p
        JOIN users u ON p.user_id = u.id
        ORDER BY p.created_at DESC
        """
    ).fetchall()

    # Fetch comments for each post
    comments = cursor.execute(
        """
        SELECT c.post_id, c.content, c.created_at, u.first_name, u.last_name
        FROM comments c
        JOIN users u ON c.user_id = u.id
        ORDER BY c.created_at ASC
        """
    ).fetchall()

    conn.close()
    return render_template("mentee/posts.html", posts=posts, comments=comments)

# Admin routes
@app.route("/admin/mentors")
def admin_mentors():
    if not is_logged_in() or session.get("role") != "admin":
        flash("You do not have permission to access this page", "error")
        return redirect(url_for("index"))

    conn = get_db()
    cursor = conn.cursor()

    mentors = cursor.execute(
        """
        SELECT u.id, u.first_name, u.last_name, u.email, mp.department, mp.mobile_no,
               (SELECT COUNT(*) FROM connections WHERE mentor_id = u.id AND status = 'ACCEPTED') as mentee_count
        FROM users u
        JOIN mentor_profiles mp ON u.id = mp.user_id
        WHERE u.role = 'mentor'
        ORDER BY u.first_name
    """
    ).fetchall()

    conn.close()

    return render_template("admin/mentors.html", mentors=mentors)


@app.route("/admin/mentees")
def admin_mentees():
    if not is_logged_in() or session.get("role") != "admin":
        flash("You do not have permission to access this page", "error")
        return redirect(url_for("index"))

    conn = get_db()
    cursor = conn.cursor()

    mentees = cursor.execute(
        """
        SELECT u.id, u.first_name, u.last_name, u.email, mp.department, mp.semester, mp.roll_no, mp.mobile_no,
               (SELECT COUNT(*) FROM connections WHERE mentee_id = u.id AND status = 'ACCEPTED') as mentor_count
        FROM users u
        JOIN mentee_profiles mp ON u.id = mp.user_id
        WHERE u.role = 'mentee'
        ORDER BY u.first_name
    """
    ).fetchall()

    conn.close()

    return render_template("admin/mentees.html", mentees=mentees)


@app.route("/admin/edit_user/<int:user_id>", methods=["GET", "POST"])
def admin_edit_user(user_id):
    if not is_logged_in() or session.get("role") != "admin":
        flash("You do not have permission for this action", "error")
        return redirect(url_for("index"))

    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        first_name = request.form["first_name"]
        last_name = request.form["last_name"]
        email = request.form["email"]

        cursor.execute(
            """
            UPDATE users 
            SET first_name = ?, last_name = ?, email = ?
            WHERE id = ?
        """,
            (first_name, last_name, email, user_id),
        )

        role = cursor.execute(
            "SELECT role FROM users WHERE id = ?", (user_id,)
        ).fetchone()["role"]

        if role == "mentor":
            department = request.form["department"]
            bio = request.form.get("bio", "")
            expertise = request.form.get("expertise", "")
            mobile_no = request.form.get("mobile_no", "")

            cursor.execute(
                """
                UPDATE mentor_profiles
                SET department = ?, bio = ?, expertise = ?, mobile_no = ?
                WHERE user_id = ?
            """,
                (department, bio, expertise, mobile_no, user_id),
            )

        elif role == "mentee":
            department = request.form["department"]
            semester = request.form["semester"]
            roll_no = request.form["roll_no"]
            mobile_no = request.form.get("mobile_no", "")
            address = request.form.get("address", "")

            cursor.execute(
                """
                UPDATE mentee_profiles
                SET department = ?, semester = ?, roll_no = ?, mobile_no = ?, address = ?
                WHERE user_id = ?
            """,
                (department, semester, roll_no, mobile_no, address, user_id),
            )

        conn.commit()

        flash("User updated successfully", "success")

        if role == "mentor":
            return redirect(url_for("admin_mentors"))
        else:
            return redirect(url_for("admin_mentees"))

    # Get user details
    user = cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    if not user:
        flash("User not found", "error")
        conn.close()
        return redirect(url_for("admin_dashboard"))

    profile = None
    if user["role"] == "mentor":
        profile = cursor.execute(
            "SELECT * FROM mentor_profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
    elif user["role"] == "mentee":
        profile = cursor.execute(
            "SELECT * FROM mentee_profiles WHERE user_id = ?", (user_id,)
        ).fetchone()

    conn.close()

    return render_template("admin/edit_user.html", user=user, profile=profile)


@app.route("/admin/delete_user/<int:user_id>", methods=["POST"])
def admin_delete_user(user_id):
    if not is_logged_in() or session.get("role") != "admin":
        flash("You do not have permission for this action", "error")
        return redirect(url_for("index"))

    conn = get_db()
    cursor = conn.cursor()

    # Get user role
    user = cursor.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()

    if not user:
        flash("User not found", "error")
        conn.close()
        return redirect(url_for("admin_dashboard"))

    role = user["role"]

    # Delete user and related data
    cursor.execute(
        "DELETE FROM activities WHERE user_id = ? OR related_user_id = ?",
        (user_id, user_id),
    )
    cursor.execute("DELETE FROM comments WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM posts WHERE user_id = ?", (user_id,))

    if role == "mentor":
        cursor.execute("DELETE FROM meetings WHERE mentor_id = ?", (user_id,))
        cursor.execute("DELETE FROM connections WHERE mentor_id = ?", (user_id,))
        cursor.execute("DELETE FROM mentor_profiles WHERE user_id = ?", (user_id,))
    elif role == "mentee":
        cursor.execute("DELETE FROM meetings WHERE mentee_id = ?", (user_id,))
        cursor.execute("DELETE FROM connections WHERE mentee_id = ?", (user_id,))
        cursor.execute("DELETE FROM academic_records WHERE mentee_id = ?", (user_id,))
        cursor.execute("DELETE FROM mentee_profiles WHERE user_id = ?", (user_id,))

    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))

    conn.commit()
    conn.close()

    flash("User deleted successfully", "success")

    if role == "mentor":
        return redirect(url_for("admin_mentors"))
    else:
        return redirect(url_for("admin_mentees"))


@app.route("/mentor/profile")
def mentor_profile():
    if not is_logged_in() or session.get("role") != "mentor":
        flash("You do not have permission to access this page", "error")
        return redirect(url_for("index"))

    user_id = session.get("user_id")
    conn = get_db()
    cursor = conn.cursor()

    # Fetch mentor's user details
    user = cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    # Fetch mentor's profile details
    profile = cursor.execute(
        "SELECT * FROM mentor_profiles WHERE user_id = ?", (user_id,)
    ).fetchone()

    conn.close()

    return render_template("mentor/profile.html", user=user, profile=profile)


@app.route("/mentor/pastmentees")
def mentor_pastmentees():
    if not is_logged_in() or session.get("role") != "mentor":
        flash("You do not have permission to view this page", "error")
        return redirect(url_for("index"))

    conn = get_db()
    cursor = conn.cursor()

    mentor_id = session.get("user_id")

    cursor.execute("""
        SELECT u.id, u.first_name, u.last_name, mp.department, mp.semester, 
               mp.roll_no, mp.mobile_no, mp.address, c.updated_at
        FROM users u
        JOIN mentee_profiles mp ON u.id = mp.user_id
        JOIN connections c ON c.mentee_id = u.id
        WHERE c.mentor_id = ? AND c.status = 'TERMINATED'
    """, (mentor_id,))
    
    mentees = cursor.fetchall()
    conn.close()

    return render_template(
        "mentor/pastmentees.html",
        mentees=mentees
    )


@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form["email"]
        conn = get_db()
        cursor = conn.cursor()
        user = cursor.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user:
            session["reset_user_id"] = user["id"]
            flash("Please set your new password below.", "success")
            conn.close()
            return redirect(url_for("reset_password"))
        else:
            flash("No user found with that email.", "error")
            conn.close()
            return redirect(url_for("forgot_password"))
    return render_template("auth/forgot_password.html")


@app.route("/reset_password", methods=["GET", "POST"])
def reset_password():
    if "reset_user_id" not in session:
        flash("Unauthorized or expired reset session.", "error")
        return redirect(url_for("login"))
    if request.method == "POST":
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("reset_password"))
        hashed_password = generate_password_hash(password)
        user_id = session["reset_user_id"]
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET password = ? WHERE id = ?", (hashed_password, user_id))
        conn.commit()
        conn.close()
        session.pop("reset_user_id", None)
        flash("Password reset successful! You can now log in.", "success")
        return redirect(url_for("login"))
    return render_template("auth/reset_password.html")


# Mentee Forgot Password
@app.route("/mentee/forgot_password", methods=["GET", "POST"])
def mentee_forgot_password():
    if request.method == "POST":
        email = request.form["email"]
        conn = get_db()
        cursor = conn.cursor()
        user = cursor.execute("SELECT * FROM users WHERE email = ? AND role = 'mentee'", (email,)).fetchone()
        if user:
            session["mentee_reset_user_id"] = user["id"]
            flash("Please set your new password below.", "success")
            conn.close()
            return redirect(url_for("mentee_reset_password"))
        else:
            flash("No mentee found with that email.", "error")
            conn.close()
            return redirect(url_for("mentee_forgot_password"))
    return render_template("auth/forgot_password.html", role="mentee")

# Mentee Reset Password
@app.route("/mentee/reset_password", methods=["GET", "POST"])
def mentee_reset_password():
    if "mentee_reset_user_id" not in session:
        flash("Unauthorized or expired reset session.", "error")
        return redirect(url_for("login"))
    if request.method == "POST":
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("mentee_reset_password"))
        hashed_password = generate_password_hash(password)
        user_id = session["mentee_reset_user_id"]
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET password = ? WHERE id = ?", (hashed_password, user_id))
        conn.commit()
        conn.close()
        session.pop("mentee_reset_user_id", None)
        flash("Password reset successful! You can now log in.", "success")
        return redirect(url_for("login"))
    return render_template("auth/reset_password.html", role="mentee")


@app.context_processor
def inject_notifications():
    mentor_notifications = []
    mentee_notifications = []
    if "user_id" in session:
        conn = get_db()
        cursor = conn.cursor()
        if session.get("role") == "mentor":
            mentor_notifications = cursor.execute(
                """
                SELECT description, timestamp
                FROM activities
                WHERE user_id = ? AND activity_type = 'POST_COMMENT_NOTIFICATION'
                ORDER BY timestamp DESC
                LIMIT 5
                """,
                (session["user_id"],),
            ).fetchall()
        elif session.get("role") == "mentee":
            # Comments on mentee's posts
            comment_notes = cursor.execute(
                """
                SELECT description, timestamp
                FROM activities
                WHERE user_id = ? AND activity_type = 'POST_COMMENT_NOTIFICATION'
                ORDER BY timestamp DESC
                LIMIT 5
                """,
                (session["user_id"],),
            ).fetchall()
            # Accepted connection requests
            connection_notes = cursor.execute(
                """
                SELECT description, timestamp
                FROM activities
                WHERE related_user_id = ? AND activity_type = 'CONNECTION_ACCEPTED'
                ORDER BY timestamp DESC
                LIMIT 5
                """,
                (session["user_id"],),
            ).fetchall()
            # Combine and sort by timestamp (latest first)
            mentee_notifications = list(comment_notes) + list(connection_notes)
            mentee_notifications.sort(key=lambda x: x["timestamp"], reverse=True)
            mentee_notifications = mentee_notifications[:5]
        conn.close()
    return {
        "mentor_notifications": mentor_notifications,
        "mentee_notifications": mentee_notifications
    }

if __name__ == "__main__":
    create_database()
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)