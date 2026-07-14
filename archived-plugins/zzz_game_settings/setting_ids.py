"""绝区零游戏设置 SystemSettingDataMap 的 ID 常量与默认目标值。

ID 与取值均为 2026-07-03 实测（游戏当时国服最新版本）。游戏版本更新可能改变
ID 含义或新增枚举，维护时集中改这一处。取值语义见每项注释。
"""

# ---------- 运行要求项（一条龙正常运行所必须） ----------

ID_CAMERA_AUTO_FOLLOW: int = 87
"""镜头自动跟随转动：0=关闭 1=开启。模拟按键以关闭为前提。"""

ID_DAMAGE_NUMBER: int = 74
"""战斗伤害跳字显示：0=关闭 1=默认效果 2=跳字合并。"""

ID_FONT_OPTION: int = 10147
"""字体选项：0=推荐方案 1=全局粗体 2=全局细体。细体利于文本识别。"""

ID_FRAME_RATE: int = 110
"""帧率：0=30 1=60 2=无限制。禁止无限制。"""

# ---------- 低负载画质项 ----------

ID_VSYNC: int = 8
"""垂直同步：0=关闭 1=开启。"""

ID_RENDER_SCALE: int = 9
"""渲染精度：0=0.8 1=1.0 2=1.2。"""

ID_SHADOW_QUALITY: int = 10
"""阴影精度：0=低 1=中 2=高。"""

ID_ANTI_ALIASING: int = 12
"""抗锯齿：0=关闭 1=TAA 2=SMAA。"""

ID_VOLUMETRIC_FOG: int = 13
"""体积雾：0=关闭 1=低 2=中 3=高。"""

ID_BLOOM: int = 14
"""高光溢出：0=关闭 1=开启。"""

ID_REFLECTION: int = 15
"""镜面反射：0=关闭 1=低 2=中 3=高。"""

ID_EFFECT_QUALITY: int = 16
"""特效质量：0=极低 1=低 2=中 3=高。"""

ID_CHARACTER_QUALITY: int = 99
"""角色质量：0=低 1=高。"""

ID_MOTION_BLUR: int = 106
"""运动模糊：0=关闭 1=开启。"""

ID_DISTORTION: int = 107
"""扭曲：0=关闭 1=开启。"""

ID_SHADING_QUALITY: int = 108
"""着色质量：0=低 1=中 2=高。"""

ID_SCENE_QUALITY: int = 109
"""场景质量：0=低 1=高。"""

ID_GLOBAL_ILLUMINATION: int = 12155
"""全局光照：0=低(遗留档位,UI已不提供) 1=中 2=高。"""

ID_CHARACTER_HIGH_PRECISION: int = 13162
"""角色动态高精度：0=关闭 1=开启。"""

ID_ANISOTROPIC: int = 16184
"""各向异性采样：0=1x 1=2x 2=4x 3=8x 4=16x。"""

# ---------- 帧率可选值 ----------

FRAME_RATE_30: int = 0
FRAME_RATE_60: int = 1


def build_run_requirement_targets(frame_rate_value: int) -> dict[int, int]:
    """运行要求项目标值。frame_rate_value 传 FRAME_RATE_30 或 FRAME_RATE_60。"""
    return {
        ID_CAMERA_AUTO_FOLLOW: 0,
        ID_DAMAGE_NUMBER: 0,
        ID_FONT_OPTION: 2,
        ID_FRAME_RATE: frame_rate_value,
    }


def build_low_quality_targets() -> dict[int, int]:
    """全部画质相关项拉到最低/关闭。"""
    return {
        ID_VSYNC: 0,
        ID_RENDER_SCALE: 0,
        ID_SHADOW_QUALITY: 0,
        ID_ANTI_ALIASING: 0,
        ID_VOLUMETRIC_FOG: 0,
        ID_BLOOM: 0,
        ID_REFLECTION: 0,
        ID_EFFECT_QUALITY: 0,
        ID_CHARACTER_QUALITY: 0,
        ID_MOTION_BLUR: 0,
        ID_DISTORTION: 0,
        ID_SHADING_QUALITY: 0,
        ID_SCENE_QUALITY: 0,
        ID_GLOBAL_ILLUMINATION: 0,
        ID_CHARACTER_HIGH_PRECISION: 0,
        ID_ANISOTROPIC: 0,
    }


def build_targets(frame_rate_value: int, low_quality: bool) -> dict[int, int]:
    """组合出本次要写入的全部目标值。

    Args:
        frame_rate_value: 帧率目标（FRAME_RATE_30 / FRAME_RATE_60）。
        low_quality: 是否同时应用最低画质；关闭时只写运行要求四项。
    """
    targets = build_run_requirement_targets(frame_rate_value)
    if low_quality:
        targets.update(build_low_quality_targets())
    return targets
