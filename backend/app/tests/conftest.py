"""相位回归测试的公共夹具。

每个测试拿到一个隔离的临时文件 sqlite 库（通过 DATA_DIR 切换，
app.db.connect 真实读写），并先走一遍 seed.init_db()——这会先建出不带
相位列的老 weeks 表，再由 skip_week.ensure_schema 补列，因此测试同时
覆盖了“老库迁移”路径。
"""

import pytest

from app import seed
from app.db import connect


@pytest.fixture
def db_conn(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    seed.init_db()
    c = connect()
    yield c
    c.close()


@pytest.fixture
def roster(db_conn):
    """插入一组相位测试专用实体，返回各自行 id。

    3 个成员、2 个任务、3 个空周；名义周推进量 = 2*7 = 14，
    14 % 3 = 2，跨周相位接不接得上一眼可手算。
    清掉种子数据，保证“空成员”场景真的没有任何有效成员。
    """
    db_conn.execute("DELETE FROM assignments")
    db_conn.execute("DELETE FROM swap_requests")
    db_conn.execute("DELETE FROM weeks")
    db_conn.execute("DELETE FROM members")
    db_conn.execute("DELETE FROM tasks")
    member_ids = []
    for name in ("相位甲", "相位乙", "相位丙"):
        cur = db_conn.execute(
            "INSERT INTO members(name,active,data_quality) VALUES (?,1,'clean')",
            (name,))
        member_ids.append(cur.lastrowid)
    task_ids = []
    for title in ("相位任务A", "相位任务B"):
        cur = db_conn.execute(
            "INSERT INTO tasks(title,weight,data_quality) VALUES (?,1,'clean')",
            (title,))
        task_ids.append(cur.lastrowid)
    week_ids = []
    for label in ("相位W1", "相位W2", "相位W3"):
        cur = db_conn.execute(
            "INSERT INTO weeks(label,status) VALUES (?,'draft')", (label,))
        week_ids.append(cur.lastrowid)
    db_conn.commit()
    return {
        "conn": db_conn,
        "member_ids": member_ids,
        "task_ids": task_ids,
        "weeks": dict(zip(("w1", "w2", "w3"), week_ids)),
        "days": 7,
    }
