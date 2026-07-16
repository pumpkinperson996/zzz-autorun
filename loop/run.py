"""实机实验闭环 —— 主循环

    基线采样 → [ 执行方提补丁 → 栏杆 → 落盘 → 实机采样 → 比成功率 ] × N → 日报

## 决策方去哪了？
design.md 写「Claude 提假设定方向、执行方干活」。但凌晨三点 Claude 不在 ——
Claude Code 不是常驻服务, 且 .env 里只有 Fireworks 的 key。
所以本循环在物理上只能是: **执行方提方案, 栏杆与实机做裁决, 停止条件兜底**。
「决策方醒来」的真实形态 = 停止后写进日报, 等下一次会话被读到。
这是约束下唯一诚实的形态, 不是设计打折。

## 为什么这样还能信
因为裁决的两样东西都不在执行方的可改范围内:
  guard.py  文件层拦截, 机械, 不靠提示词
  实机成功率 游戏说了算, 模型改不了游戏
执行方能做的最坏情况是「提一堆没用的补丁」, 而每一轮都要过实机 —— 成功率不涨就回滚。

## 停止条件(design.md D1 / tasks 4.3)
  · 连续 3 轮成功率相对基线无提升 → 停, 写日报
  · 补丁被栏杆拒绝 → 停, 上报(可能是模型想越界)
  · 采样中断(游戏状态无法恢复/单跑道被占) → 停
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time

from . import executor, guard, oracle

PLUGIN_DIR = r'C:\ZZZ-OD\plugins\lost_void_film'
OUT_ROOT = r'C:\ZZZ-OD\.debug\temp\lost_void_film\_keep_loop'

MAX_ROUNDS = 3
SAMPLES = 3

PATCH_SCHEMA = {
    'type': 'object',
    'properties': {
        'reasoning': {'type': 'string'},
        'hypothesis': {'type': 'string', 'description': '这一轮你在验证什么假设'},
        'patches': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'old_string': {'type': 'string', 'description': '与源文件逐字符一致且唯一'},
                    'new_string': {'type': 'string'},
                    'why': {'type': 'string'},
                },
                'required': ['old_string', 'new_string', 'why'],
            },
        },
        'give_up': {'type': 'boolean', 'description': '若认为在允许范围内无解, 置 true 并说明'},
        'give_up_reason': {'type': 'string'},
    },
    'required': ['reasoning', 'hypothesis', 'patches', 'give_up', 'give_up_reason'],
}

_RULES = """## 硬约束(机制强制, 违反会被栏杆拒绝, 补丁不会落盘)
1. 只能改 plugins/lost_void_film/ 下的非测试文件
2. 不得改 src/(零侵入 + 启动器 reset --hard 会抹掉)、config/、assets/、ZZZ-autorun/
3. 既有测试只读; conftest.py / pytest.ini 只读
4. 不得出现 clear_ether8_tasks(用户取舍, 属 D 类须人工裁决)
5. **判据是实机成功率, 不是测试全绿。** 不要为了"修好"而放宽判定逻辑
   (例如让名字匹配更宽松)——那会制造假阳性, 而实机会把它顶出来。
6. 若你认为在以上范围内无解(例如根因在 src/), 置 give_up=true 并说明 ——
   诚实的"做不到"比一个没用的补丁有价值。
