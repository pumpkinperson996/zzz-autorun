"""常驻刷菲林 —— 真实目标，也是唯一诚实的素材来源

设计的第一天就写了「跑游戏从**验证手段**降级成**素材来源**」，然后我建了个手动开车
的测试台，整晚在和游戏状态搏斗。这个模块是回到正轨。

为什么这个形状对:
  · film app 自己就是循环(规划下一局 -> 执行一局 -> 局后处理, max_runs_per_session=99)
    —— 不需要 guardian 循环, 更不需要我开车
  · 它自己导航、自己选战略、自己组队 —— 我不必猜「自由编队还是预备编队」
  · 层0 证据管道在失败那一帧自动取证 —— 案子自己会累积
  · **没抓到 bug 的时候也有产出**: 菲林在涨

判据:
  主  菲林/小时 —— config/01/lost_void_film/progress.yml 的 ledger.total.earned
      这是真实目标, 模型伪造不了菲林。比「某个 op 的成功率」高一个维度:
      后者绿了而菲林没涨, 等于没修。
  次  单局成功率、各失败原因频次 —— 从 .debug/temp/lost_void_film/*/case.json 统计
"""
from __future__ import annotations

import asyncio
import json
import os
import time

PROGRESS = r'C:\ZZZ-OD\config\01\lost_void_film\progress.yml'
SNAP_ROOT = r'C:\ZZZ-OD\.debug\temp\lost_void_film'
OUT = r'C:\ZZZ-OD\.debug\temp\lost_void_film\_keep_farm'


def film_earned() -> int | None:
    """当前已获得的菲林总数 —— 主判据的原始读数"""
    try:
        import yaml
        with open(PROGRESS, encoding='utf-8') as f:
            d = yaml.safe_load(f) or {}
        return int(d['ledger']['total']['earned'])
    except Exception:
        return None


def cases() -> list[dict]:
    """已累积的案子(排除保留区)"""
    out = []
    if not os.path.isdir(SNAP_ROOT):
        return out
    for d in sorted(os.listdir(SNAP_ROOT)):
        p = os.path.join(SNAP_ROOT, d)
        if not os.path.isdir(p) or d.startswith('_keep'):
            continue
        cj = os.path.join(p, 'case.json')
        if not os.path.exists(cj):
            continue
        try:
            with open(cj, encoding='utf-8') as f:
                c = json.load(f)
            c['_dir'] = d
            c['_has_screen'] = os.path.exists(os.path.join(p, 'screen.png'))
            out.append(c)
        except Exception:
            pass
    return out


def case_histogram(cs: list[dict]) -> dict[str, int]:
    """失败原因的频次分布 —— 决定先修哪个, 而不是我挑一个去死磕"""
    h: dict[str, int] = {}
    for c in cs:
        r = str(c.get('reason', '?'))
        # 「选人器未找到-般岳」这类按前缀归并, 看的是类型不是个例
        key = r.split('-')[0] if '-' in r else r
        h[key] = h.get(key, 0) + 1
    return dict(sorted(h.items(), key=lambda kv: -kv[1]))


async def farm(backend, ctx, *, hours: float) -> dict:
    """跑 film app 刷菲林, 直到它自己收工或到时

    不干预、不开车、不测量单个 op —— 只是让它跑, 并记录菲林增量与案子分布。
    """
    from . import oracle

    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    film0 = film_earned()
    cases0 = {c['_dir'] for c in cases()}
    print(f'开跑。菲林 {film0}  已有案子 {len(cases0)} 个  预算 {hours} 小时')

    # 先回大世界这个已知起点 —— film app 从那儿能自己导航
    from zzz_od.operation.back_to_normal_world import BackToNormalWorld
    oracle.check_abort(backend)
    ok, fut = backend.start_run('farm', lambda c: BackToNormalWorld(c),
                                display_name='BackToNormalWorld')
    if ok:
        try:
            fut.result(180)
        except Exception as e:
            print(f'  回大世界失败(继续): {e}')

    rounds = []
    while time.time() - t0 < hours * 3600:
        try:
            oracle.check_abort(backend)
        except oracle.Abort as e:
            print(f'\n必停: {e}')
            break

        from lost_void_film.lost_void_film_app import LostVoidFilmApp
        print(f'\n[{time.strftime("%H:%M:%S")}] 拉起 film app ...')
        ok, fut = backend.start_run('farm', lambda c: LostVoidFilmApp(c),
                                    display_name='lost_void_film.lost_void_film_app.LostVoidFilmApp')
        if not ok:
            print('  单跑道被占, 等 60s')
            await asyncio.sleep(60)
            continue
        r0 = time.time()
        try:
            await asyncio.get_running_loop().run_in_executor(None, fut.result, hours * 3600)
        except Exception as e:
            print(f'  本轮异常: {str(e)[:150]}')
        f_now = film_earned()
        rounds.append({'at': time.strftime('%Y-%m-%d %H:%M:%S'),
                       'minutes': round((time.time() - r0) / 60, 1),
                       'film': f_now})
        print(f'  本轮结束 {(time.time() - r0) / 60:.0f}分钟  菲林 {film0} -> {f_now}')
        await asyncio.sleep(10)

    film1 = film_earned()
    cs = cases()
    new = [c for c in cs if c['_dir'] not in cases0]
    elapsed = (time.time() - t0) / 3600
    report = {
        'hours': round(elapsed, 2),
        'film_start': film0, 'film_end': film1,
        'film_gained': (film1 - film0) if (film0 is not None and film1 is not None) else None,
        'film_per_hour': round((film1 - film0) / elapsed, 1) if (film0 and film1 and elapsed) else None,
        'rounds': rounds,
        'new_cases': len(new),
        'histogram': case_histogram(new),
        'cases_with_screen': sum(1 for c in new if c['_has_screen']),
    }
    with open(os.path.join(OUT, f'{time.strftime("%Y%m%d_%H%M%S")}_farm.json'),
              'w', encoding='utf-8') as f:
        json.dump({**report, 'cases': new}, f, ensure_ascii=False, indent=2)

    print(f'\n{"=" * 58}')
    print(f'  跑了 {report["hours"]} 小时')
    print(f'  菲林 {film0} -> {film1}   增量 {report["film_gained"]}   ({report["film_per_hour"]}/小时)')
    print(f'  新案子 {report["new_cases"]} 个 (带截图 {report["cases_with_screen"]} 个)')
    print(f'  失败分布: {report["histogram"] or "无失败"}')
    print(f'{"=" * 58}')
    return report


async def main() -> None:
    import sys
    for p in (r'C:\ZZZ-OD', r'C:\ZZZ-OD\src', r'C:\ZZZ-OD\plugins'):
        sys.path.insert(0, p)
    os.chdir(r'C:\ZZZ-OD')
    from zzz_od.backend.backend_context import ZzzBackendContext
    from zzz_od.context.zzz_context import ZContext

    hours = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0
    ctx = ZContext()
    backend = ZzzBackendContext(ctx)
    await backend.start()
    try:
        ctx.controller.init_game_win()
        if not ctx.controller.is_game_window_ready:
            print('游戏窗口未就绪')
            return
        await farm(backend, ctx, hours=hours)
    finally:
        await backend.shutdown()


if __name__ == '__main__':
    asyncio.run(main())
