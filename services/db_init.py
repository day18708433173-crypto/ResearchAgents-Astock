"""镜衡数据库初始化 - MVP P0 核心表结构"""

import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "jingheng.db"


def init_database():
    """初始化数据库表结构"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    
    # ═══════════════════════════════════════════════
    # 卷宗表 (Dossier)
    # ═══════════════════════════════════════════════
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dossier (
            dossier_id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL UNIQUE,
            stock_name TEXT NOT NULL,
            industry TEXT DEFAULT '',
            user_id TEXT DEFAULT 'default_user',
            current_hold_shares INTEGER DEFAULT 0,
            current_strategy_version INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    
    # ═══════════════════════════════════════════════
    # 策略版本表 (StrategyVersion)
    # ═══════════════════════════════════════════════
    conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_version (
            version_id INTEGER PRIMARY KEY AUTOINCREMENT,
            dossier_id INTEGER NOT NULL,
            version_number INTEGER NOT NULL,
            is_active INTEGER DEFAULT 1,
            strategy_content TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (dossier_id) REFERENCES dossier(dossier_id)
        )
    """)
    
    # ═══════════════════════════════════════════════
    # 修改理由表 (StrategyChangeReason)
    # ═══════════════════════════════════════════════
    conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_change_reason (
            reason_id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER NOT NULL,
            summary TEXT NOT NULL,
            conversation_ref TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (version_id) REFERENCES strategy_version(version_id)
        )
    """)
    
    # ═══════════════════════════════════════════════
    # 交易记录表 (Transaction) - 不可删除/编辑
    # ═══════════════════════════════════════════════
    # 注意：transaction是SQLite保留关键字，需要用双引号包裹
    conn.execute("""
        CREATE TABLE IF NOT EXISTS "transaction" (
            txn_id INTEGER PRIMARY KEY AUTOINCREMENT,
            dossier_id INTEGER NOT NULL,
            direction TEXT NOT NULL CHECK(direction IN ('buy', 'sell')),
            price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            txn_time TEXT NOT NULL,
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (dossier_id) REFERENCES dossier(dossier_id)
        )
    """)
    
    # ═══════════════════════════════════════════════
    # 提醒记录表 (Alert)
    # ═══════════════════════════════════════════════
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alert (
            alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
            dossier_id INTEGER NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('buy', 'sell')),
            triggered_version_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            sent_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (dossier_id) REFERENCES dossier(dossier_id),
            FOREIGN KEY (triggered_version_id) REFERENCES strategy_version(version_id)
        )
    """)
    
    # ═══════════════════════════════════════════════
    # 辩论记录表 (DebateRecord)
    # ═══════════════════════════════════════════════
    conn.execute("""
        CREATE TABLE IF NOT EXISTS debate_record (
            debate_id INTEGER PRIMARY KEY AUTOINCREMENT,
            dossier_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            ticker_name TEXT DEFAULT '',
            content TEXT NOT NULL,
            generated_at TEXT DEFAULT (datetime('now')),
            debate_date TEXT NOT NULL,
            template_id TEXT DEFAULT '',
            FOREIGN KEY (dossier_id) REFERENCES dossier(dossier_id)
        )
    """)
    
    # ═══════════════════════════════════════════════
    # Agent对话记录表
    # ═══════════════════════════════════════════════
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_conversation (
            conversation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            dossier_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('agent', 'user')),
            content TEXT NOT NULL,
            timestamp TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (dossier_id) REFERENCES dossier(dossier_id)
        )
    """)
    
    # ═══════════════════════════════════════════════
    # 每日辩论次数限制索引
    # ═══════════════════════════════════════════════
    # ═══════════════════════════════════════════════
    # 提醒规则表 (AlertRule) - 用户设置的提醒触发条件
    # ═══════════════════════════════════════════════
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alert_rule (
            rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
            dossier_id INTEGER NOT NULL,
            rule_type TEXT NOT NULL CHECK(rule_type IN ('price_target', 'price_change', 'indicator', 'time_based')),
            target_type TEXT NOT NULL CHECK(target_type IN ('buy', 'sell', 'review')),
            trigger_condition TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            last_triggered_at TEXT,
            trigger_count INTEGER DEFAULT 0,
            FOREIGN KEY (dossier_id) REFERENCES dossier(dossier_id)
        )
    """)
    
    # ═══════════════════════════════════════════════
    # 扩展 alert 表，增加 rule_id 关联
    # ═══════════════════════════════════════════════
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alert_new (
            alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
            dossier_id INTEGER NOT NULL,
            rule_id INTEGER,
            type TEXT NOT NULL CHECK(type IN ('buy', 'sell', 'review', 'info')),
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            triggered_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (dossier_id) REFERENCES dossier(dossier_id),
            FOREIGN KEY (rule_id) REFERENCES alert_rule(rule_id)
        )
    """)
    
    # 迁移旧数据（如果存在）
    try:
        conn.execute("""
            INSERT INTO alert_new (dossier_id, rule_id, type, title, message, is_read, triggered_at)
            SELECT dossier_id, NULL, type, type, message, is_read, sent_at FROM alert
        """)
        conn.execute("DROP TABLE alert")
        conn.execute("ALTER TABLE alert_new RENAME TO alert")
    except:
        pass
    
    _ensure_debate_tables(conn)
    _ensure_dossier_commission_columns(conn)
    conn.commit()
    conn.close()
    print(f"[DB] Database initialized at {DB_PATH}")


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _ensure_debate_tables(conn: sqlite3.Connection):
    """Align debate tables with modules.debate.orchestrator."""
    debate_columns = _table_columns(conn, "debate_record")
    if debate_columns and ("id" not in debate_columns or "coverage" not in debate_columns):
        conn.execute("ALTER TABLE debate_record RENAME TO debate_record_legacy")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS debate_record (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            ticker_name TEXT,
            template_id TEXT,
            coverage INTEGER,
            rounds TEXT,
            data_card_id INTEGER,
            judge_verdict TEXT,
            accuracy_grade TEXT,
            total_llm_calls INTEGER,
            estimated_cost REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='debate_record_legacy'").fetchone():
        legacy_columns = _table_columns(conn, "debate_record_legacy")
        if {"ticker", "ticker_name", "template_id"}.issubset(legacy_columns):
            content_expr = "content" if "content" in legacy_columns else "'[]'"
            created_expr = "generated_at" if "generated_at" in legacy_columns else "datetime('now')"
            conn.execute(f"""
                INSERT INTO debate_record (ticker, ticker_name, template_id, coverage, rounds, created_at)
                SELECT ticker, ticker_name, template_id, 0, {content_expr}, {created_expr}
                FROM debate_record_legacy
            """)
        conn.execute("DROP TABLE debate_record_legacy")

    agent_columns = _table_columns(conn, "agent_conversation")
    if agent_columns and ("debate_id" not in agent_columns or "agent_role" not in agent_columns):
        conn.execute("ALTER TABLE agent_conversation RENAME TO agent_conversation_legacy")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_conversation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            debate_id INTEGER,
            round_num INTEGER,
            agent_role TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='agent_conversation_legacy'").fetchone():
        conn.execute("DROP TABLE agent_conversation_legacy")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_debate_created_at ON debate_record(created_at)")


def _ensure_dossier_commission_columns(conn: sqlite3.Connection):
    """卷宗佣金配置：最低佣金 + 费率（小数，如万2.5 存 0.00025）"""
    columns = _table_columns(conn, "dossier")
    if "commission_min" not in columns:
        conn.execute("ALTER TABLE dossier ADD COLUMN commission_min REAL")
    if "commission_rate" not in columns:
        conn.execute("ALTER TABLE dossier ADD COLUMN commission_rate REAL")


def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


if __name__ == "__main__":
    init_database()
