CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    account_id TEXT NOT NULL,
    password TEXT NOT NULL,
    email TEXT,
    email2 TEXT,
    url TEXT
);
