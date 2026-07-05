"""Database schema for the AICRM backend.

DEPRECATED: This module is retained as a reference for the current schema
structure but is NO LONGER the primary mechanism for schema evolution.

Schema changes should now be introduced through Alembic migrations located
in backend/migrations/versions/.  See backend/README.md for the migration
workflow.

To create a new migration:
    cd backend
    alembic revision --autogenerate -m "description of change"

To apply migrations:
    cd backend
    alembic upgrade head
"""

CREATE_CONTACTS_TABLE = """
CREATE TABLE IF NOT EXISTS contacts (
    id          VARCHAR(64)  PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    email       VARCHAR(300),
    phone       VARCHAR(50),
    company     VARCHAR(200),
    status      VARCHAR(50)  NOT NULL DEFAULT 'active',
    notes       TEXT,
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
"""

CREATE_AUDIT_LOG_TABLE = """
CREATE TABLE IF NOT EXISTS audit_log (
    id              SERIAL PRIMARY KEY,
    entity_type     VARCHAR(100) NOT NULL,
    entity_id       VARCHAR(64)  NOT NULL,
    action          VARCHAR(50)  NOT NULL,
    actor_sub       VARCHAR(200) NOT NULL,
    actor_username  VARCHAR(200),
    actor_email     VARCHAR(300),
    actor_roles     TEXT,
    timestamp       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    details_json    JSONB
);
"""


CREATE_TEMPLATES_TABLE = """
CREATE TABLE IF NOT EXISTS templates (
    id          VARCHAR(64)  PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    category    VARCHAR(100) NOT NULL DEFAULT 'other',
    subject     VARCHAR(500),
    content     TEXT,
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
"""


CREATE_LEADS_TABLE = """
CREATE TABLE IF NOT EXISTS leads (
    id          VARCHAR(64)  PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    company     VARCHAR(200),
    email       VARCHAR(300),
    phone       VARCHAR(50),
    value       NUMERIC(12, 2),
    stage       VARCHAR(50)  NOT NULL DEFAULT 'new',
    source      VARCHAR(50),
    notes       TEXT,
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
"""

CREATE_ACTIVITIES_TABLE = """
CREATE TABLE IF NOT EXISTS activities (
    id            VARCHAR(64)  PRIMARY KEY,
    type          VARCHAR(50)  NOT NULL,
    description   TEXT         NOT NULL,
    contact_name  VARCHAR(200),
    occurred_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    due_date      DATE,
    status        VARCHAR(50)  NOT NULL DEFAULT 'pending',
    created_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
"""

CREATE_ACTIVITIES_OCCURRED_AT_INDEX = """
CREATE INDEX IF NOT EXISTS idx_activities_occurred_at ON activities (occurred_at DESC);
"""

CREATE_ACTIVITIES_STATUS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_activities_status ON activities (status);
"""

CREATE_SETTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS settings (
    id          VARCHAR(64)  PRIMARY KEY DEFAULT 'app',
    payload     JSONB        NOT NULL DEFAULT '{}',
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
"""

CREATE_CONTACT_TAGS_TABLE = """
CREATE TABLE IF NOT EXISTS contact_tags (
    id          VARCHAR(64)  PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    color       VARCHAR(20)  NOT NULL DEFAULT '#3b82f6',
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
"""

CREATE_CONTACT_TAGS_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_contact_tags_name
ON contact_tags (LOWER(name));
"""

CREATE_CONTACT_TAG_MAPPING_TABLE = """
CREATE TABLE IF NOT EXISTS contact_tag_mapping (
    contact_id  VARCHAR(64) NOT NULL,
    tag_id      VARCHAR(64) NOT NULL,
    assigned_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    PRIMARY KEY (contact_id, tag_id),
    FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES contact_tags(id) ON DELETE CASCADE
);
"""

CREATE_SALES_GOALS_TABLE = """
CREATE TABLE IF NOT EXISTS sales_goals (
    id              VARCHAR(64)  PRIMARY KEY,
    name            VARCHAR(200) NOT NULL,
    type            VARCHAR(50)  NOT NULL,
    target_value    NUMERIC(14, 2) NOT NULL DEFAULT 0,
    current_value   NUMERIC(14, 2) NOT NULL DEFAULT 0,
    period          VARCHAR(50)  NOT NULL,
    start_date      DATE         NOT NULL,
    end_date        DATE         NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
"""


def create_schema():
    """Execute all schema creation statements."""
    from app.db.connection import get_cursor

    with get_cursor() as cur:
        cur.execute(CREATE_CONTACTS_TABLE)
        cur.execute(CREATE_AUDIT_LOG_TABLE)
        cur.execute(CREATE_TEMPLATES_TABLE)
        cur.execute(CREATE_LEADS_TABLE)
        cur.execute(CREATE_ACTIVITIES_TABLE)
        cur.execute(CREATE_ACTIVITIES_OCCURRED_AT_INDEX)
        cur.execute(CREATE_ACTIVITIES_STATUS_INDEX)
        cur.execute(CREATE_SETTINGS_TABLE)
        cur.execute(CREATE_CONTACT_TAGS_TABLE)
        cur.execute(CREATE_CONTACT_TAGS_INDEX)
        cur.execute(CREATE_CONTACT_TAG_MAPPING_TABLE)
        cur.execute(CREATE_SALES_GOALS_TABLE)
