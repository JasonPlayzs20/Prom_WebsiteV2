# from lib2to3.pgen2.literals import simple_escapes

from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, JSONResponse

from starlette.middleware.sessions import SessionMiddleware

from pydantic import BaseModel
from typing import Optional
import sqlite3

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="secret")
app.mount("/assets", StaticFiles(directory="assets"), name="assets")
templates = Jinja2Templates(directory="templates")


# ── DB ───────────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect("data.db")
    conn.row_factory = sqlite3.Row
    return conn


@app.on_event("startup")
async def startup():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    name TEXT NOT NULL,
    hasSecondSeat BOOLEAN NOT NULL DEFAULT FALSE,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    isTeacher BOOLEAN NOT NULL DEFAULT FALSE)
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS seats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    table_number INTEGER NOT NULL CHECK(table_number BETWEEN 1 AND 40),
    seat_index INTEGER NOT NULL DEFAULT 0,
    UNIQUE(user_id, seat_index),
    FOREIGN KEY(user_id) REFERENCES users(id))
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL)
    """)

    sample_users = [
        ("teacher1@dawss.ca", "admin123", "Mr. B",   False, True,  True),
        ("teacher2@dawss.ca", "admin123", "Ms. Q", False, True,  True),
        ("jason@dawss.ca", "prom2026", "Jason", False, True, False),
        ("diana@dawss.ca", "prom2026", "Diana", True, True, False),
        ("mike@dawss.ca", "prom2026", "Mike", False, False, False),
        ("max@dawss.ca", "prom2026", "Max", False, True, False),
        ("kirk@dawss.ca", "prom2026", "Kirk", True, True, False),
        ("riyaj@dawss.ca", "prom2026", "Riyaj", False, False, False),
    ]

    cursor.executemany(
        "INSERT OR IGNORE INTO users (email, password, name, hasSecondSeat, enabled, isTeacher) VALUES (?, ?, ?, ?, ?, ?)",
        sample_users
    )
    cursor.execute(
        "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
        ("seat_picking_enabled", "1")
    )

    conn.commit()
    conn.close()
    print("✅ Database ready!")


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_db_cursor():
    conn = get_db()
    return conn, conn.cursor()


def get_table_counts(cursor):
    """Returns list of 40 dicts: {number, count}"""
    cursor.execute("SELECT table_number, COUNT(*) as cnt FROM seats GROUP BY table_number")
    raw = {row["table_number"]: row["cnt"] for row in cursor.fetchall()}
    return [{"number": i, "count": raw.get(i, 0)} for i in range(1, 41)]


def get_my_seats(cursor, user_id: int):
    """Returns ordered list of table numbers the user holds (0–2 items)"""
    cursor.execute(
        "SELECT table_number FROM seats WHERE user_id = ? ORDER BY seat_index",
        (user_id,)
    )
    return [row["table_number"] for row in cursor.fetchall()]


SEAT_PICKING_SETTING_KEY = "seat_picking_enabled"


def get_bool_setting(cursor, key: str, default: bool = True) -> bool:
    cursor.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    if not row:
        return default
    return str(row["value"]).strip().lower() in ("1", "true", "yes", "on")


def set_bool_setting(cursor, key: str, value: bool):
    val = "1" if value else "0"
    cursor.execute("UPDATE app_settings SET value = ? WHERE key = ?", (val, key))
    if cursor.rowcount == 0:
        cursor.execute("INSERT INTO app_settings (key, value) VALUES (?, ?)", (key, val))


def is_seat_picking_enabled(cursor) -> bool:
    return get_bool_setting(cursor, SEAT_PICKING_SETTING_KEY, default=True)


def require_teacher(request: Request):
    """Returns user_id if teacher session is valid, else None."""
    if "user_id" not in request.session:
        return None
    if not request.session.get("isTeacher"):
        return None
    return request.session["user_id"]


# ── Pages ────────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root(request: Request):
    return templates.TemplateResponse(request, "index.html", {"active_page": "home"})

@app.get("/index", include_in_schema=False)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"active_page": "home"})


@app.get("/important-dates", include_in_schema=False)
async def important_dates_page(request: Request):
    return templates.TemplateResponse(request, "important_dates.html", {"active_page": "important-dates"})


@app.get("/table-seating", include_in_schema=False)
async def table_seating_page(request: Request):
    return templates.TemplateResponse(request, "table_seating.html", {"active_page": "table-seating"})


@app.get("/mock-awards", include_in_schema=False)
async def mock_awards_page(request: Request):
    return templates.TemplateResponse(request, "mock_awards.html", {"active_page": "mock-awards"})


@app.get("/forms", include_in_schema=False)
async def forms_page(request: Request):
    return templates.TemplateResponse(request, "forms.html", {"active_page": "forms"})


@app.get("/menu", include_in_schema=False)
async def menu_page(request: Request):
    return templates.TemplateResponse(request, "menu.html", {"active_page": "menu"})


@app.get("/rules", include_in_schema=False)
async def rules_page(request: Request):
    return templates.TemplateResponse(request, "rules.html", {"active_page": "rules"})


@app.get("/faq", include_in_schema=False)
async def faq_page(request: Request):
    return templates.TemplateResponse(request, "faq.html", {"active_page": "faq"})


@app.get("/gowns-for-grads", include_in_schema=False)
async def gowns_for_grads_page(request: Request):
    return templates.TemplateResponse(request, "gowns_for_grads.html", {"active_page": "gowns-for-grads"})


@app.get("/login", include_in_schema=False)
async def login_page(request: Request):
    if "user_id" in request.session:
        if request.session["isTeacher"]:
            return RedirectResponse(url="/teacher")
        return RedirectResponse(url="/student")
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login", include_in_schema=False)
async def login(request: Request, email: str = Form(...), password: str = Form(...)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ? AND password = ?", (email, password))
    user = cursor.fetchone()
    conn.close()

    if user and not user["isTeacher"]:
        request.session["user_id"] = user["id"]
        request.session["user_name"] = user["name"]
        request.session["isTeacher"] = user["isTeacher"]
        return RedirectResponse(url="/student", status_code=303)
    elif user and user["isTeacher"]:
        request.session["user_id"] = user["id"]
        request.session["user_name"] = user["name"]
        request.session["isTeacher"] = user["isTeacher"]
        return RedirectResponse(url="/teacher", status_code=303)
    else:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid email or password. Please try again."},
        )


@app.get("/student", include_in_schema=False)
async def student_dashboard(request: Request):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login")
    if request.session["isTeacher"]:
        return RedirectResponse(url="/teacher")

    user_id = request.session["user_id"]
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()

    tables   = get_table_counts(cursor)
    my_seats = get_my_seats(cursor, user_id)
    seat_picking_enabled = is_seat_picking_enabled(cursor)
    conn.close()

    return templates.TemplateResponse(request, "student.html", {
        "user_name":       user["name"],
        "enabled":         bool(user["enabled"]),
        "has_second_seat": bool(user["hasSecondSeat"]),
        "seat_picking_enabled": seat_picking_enabled,
        "tables":          tables,
        "my_seats":        my_seats,
    })


@app.get("/teacher", include_in_schema=False)
async def teacher_dashboard(request: Request):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login")
    if not request.session["isTeacher"]:
        return RedirectResponse(url="/student")

    conn = get_db()
    cursor = conn.cursor()
    tables = get_table_counts(cursor)
    seat_picking_enabled = is_seat_picking_enabled(cursor)
    conn.close()

    return templates.TemplateResponse(request, "teacher.html", {
        "user_name": request.session["user_name"],
        "tables":    tables,
        "seat_picking_enabled": seat_picking_enabled,
    })


@app.get("/logout", include_in_schema=False)
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")


# ── Student Seat API (student self-service) ───────────────────────────────────

class SelectBody(BaseModel):
    table: int

class ChangeBody(BaseModel):
    from_table: int
    to_table: int


@app.post("/seat/select", include_in_schema=False)
async def seat_select(request: Request, body: SelectBody):
    """Student picks a new seat (first or second)."""
    if "user_id" not in request.session:
        return JSONResponse({"success": False, "error": "Not logged in"}, status_code=401)

    user_id = request.session["user_id"]
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    if not user or not user["enabled"]:
        conn.close()
        return JSONResponse({"success": False, "error": "Account not enabled."})
    if not is_seat_picking_enabled(cursor):
        conn.close()
        return JSONResponse({"success": False, "error": "Seat selection is currently paused for all students."})

    my_seats  = get_my_seats(cursor, user_id)
    max_seats = 2 if user["hasSecondSeat"] else 1
    if len(my_seats) >= max_seats:
        conn.close()
        return JSONResponse({"success": False, "error": "You've already selected your maximum seats."})

    if not (1 <= body.table <= 40):
        conn.close()
        return JSONResponse({"success": False, "error": "Invalid table number."})

    cursor.execute("SELECT COUNT(*) as cnt FROM seats WHERE table_number = ?", (body.table,))
    if cursor.fetchone()["cnt"] >= 10:
        conn.close()
        return JSONResponse({"success": False, "error": "That table is full!"})

    cursor.execute(
        "INSERT INTO seats (user_id, table_number, seat_index) VALUES (?, ?, ?)",
        (user_id, body.table, len(my_seats))
    )
    conn.commit()

    tables   = get_table_counts(cursor)
    my_seats = get_my_seats(cursor, user_id)
    conn.close()

    return JSONResponse({
        "success":  True,
        "message":  f"Seat reserved at Table {body.table}!",
        "my_seats": my_seats,
        "tables":   tables,
    })


@app.post("/seat/change", include_in_schema=False)
async def seat_change(request: Request, body: ChangeBody):
    """Student moves from one table to another."""
    if "user_id" not in request.session:
        return JSONResponse({"success": False, "error": "Not logged in"}, status_code=401)

    user_id = request.session["user_id"]
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    if not user or not user["enabled"]:
        conn.close()
        return JSONResponse({"success": False, "error": "Account not enabled."})
    if not is_seat_picking_enabled(cursor):
        conn.close()
        return JSONResponse({"success": False, "error": "Seat selection is currently paused for all students."})

    cursor.execute(
        "SELECT id FROM seats WHERE user_id = ? AND table_number = ?",
        (user_id, body.from_table)
    )
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        return JSONResponse({"success": False, "error": "You don't have a seat at that table."})

    if not (1 <= body.to_table <= 40):
        conn.close()
        return JSONResponse({"success": False, "error": "Invalid table number."})

    cursor.execute(
        "SELECT COUNT(*) as cnt FROM seats WHERE table_number = ?",
        (body.to_table,)
    )
    if cursor.fetchone()["cnt"] >= 10:
        conn.close()
        return JSONResponse({"success": False, "error": "That table is full!"})

    cursor.execute(
        "UPDATE seats SET table_number = ? WHERE id = ?",
        (body.to_table, existing["id"])
    )
    conn.commit()

    tables   = get_table_counts(cursor)
    my_seats = get_my_seats(cursor, user_id)
    conn.close()

    return JSONResponse({
        "success":  True,
        "message":  f"Moved from Table {body.from_table} to Table {body.to_table}!",
        "my_seats": my_seats,
        "tables":   tables,
    })


# ── Teacher API ───────────────────────────────────────────────────────────────

@app.get("/teacher/students", include_in_schema=False)
async def teacher_get_students(request: Request):
    """Return all non-teacher students with their seat info."""
    if not require_teacher(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=403)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE isTeacher = 0 ORDER BY name")
    users = cursor.fetchall()

    students = []
    for u in users:
        seats = get_my_seats(cursor, u["id"])
        students.append({
            "id":           u["id"],
            "name":         u["name"],
            "email":        u["email"],
            "enabled":      bool(u["enabled"]),
            "hasSecondSeat": bool(u["hasSecondSeat"]),
            "seats":        seats,
        })

    conn.close()
    return JSONResponse({"students": students})


class SeatPickingToggleBody(BaseModel):
    enabled: bool


@app.post("/teacher/settings/seat-picking", include_in_schema=False)
async def teacher_toggle_seat_picking(request: Request, body: SeatPickingToggleBody):
    """Globally enable/disable student seat picking without changing per-student status."""
    if not require_teacher(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=403)

    conn = get_db()
    cursor = conn.cursor()
    set_bool_setting(cursor, SEAT_PICKING_SETTING_KEY, body.enabled)
    conn.commit()
    conn.close()

    state = "enabled" if body.enabled else "paused"
    return JSONResponse({
        "success": True,
        "enabled": body.enabled,
        "message": f"Global seat picking is now {state}.",
    })


class ToggleBody(BaseModel):
    user_id: int
    field: str   # "enabled" or "hasSecondSeat"
    value: bool
    seat_table_to_remove: Optional[int] = None


@app.post("/teacher/student/toggle", include_in_schema=False)
async def teacher_toggle_field(request: Request, body: ToggleBody):
    """Toggle enabled or hasSecondSeat for a student."""
    if not require_teacher(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=403)

    if body.field not in ("enabled", "hasSecondSeat"):
        return JSONResponse({"success": False, "error": "Invalid field."})

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE id = ? AND isTeacher = 0", (body.user_id,))
    if not cursor.fetchone():
        conn.close()
        return JSONResponse({"success": False, "error": "Student not found."})

    seat_row_to_delete = None

    # If disabling hasSecondSeat and student has 2 seats, teacher must choose which seat to remove.
    if body.field == "hasSecondSeat" and not body.value:
        cursor.execute(
            "SELECT id, table_number FROM seats WHERE user_id = ? ORDER BY seat_index",
            (body.user_id,)
        )
        seat_rows = cursor.fetchall()
        if len(seat_rows) > 1:
            if body.seat_table_to_remove is None:
                conn.close()
                return JSONResponse({
                    "success": False,
                    "requires_seat_choice": True,
                    "error": "Choose which seat to remove before disabling the 2nd ticket.",
                    "seats": [row["table_number"] for row in seat_rows],
                })

            for row in seat_rows:
                if row["table_number"] == body.seat_table_to_remove:
                    seat_row_to_delete = row
                    break

            if seat_row_to_delete is None:
                conn.close()
                return JSONResponse({"success": False, "error": "Selected seat not found for this student."})

    cursor.execute(
        f"UPDATE users SET {body.field} = ? WHERE id = ? AND isTeacher = 0",
        (1 if body.value else 0, body.user_id)
    )

    if seat_row_to_delete:
        cursor.execute("DELETE FROM seats WHERE id = ?", (seat_row_to_delete["id"],))
        # Re-index remaining seats (0, 1) to keep them contiguous.
        cursor.execute(
            "SELECT id FROM seats WHERE user_id = ? ORDER BY seat_index",
            (body.user_id,)
        )
        remaining = cursor.fetchall()
        for i, row in enumerate(remaining):
            cursor.execute("UPDATE seats SET seat_index = ? WHERE id = ?", (i, row["id"]))

    conn.commit()
    conn.close()

    label = "enabled" if body.field == "enabled" else "2nd ticket"
    state = "on" if body.value else "off"
    if seat_row_to_delete:
        return JSONResponse({
            "success": True,
            "message": f"Turned {label} {state}. Removed seat at Table {seat_row_to_delete['table_number']}.",
        })
    return JSONResponse({"success": True, "message": f"Turned {label} {state}."})


class TeacherAssignBody(BaseModel):
    user_id: int
    to_table: int
    from_table: Optional[int] = None


class TeacherChangeBody(BaseModel):
    user_id: int
    from_table: int
    to_table: int


class TeacherRemoveBody(BaseModel):
    user_id: int
    table_number: int


@app.post("/teacher/seat/assign", include_in_schema=False)
async def teacher_assign_seat(request: Request, body: TeacherAssignBody):
    """Teacher assigns a new seat to a student who has none (or adds a second)."""
    if not require_teacher(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=403)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id = ? AND isTeacher = 0", (body.user_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return JSONResponse({"success": False, "error": "Student not found."})

    my_seats  = get_my_seats(cursor, body.user_id)
    max_seats = 2 if user["hasSecondSeat"] else 1

    if not (1 <= body.to_table <= 40):
        conn.close()
        return JSONResponse({"success": False, "error": "Invalid table number."})

    # If the student is already at max seats, treat assign as "move" instead of hard failing.
    if len(my_seats) >= max_seats:
        from_table = body.from_table
        if from_table is None and len(my_seats) == 1:
            from_table = my_seats[0]

        if from_table is None:
            conn.close()
            return JSONResponse({
                "success": False,
                "error": "Student already has maximum seats. Choose which seat to move.",
            })

        if from_table == body.to_table:
            conn.close()
            return JSONResponse({"success": False, "error": "Student is already seated at that table."})

        cursor.execute(
            "SELECT id FROM seats WHERE user_id = ? AND table_number = ? ORDER BY seat_index LIMIT 1",
            (body.user_id, from_table)
        )
        existing = cursor.fetchone()
        if not existing:
            conn.close()
            return JSONResponse({"success": False, "error": "Student doesn't have a seat at that table."})

        cursor.execute("SELECT COUNT(*) as cnt FROM seats WHERE table_number = ?", (body.to_table,))
        if cursor.fetchone()["cnt"] >= 10:
            conn.close()
            return JSONResponse({"success": False, "error": "That table is full!"})

        cursor.execute(
            "UPDATE seats SET table_number = ? WHERE id = ?",
            (body.to_table, existing["id"])
        )
        conn.commit()

        tables = get_table_counts(cursor)
        conn.close()
        return JSONResponse({
            "success": True,
            "message": f"Moved {user['name']} from Table {from_table} to Table {body.to_table}.",
            "tables":  tables,
        })

    cursor.execute("SELECT COUNT(*) as cnt FROM seats WHERE table_number = ?", (body.to_table,))
    if cursor.fetchone()["cnt"] >= 10:
        conn.close()
        return JSONResponse({"success": False, "error": "That table is full!"})

    cursor.execute(
        "INSERT INTO seats (user_id, table_number, seat_index) VALUES (?, ?, ?)",
        (body.user_id, body.to_table, len(my_seats))
    )
    conn.commit()

    tables = get_table_counts(cursor)
    conn.close()
    return JSONResponse({
        "success": True,
        "message": f"Assigned {user['name']} to Table {body.to_table}.",
        "tables":  tables,
    })


@app.post("/teacher/seat/change", include_in_schema=False)
async def teacher_change_seat(request: Request, body: TeacherChangeBody):
    """Teacher moves a student from one table to another."""
    if not require_teacher(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=403)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id = ? AND isTeacher = 0", (body.user_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return JSONResponse({"success": False, "error": "Student not found."})

    cursor.execute(
        "SELECT id FROM seats WHERE user_id = ? AND table_number = ?",
        (body.user_id, body.from_table)
    )
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        return JSONResponse({"success": False, "error": "Student doesn't have a seat at that table."})

    if not (1 <= body.to_table <= 40):
        conn.close()
        return JSONResponse({"success": False, "error": "Invalid table number."})

    cursor.execute(
        "SELECT COUNT(*) as cnt FROM seats WHERE table_number = ?", (body.to_table,)
    )
    if cursor.fetchone()["cnt"] >= 10:
        conn.close()
        return JSONResponse({"success": False, "error": "That table is full!"})

    cursor.execute(
        "UPDATE seats SET table_number = ? WHERE id = ?",
        (body.to_table, existing["id"])
    )
    conn.commit()

    tables = get_table_counts(cursor)
    conn.close()
    return JSONResponse({
        "success": True,
        "message": f"Moved {user['name']} from Table {body.from_table} to Table {body.to_table}.",
        "tables":  tables,
    })


@app.post("/teacher/seat/remove", include_in_schema=False)
async def teacher_remove_seat(request: Request, body: TeacherRemoveBody):
    """Teacher removes a student's specific seat."""
    if not require_teacher(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=403)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id = ? AND isTeacher = 0", (body.user_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return JSONResponse({"success": False, "error": "Student not found."})

    # Find the specific seat row to delete (SQLite doesn't support DELETE...LIMIT)
    cursor.execute(
        "SELECT id FROM seats WHERE user_id = ? AND table_number = ? ORDER BY seat_index LIMIT 1",
        (body.user_id, body.table_number)
    )
    seat_row = cursor.fetchone()
    if not seat_row:
        conn.close()
        return JSONResponse({"success": False, "error": "No seat found at that table for this student."})
    cursor.execute("DELETE FROM seats WHERE id = ?", (seat_row["id"],))

    # Re-index remaining seats (0, 1) to keep them contiguous
    cursor.execute(
        "SELECT id FROM seats WHERE user_id = ? ORDER BY seat_index",
        (body.user_id,)
    )
    remaining = cursor.fetchall()
    for i, row in enumerate(remaining):
        cursor.execute("UPDATE seats SET seat_index = ? WHERE id = ?", (i, row["id"]))

    conn.commit()
    tables = get_table_counts(cursor)
    conn.close()

    return JSONResponse({
        "success": True,
        "message": f"Removed {user['name']}'s seat at Table {body.table_number}.",
        "tables":  tables,
    })
