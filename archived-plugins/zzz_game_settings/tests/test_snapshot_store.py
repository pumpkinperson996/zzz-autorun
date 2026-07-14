"""快照状态存储与崩溃恢复语义测试。"""
from plugins.zzz_game_settings.snapshot_store import SnapshotStore


def _store(tmp_path) -> SnapshotStore:
    return SnapshotStore(instance_idx=0, group_id='one_dragon',
                         file_path=str(tmp_path / 'state.yml'))


def test_initial_state(tmp_path) -> None:
    store = _store(tmp_path)
    assert store.snapshot_pending is False
    assert store.snapshot_block == ''


def test_save_sets_pending(tmp_path) -> None:
    store = _store(tmp_path)
    store.save_snapshot('{block}', '2026-07-03 12:00:00')
    assert store.snapshot_pending is True
    assert store.snapshot_block == '{block}'
    assert store.snapshot_time == '2026-07-03 12:00:00'


def test_pending_persists_across_restart(tmp_path) -> None:
    """模拟崩溃：新进程用同一文件重建 store，仍应看到待还原快照。"""
    path = str(tmp_path / 'state.yml')
    s1 = SnapshotStore(0, 'one_dragon', file_path=path)
    s1.save_snapshot('{user-settings}', '2026-07-03 12:00:00')

    s2 = SnapshotStore(0, 'one_dragon', file_path=path)
    assert s2.snapshot_pending is True
    assert s2.snapshot_block == '{user-settings}'


def test_clear_pending(tmp_path) -> None:
    path = str(tmp_path / 'state.yml')
    s1 = SnapshotStore(0, 'one_dragon', file_path=path)
    s1.save_snapshot('{block}', 't')
    s1.clear_pending()

    s2 = SnapshotStore(0, 'one_dragon', file_path=path)
    assert s2.snapshot_pending is False
