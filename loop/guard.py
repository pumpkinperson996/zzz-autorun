"""闭环安全锁 —— 文件层拦截，不靠提示词自觉

design.md 的四条锁里，「改动范围」这条必须在机制层强制。理由不是不信任模型，而是
提示词在凌晨三点不成立: 一个被「让测试变绿 / 让成功率上去」驱动的模型，会找到任何
没被机制堵死的路。本轮设计的前一版就是被这样打穿的 —— 六种绕过方式里有三种已在本仓
实测确认(见 design.md D1)。

本模块只做一件事: 给定一个待写入的路径与内容, 回答放行还是拒绝, 并给出理由。
调用方(补丁应用器)必须在落盘前问过它。
"""
from __future__ import annotations

import os
import re

# 唯一允许改动的目录 —— 闭环的作用对象
ALLOWED_ROOT = 'plugins/lost_void_film'

# 明令禁止的目录
# src/     : 插件的立身之本是零侵入; 且启动器自动更新 git_service.py:257 _reset_hard
#            会把对 src/ 的任何修改抹掉 —— 改了也白改, 还会掩盖真实原因
# config/  : 用户的真实配置与缺口缓存, 不是代码
# assets/  : 模板与模型。感知类(A类)故障必须由人补模板 —— 模型调阈值只会让
#            另外 199 个场景悄悄变坏, 而这种坏没有任何判据能抓住
# ZZZ-autorun/ : 闭环自身。模型不得改自己的栏杆
FORBIDDEN_ROOTS = (
    'src/',
    'config/',
    'assets/',
    'ZZZ-autorun/',
    '.git/',
)

# 冻结常量: 花真实资源或体现用户取舍的开关。命中即拒, 归 D 类上报由人裁决
# clear_ether8_tasks: 用户 2026-07-15 明确「不做」。ether>=8 任务 0 菲林、最难、
#   失败率最高。模型看到「不够积极」会非常想把它打开
FROZEN_CONSTANTS = (
    'clear_ether8_tasks',
)

# 保护既有测试: 只允许新增 tests/regression/test_*.py, 不得改动或删除已有测试文件
# 注: 成功率才是判据(design.md D1), 测试不是。但既有测试是行为规格 ——
#   例如 test_pool_planner.py 的四条 == ['x'] 断言编码了 min(3, available) 的正确语义,
#   一个「必须凑满3人」的错误修复会让它们变红。那是它们在正常工作, 不是它们是地雷。
TEST_DIR = 'tests'
REGRESSION_DIR = 'tests/regression'


class Rejected(Exception):
    """改动被安全锁拒绝"""


def _norm(path: str) -> str:
    """统一成相对仓库根、正斜杠的形式"""
    p = path.replace('\\', '/')
    low = p.lower()
    marker = 'zzz-od/'
    if marker in low:
        p = p[low.rindex(marker) + len(marker):]
    return p.lstrip('./')


