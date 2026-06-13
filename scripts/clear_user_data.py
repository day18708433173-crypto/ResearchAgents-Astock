"""清空镜衡用户业务数据（卷宗、交易、辩论等），保留表结构。"""

import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "jingheng.db"

# 仅清理业务使用记录，不触碰 rag_vectors.db / rag_cache.db 等知识库缓存
USER_TABLES = [
    "agent_conversation",
    "alert",
    "alert_rule",
    "strategy_alert",
    "strategy_change_reason",
    "strategy_version",
    "transaction",
    "debate_record",
    "data_cards",
    "dossier",
]


def count_rows(conn: sqlite3.Connection, table: str) -> int:
    sql = f'SELECT COUNT(*) FROM "{table}"' if table == "transaction" else f"SELECT COUNT(*) FROM {table}"
    return conn.execute(sql).fetchone()[0]


def clear_user_data() -> None:
    if not DB_PATH.exists():
        print(f"[skip] 数据库不存在: {DB_PATH}")
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = OFF")

    print(f"清理前 ({DB_PATH.name}):")
    for table in USER_TABLES:
        try:
            print(f"  {table}: {count_rows(conn, table)} rows")
        except sqlite3.OperationalError:
            print(f"  {table}: (表不存在，跳过)")

    for table in USER_TABLES:
        try:
            sql = f'DELETE FROM "{table}"' if table == "transaction" else f"DELETE FROM {table}"
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass

    conn.execute("DELETE FROM sqlite_sequence WHERE name IN ({})".format(
        ",".join("?" * len(USER_TABLES))
    ), USER_TABLES)

    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")
    conn.close()

    conn = sqlite3.connect(str(DB_PATH))
    print(f"\n清理后 ({DB_PATH.name}):")
    for table in USER_TABLES:
        try:
            print(f"  {table}: {count_rows(conn, table)} rows")
        except sqlite3.OperationalError:
            print(f"  {table}: (表不存在)")
    conn.close()
    print("\n[done] 用户业务数据已清空。")


if __name__ == "__main__":
    clear_user_data()
