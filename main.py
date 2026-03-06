from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

import sqlite3

app = FastAPI()
app.mount("/assets", StaticFiles(directory="assets"), name="assets")
templates = Jinja2Templates(directory="templates")

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

    # Sample users
    sample_users = [
        ("teacher1@dawss.ca", "admin123", "Mr. Smith", False, True, True),
        ("teacher2@dawss.ca", "admin123", "Ms. Johnson", False, True, True),
        ("jason@dawss.ca", "prom2026", "Jason", False, True, False),
        ("sarah@dawss.ca", "prom2026", "Sarah", True, True, False),
        ("mike@dawss.ca", "prom2026", "Mike", False, False, False),
    ]

    cursor.executemany(
        "INSERT OR IGNORE INTO users (email, password, name, hasSecondSeat, enabled, isTeacher) VALUES (?, ?, ?, ?, ?, ?)",
        sample_users
    )

    conn.commit()
    conn.close()
    print("✅ Database ready!")


@app.get("/", include_in_schema=False)
async def root(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/login", include_in_schema=False)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login", include_in_schema=False)
async def login(request: Request, email: str = Form(...), password: str = Form(...)):
    conn = get_db()
    cursor = conn.cursor()
    # ──────────────────────────────────────────────
    # TODO: Replace this with a real database lookup!
    # For now, a simple hard-coded check as a placeholder.
    # ──────────────────────────────────────────────

    cursor.execute("SELECT * FROM users WHERE email = ? AND password = ?", (email,password))
    user = cursor.fetchone()
    conn.close()

    if user and not (user["isTeacher"]):
        # Successful login → redirect to home (or a dashboard later)
        return RedirectResponse(url="/", status_code=303)
    elif user and (user["isTeacher"]):
        return RedirectResponse(url="/teacher", status_code=303)
    else:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid email or password. Please try again."},
        )


@app.get("/student", include_in_schema=False)
async def student_dashboard():
    return {"portal": "student", "message": "Welcome, student!"}


@app.get("/teacher", include_in_schema=False)
async def teacher_dashboard():
    return {"portal": "teacher", "message": "Welcome, teacher!"}

@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}