"""


def _git(*args: str) -> str:
    return subprocess.run(['git', *args], cwd=PLUGIN_DIR, capture_output=True,
                          text=True, encoding='utf-8').stdout


def _rollback() -> None:
    _git('checkout', '--', '.')


def _tests_pass() -> bool:
    r = subprocess.run([r'C:\ZZZ-OD\.venv\Scripts\python.exe', '-m', 'pytest', '-q'],
                       cwd=os.path.join(PLUGIN_DIR, 'tests'),
                       capture_output=True, text=True, encoding='utf-8')
    return r.returncode == 0


def _read(rel: str) -> str:
    with open(os.path.join(PLUGIN_DIR, rel), encoding='utf-8') as f:
        return f.read()


def _numbered(rel: str) -> str:
    return '\n'.join(f'{i + 1}: {ln}' for i, ln in enumerate(_read(rel).split('\n')))


def apply_patches(rel: str, patches: list[dict]) -> tuple[bool, str]:
    """过栏杆 → 校验唯一性 → 落盘。任一步失败则原样不动"""
    path_for_guard = f'plugins/lost_void_film/{rel}'
    cur = _read(rel)
    for p in patches:
        try:
            guard.check_write(path_for_guard, p['new_string'])
        except guard.Rejected as e:
            return False, f'栏杆拒绝: {e}'
        if cur.count(p['old_string']) != 1:
            return False, f"old_string 匹配 {cur.count(p['old_string'])} 次(需恰好1次)"
        cur = cur.replace(p['old_string'], p['new_string'], 1)
    with open(os.path.join(PLUGIN_DIR, rel), 'w', encoding='utf-8') as f:
        f.write(cur)
    return True, ''


async def fix_case(backend, ctx, *, name: str, targets: list[str], rel: str,
                   brief: str) -> dict:
    """对一个案子跑闭环: 基线 → 迭代 → 日报"""
    out = os.path.join(OUT_ROOT, f'{time.strftime("%Y%m%d_%H%M%S")}_{name}')
    os.makedirs(out, exist_ok=True)
    log: dict = {'case': name, 'targets': targets, 'rounds': []}

    if _git('status', '--porcelain').strip():
        return {**log, 'stopped': '工作区不干净 —— 拒绝在未提交的改动上跑循环'}

    print(f'\n{"=" * 62}\n案子: {name}\n目标: {targets}\n{"=" * 62}')
    print(f'\n[基线] 采样 {SAMPLES} 次 ...')
    base = await oracle.sample_success_rate(backend, ctx, targets, SAMPLES, out)
    log['baseline'] = base
    if base['aborted']:
        return {**log, 'stopped': f'基线采样中断: {base["aborted"]}'}
    print(f'  基线成功率 {base["rate"]:.0%}   逐人命中 {base["per_agent"]}')

    no_gain = 0
    for rnd in range(MAX_ROUNDS):
        print(f'\n[第{rnd + 1}轮] 执行方提方案 ...')
        prompt = (
            f'你是实机实验闭环的执行方。目标: 提高下面这个场景的**实机成功率**。\n\n'
            f'## 案情\n{brief}\n\n'
            f'## 当前实测\n基线成功率 {base["rate"]:.0%}, 逐人命中次数 {base["per_agent"]} '
            f'(采样 {base["n"]} 次)\n历史轮次: '
            f'{json.dumps([{k: r[k] for k in ("hypothesis", "rate", "verdict")} for r in log["rounds"]], ensure_ascii=False)}\n\n'
            f'{_RULES}\n\n## 源码 {rel} (行号已标)\n{_numbered(rel)}\n'
        )
        try:
            prop, _ = executor.ask(prompt, PATCH_SCHEMA, max_tokens=14000)
        except executor.ExecutorError as e:
            log['stopped'] = f'执行方调用失败: {e}'
            break

        if prop['give_up']:
            print(f'  执行方认为无解: {prop["give_up_reason"][:150]}')
            log['stopped'] = f'执行方放弃(诚实): {prop["give_up_reason"]}'
            break

        print(f'  假设: {prop["hypothesis"][:110]}')
        ok, err = apply_patches(rel, prop['patches'])
        if not ok:
            print(f'  ✗ {err}')
            log['rounds'].append({'hypothesis': prop['hypothesis'], 'rate': None,
                                  'verdict': f'补丁未落盘: {err}'})
            if '栏杆拒绝' in err:
                log['stopped'] = f'补丁越界, 停并上报: {err}'
                break
            continue

        if not _tests_pass():
            # 测试不是判据, 但它红了说明改坏了既有行为 —— 直接回滚
            _rollback()
            print('  ✗ 测试变红 → 回滚')
            log['rounds'].append({'hypothesis': prop['hypothesis'], 'rate': None,
                                  'verdict': '测试变红, 已回滚'})
            no_gain += 1
            continue

        print(f'  已落盘, 实机采样 {SAMPLES} 次 ...')
        s = await oracle.sample_success_rate(backend, ctx, targets, SAMPLES, out)
        if s['aborted']:
            _rollback()
            log['stopped'] = f'采样中断: {s["aborted"]} (已回滚本轮)'
            break

        gained = s['rate'] > base['rate']
        verdict = f'{base["rate"]:.0%} -> {s["rate"]:.0%} {"提升 ✓ 保留" if gained else "无提升 ✗ 回滚"}'
        print(f'  {verdict}   逐人命中 {s["per_agent"]}')
        log['rounds'].append({'hypothesis': prop['hypothesis'], 'rate': s['rate'],
                              'per_agent': s['per_agent'], 'verdict': verdict,
                              'diff': _git('diff', '--stat')})
        if gained:
            base = s
            no_gain = 0
        else:
            _rollback()
            no_gain += 1
            if no_gain >= MAX_ROUNDS:
                log['stopped'] = f'连续 {no_gain} 轮无提升 —— 停, 别磨'
                break

    log.setdefault('stopped', f'跑满 {MAX_ROUNDS} 轮')
    log['final_rate'] = base['rate']
    log['final_per_agent'] = base['per_agent']
    with open(os.path.join(out, 'digest.json'), 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    print(f'\n{"=" * 62}\n停止原因: {log["stopped"]}\n最终成功率: {log["final_rate"]:.0%}  '
          f'{log["final_per_agent"]}\n日报: {out}\\digest.json\n{"=" * 62}')
    return log


async def main() -> None:
    sys.path.insert(0, r'C:\ZZZ-OD')
    sys.path.insert(0, r'C:\ZZZ-OD\src')
    sys.path.insert(0, r'C:\ZZZ-OD\plugins')
    os.chdir(r'C:\ZZZ-OD')
    from zzz_od.backend.backend_context import ZzzBackendContext
    from zzz_od.context.zzz_context import ZContext

    ctx = ZContext()
    backend = ZzzBackendContext(ctx)
    await backend.start()
    try:
        ctx.controller.init_game_win()
        if not ctx.controller.is_game_window_ready:
            print('游戏窗口未就绪')
            return
        await fix_case(
            backend, ctx,
            name='banyue_not_picked',
            targets=['卢西娅', '般岳', '伊德海莉'],
            rel='trial_team_select.py',
            brief=(
                '实机现状: 卢西娅经方式1模板匹配命中; 伊德海莉经方式2兜底命中; **般岳两条路都不中**。\n'
                '已排除(有实测证据, 别再论证):\n'
                '  · 非「角色不在名单」: 20页扫到底的名册核查确认 般岳在选人器第0页, 名单共48人\n'
                '  · 非偏移问题: 偏移已按实测值修正(dx=-64 dy=-111), 伊德海莉因此被救回, 般岳未动\n'
                '  · 非滚动泄漏: 已加 _scroll_picker_to_top(), 每个角色从顶部开始, 般岳仍未中\n'
                '  · 非 OCR 问题: 该帧 OCR 全部 0.999+; agent_resolved=true\n'
                '现有假设(未验证): 般岳可能是暗化的试用/未拥有格子, SIFT 特征匹配对亮度敏感 →\n'
                '  方式1失效; 而方式2逐格点击后靠左侧预览面板读名字, 理应能认出 —— 但也没中。\n'
                '  注意: match_team_agent_template 在 src/ 下, 属禁区, 不可改。\n'
                '若你认为在 plugins/ 范围内确实无解, 请诚实 give_up 并说明根因位置。'
            ),
        )
    finally:
        await backend.shutdown()


if __name__ == '__main__':
    asyncio.run(main())
