-- deal-intel-agent root schema (v3: matching-ready + notifications)

CREATE TABLE IF NOT EXISTS deals (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    budget REAL,
    stage TEXT NOT NULL DEFAULT 'contact',
    -- contact -> discovery -> proposal -> negotiation -> closed_won -> closed_lost
    outcome TEXT,
    outcome_reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS people (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT,
    org TEXT
);

CREATE TABLE IF NOT EXISTS deal_people (
    deal_id TEXT NOT NULL REFERENCES deals(id),
    person_id TEXT NOT NULL REFERENCES people(id),
    role TEXT,
    PRIMARY KEY (deal_id, person_id)
);

-- One row per unit of input, from ANY tool.
-- message_id / in_reply_to are mail-native identifiers used to auto-match
-- a reply to the exact input it responds to, so chaining doesn't rely on
-- anyone manually passing parent_input_id.
CREATE TABLE IF NOT EXISTS inputs (
    id TEXT PRIMARY KEY,
    deal_id TEXT NOT NULL REFERENCES deals(id),
    tool_source TEXT NOT NULL,
    input_type TEXT NOT NULL,
    thread_id TEXT,
    parent_input_id TEXT REFERENCES inputs(id),
    sender_person_id TEXT REFERENCES people(id),
    link TEXT,
    raw_ref TEXT,
    message_id TEXT,          -- e.g. mail Message-ID header
    in_reply_to TEXT,          -- e.g. mail In-Reply-To header
    summary TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS attachments (
    id TEXT PRIMARY KEY,
    input_id TEXT NOT NULL REFERENCES inputs(id),
    file_path TEXT NOT NULL,
    file_type TEXT,
    description TEXT
);

CREATE TABLE IF NOT EXISTS signals (
    id TEXT PRIMARY KEY,
    deal_id TEXT NOT NULL REFERENCES deals(id),
    input_id TEXT REFERENCES inputs(id),
    signal_type TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS deal_stage_history (
    id TEXT PRIMARY KEY,
    deal_id TEXT NOT NULL REFERENCES deals(id),
    stage TEXT NOT NULL,
    entered_at TEXT NOT NULL DEFAULT (datetime('now')),
    exited_at TEXT,
    trigger_input_id TEXT REFERENCES inputs(id)
);

CREATE TABLE IF NOT EXISTS reviews (
    id TEXT PRIMARY KEY,
    deal_id TEXT NOT NULL REFERENCES deals(id),
    note TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS hindsight_records (
    deal_id TEXT PRIMARY KEY REFERENCES deals(id),
    stage_reached TEXT NOT NULL,
    outcome TEXT NOT NULL,
    outcome_reason TEXT,
    signal_summary TEXT NOT NULL,
    embedding_id TEXT,
    written_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Every notable event (new input matched, stage change, couldn't auto-match)
-- writes here so the user gets told, and so a future UI has one place to poll.
CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    deal_id TEXT REFERENCES deals(id),
    input_id TEXT REFERENCES inputs(id),
    kind TEXT NOT NULL,        -- new_input / stage_change / unmatched_input / stalled
    message TEXT NOT NULL,
    read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_inputs_deal ON inputs(deal_id);
CREATE INDEX IF NOT EXISTS idx_inputs_thread ON inputs(thread_id);
CREATE INDEX IF NOT EXISTS idx_inputs_parent ON inputs(parent_input_id);
CREATE INDEX IF NOT EXISTS idx_inputs_message_id ON inputs(message_id);
CREATE INDEX IF NOT EXISTS idx_stage_history_deal ON deal_stage_history(deal_id);
CREATE INDEX IF NOT EXISTS idx_notifications_deal ON notifications(deal_id);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    deal_id TEXT NOT NULL REFERENCES deals(id),
    role TEXT NOT NULL,   -- 'user' or 'agent'
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_chat_deal ON chat_messages(deal_id);

-- Chain-of-reasoning memory. Distinct from hindsight_records (which is
-- retrieval across OTHER closed deals). This chain is the agent's own
-- accumulated understanding of THIS deal, turn over turn: each node links
-- to the one before it, so reasoning carries forward instead of being
-- recomputed fresh every time (which is what plain RAG does).
CREATE TABLE IF NOT EXISTS reasoning_chain (
    id TEXT PRIMARY KEY,
    deal_id TEXT NOT NULL REFERENCES deals(id),
    parent_reasoning_id TEXT REFERENCES reasoning_chain(id),
    trigger TEXT NOT NULL,       -- the user message or new input that prompted this reasoning
    reasoning TEXT NOT NULL,     -- the agent's updated understanding/conclusion
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_reasoning_deal ON reasoning_chain(deal_id);
