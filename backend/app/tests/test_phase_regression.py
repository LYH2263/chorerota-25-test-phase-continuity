"""补相位跨周连续回归测试。

场景构造在 phase_scenarios（夹具模块），手算期望与断言在 phase_assertions
（断言助手模块）；本文件只负责让 pytest 收集并逐场景执行。失败时由断言
助手打印场景名与两侧相位（前一周终点 / 后一周起点）。
"""
import pytest

from app.tests.phase_scenarios import build_scenarios
from app.tests.phase_assertions import assert_scenario

SCENARIOS = build_scenarios()


@pytest.mark.parametrize(
    "run",
    SCENARIOS,
    ids=[s.name for s in SCENARIOS],
)
def test_phase_continuity_across_weeks(run):
    assert_scenario(run)


def test_four_scenarios_collected():
    # 交付下限：至少四组场景，且名称覆盖四个规定情形
    assert len(SCENARIOS) >= 4
    names = {s.name for s in SCENARIOS}
    assert {"两周连续生成", "中间插入skip周再生成",
            "skip后取消skip重生成", "非法空成员生成"} <= names
