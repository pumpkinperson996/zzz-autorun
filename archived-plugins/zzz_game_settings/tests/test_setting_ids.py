"""目标值组装测试。"""
from plugins.zzz_game_settings import setting_ids


def test_run_requirement_only_when_low_quality_off() -> None:
    targets = setting_ids.build_targets(setting_ids.FRAME_RATE_60, low_quality=False)
    assert targets == {
        setting_ids.ID_CAMERA_AUTO_FOLLOW: 0,
        setting_ids.ID_DAMAGE_NUMBER: 0,
        setting_ids.ID_FONT_OPTION: 2,
        setting_ids.ID_FRAME_RATE: setting_ids.FRAME_RATE_60,
    }


def test_low_quality_adds_graphics() -> None:
    targets = setting_ids.build_targets(setting_ids.FRAME_RATE_30, low_quality=True)
    assert targets[setting_ids.ID_FRAME_RATE] == setting_ids.FRAME_RATE_30
    assert targets[setting_ids.ID_SCENE_QUALITY] == 0
    assert targets[setting_ids.ID_ANTI_ALIASING] == 0
    assert targets[setting_ids.ID_GLOBAL_ILLUMINATION] == 0
    # 运行要求项仍在
    assert targets[setting_ids.ID_CAMERA_AUTO_FOLLOW] == 0
    assert len(targets) == 20  # 4 运行要求 + 16 画质