def check_write(path: str, content: str | None = None, *, exists: bool | None = None) -> None:
    """校验一次待写入。放行则返回 None, 否则抛 Rejected。

    Args:
        path: 目标路径(绝对或相对仓库根均可)
        content: 待写入内容。None 表示只校验路径
        exists: 目标是否已存在。None 表示由本函数自行判断(仅当 path 为绝对路径时可靠)

    Raises:
        Rejected: 带明确理由, 调用方应原样上报决策方
    """
    rel = _norm(path)

    for root in FORBIDDEN_ROOTS:
        if rel.startswith(root):
            raise Rejected(f'禁止改动 {root} —— 路径 {rel}')

    if not rel.startswith(ALLOWED_ROOT + '/'):
        raise Rejected(f'改动范围仅限 {ALLOWED_ROOT}/ —— 路径 {rel}')

    inner = rel[len(ALLOWED_ROOT) + 1:]

    # 既有测试只读; 新增回归测试仅限 tests/regression/test_*.py
    if inner.startswith(TEST_DIR + '/'):
        if not inner.startswith(REGRESSION_DIR + '/'):
            raise Rejected(
                f'既有测试为只读 —— {rel}。新增回归测试请放 {ALLOWED_ROOT}/{REGRESSION_DIR}/test_*.py'
            )
        name = os.path.basename(inner)
        if not (name.startswith('test_') and name.endswith('.py')):
            raise Rejected(
                f'{REGRESSION_DIR}/ 下只接受 test_*.py —— {rel}。'
                f'conftest.py / pytest.ini / __init__.py 等可改变整个测试会话行为, 一律拒绝'
            )
        if exists is None:
            exists = os.path.isabs(path) and os.path.exists(path)
        if exists:
            raise Rejected(f'回归测试只增不改 —— {rel} 已存在')

    # pytest 配置是判据的开关, 不是测试文件, 单独堵
    if os.path.basename(rel) in ('pytest.ini', 'conftest.py', 'pyproject.toml', 'setup.cfg', 'tox.ini'):
        raise Rejected(f'测试配置为只读 —— {rel}。它决定哪些断言会被执行, 属于判据本身')

    if content is not None:
        for const in FROZEN_CONSTANTS:
            # 裸名匹配, 不限定后随符号。真实写法五花八门:
            #   clear_ether8_tasks: bool = True
            #   return self.get('clear_ether8_tasks', True)
            #   cfg.clear_ether8_tasks = True
            # 只要补丁提到这个名字就拒并上报 —— 宁可多拦一个正当重构, 也不能漏掉
            # 一次「让它更积极」的自作主张。这属 D 类, 本就该由人看。
            if re.search(rf'\b{re.escape(const)}\b', content):
                raise Rejected(
                    f'{const} 已冻结(用户取舍, 非缺陷) —— {rel}。'
                    f'该诉求属 D 类, 应上报人工裁决而非自动改动'
                )


def check_all(paths_and_contents: dict[str, str | None]) -> list[str]:
    """批量校验, 返回全部拒绝理由(空列表表示全部放行)"""
    out: list[str] = []
    for p, c in paths_and_contents.items():
        try:
            check_write(p, c)
        except Rejected as e:
            out.append(str(e))
    return out


if __name__ == '__main__':
    # 自检: 每条锁都必须真的拦得住
    def blocked(path: str, content: str | None = None) -> str:
        try:
            check_write(path, content)
        except Rejected as e:
            return str(e)
        raise AssertionError(f'应当被拒绝却放行了: {path}')

    def allowed(path: str, content: str | None = None) -> None:
        check_write(path, content, exists=False)

    # 越界目录
    assert 'src/' in blocked('src/zzz_od/application/hollow_zero/lost_void/lost_void_app.py')
    assert 'config/' in blocked('config/01/lost_void_film/lost_void.yml')
    assert 'assets/' in blocked('assets/template/agent_state/x.png')
    assert 'ZZZ-autorun/' in blocked('ZZZ-autorun/loop/guard.py')
    # 范围外
    assert '仅限' in blocked('plugins/unattended_guardian/guardian_loop.py')
    # 既有测试只读
    assert '只读' in blocked('plugins/lost_void_film/tests/test_pool_planner.py')
    # conftest / pytest.ini —— 前一版被打穿的两条路
    assert blocked('plugins/lost_void_film/tests/regression/conftest.py')
    assert blocked('plugins/lost_void_film/tests/pytest.ini')
    # 冻结常量
    assert 'clear_ether8_tasks' in blocked(
        'plugins/lost_void_film/lost_void_film_config.py',
        "    return self.get('clear_ether8_tasks', True)")
    # 绝对路径同样识别
    assert 'src/' in blocked(r'C:\ZZZ-OD\src\one_dragon\utils\cv2_utils.py')

    # 正常改动放行
    allowed('plugins/lost_void_film/pool_planner.py', 'def x(): return 3')
    allowed('plugins/lost_void_film/tests/regression/test_case_20260715.py', 'def test_x(): pass')

    print('[OK] 安全锁自检通过: 越界目录 / 范围外 / 既有测试 / conftest / pytest.ini / 冻结常量 均已拦截')
