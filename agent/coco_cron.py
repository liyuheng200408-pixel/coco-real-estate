"""
Coco 房产助理 - 定时任务自动注册
首次对话时自动注册每日早报/午间检查/跟进提醒到飞书会话
"""
import logging
import os

logger = logging.getLogger(__name__)

# 标记文件：防止重复注册（放在 HERMES_HOME 下，与 cron 存储一致）
_MARKER = ".coco_cron_registered"
# ==================== Coco 定时任务（默认关闭，2026-08-12 老板决定） ====================
# 老板决策：定时任务默认不注册（消耗 token），功能保留，经纪人需要时自行开启。
# 开启方式：在 .env.db 设置 COCO_ENABLE_CRON=1 并重启服务，即注册以下任务。
_CRON_JOBS = ()

# 任务定义清单（供手动开启时参考，与 _CRON_JOBS 内容一致）
_AVAILABLE_JOBS = (
    ("coco_daily_report", "0 9 * * *", "coco_daily_report",
     "你是Coco房产助理。请直接调用 daily_report 工具生成每日早报（不要使用 tool_call，直接调用工具），然后用简洁清单体向经纪人汇报：今日待跟进客户、S/A级客户状态、逾期预警。不要添加额外内容。"),
    ("coco_midday_check", "0 13 * * *", "coco_midday_check",
     "你是Coco房产助理。请直接调用 midday_check 工具做午间检查（不要使用 tool_call，直接调用工具），汇报：逾期未跟进客户、今日剩余任务。没有异常就简短回复'今日无异常'。"),
    ("coco_overdue_check", "*/30 * * * *", "coco_overdue_check",
     "你是Coco房产助理。请直接调用 get_overdue 工具检查逾期客户（不要使用 tool_call，直接调用工具）。如果有逾期客户，列出客户名和逾期天数，提醒经纪人尽快跟进。如果没有逾期客户，只回复[SILENT]不要输出任何其他内容。"),
)
# 已取消（2026-08-12）：coco_birthday_check（生日提醒）、coco_watchdog（备份/密钥监控）


def _marker_path() -> str:
    """标记文件路径：跟随 HERMES_HOME（与 cron 存储同目录）"""
    try:
        from hermes_constants import get_hermes_home
        home = get_hermes_home()
        return os.path.join(str(home), _MARKER)
    except Exception:
        # 兜底：环境变量
        home = os.getenv("HERMES_HOME") or os.path.expanduser("~/.hermes")
        return os.path.join(home, _MARKER)


def _cron_store_ready() -> bool:
    """确认 cron 存储可用"""
    try:
        from cron.jobs import get_cron_output_dir
        get_cron_output_dir()
        return True
    except Exception:
        return False


def _job_exists(job_name: str) -> bool:
    """通过官方 list_jobs 接口检查同名任务是否已注册（不猜存储路径）"""
    try:
        from cron.jobs import list_jobs
        jobs = list_jobs(include_disabled=True)
        for job in jobs:
            if job.get("name") == job_name:
                return True
    except Exception as e:
        logger.warning("[Coco] list_jobs failed: %s", e)
    return False


def register_coco_cron_jobs(chat_id: str) -> dict:
    """注册 Coco 定时任务到指定飞书会话（默认关闭，2026-08-12 老板决定）

    默认不注册任何定时任务（消耗 token）。如需开启：在 .env.db 设置
    COCO_ENABLE_CRON=1 并重启服务，此函数才会注册 _AVAILABLE_JOBS 中的任务。

    Args:
        chat_id: 飞书会话 ID

    Returns:
        dict: {"registered": [job names], "skipped": [job names]}
    """
    result = {"registered": [], "skipped": []}

    # 开关：默认关闭；COCO_ENABLE_CRON=1 才注册
    if os.getenv('COCO_ENABLE_CRON', '0') != '1':
        logger.info("[Coco] 定时任务默认关闭（COCO_ENABLE_CRON 未设为 1），跳过注册")
        return result

    marker = _marker_path()
    all_jobs = list(_AVAILABLE_JOBS)

    # 标记存在则跳过（幂等）；缺失任务由 _job_exists 兜底补注册
    if os.path.exists(marker):
        # 检查是否有缺失任务需要补注册（兼容 4 元组提示词任务与 5 元组脚本任务）
        missing = [item[2] for item in all_jobs if not _job_exists(item[2])]
        if not missing:
            return result
        logger.info("[Coco] missing jobs to re-register: %s", missing)

    if not _cron_store_ready():
        logger.warning("[Coco] cron store not ready, skip cron registration")
        return result

    for item in all_jobs:
        job_name, schedule, name = item[0], item[1], item[2]
        if _job_exists(name):
            result["skipped"].append(name)
            continue
        try:
            from cron.jobs import create_job
            extra = {}
            prompt = item[3]
            if isinstance(prompt, dict):  # 脚本型任务（watchdog）
                extra = prompt
                prompt = None
            create_job(
                prompt=prompt,
                schedule=schedule,
                name=name,
                deliver=f"feishu:{chat_id}",
                enabled_toolsets=["real_estate"],
                **extra,
            )
            result["registered"].append(name)
            logger.info("[Coco] cron job registered: %s -> %s", name, chat_id)
        except Exception as e:
            logger.warning("[Coco] cron job %s registration failed: %s", name, e)
            result["skipped"].append(f"{name}(error)")

    # 写标记
    try:
        os.makedirs(os.path.dirname(marker), exist_ok=True)
        with open(marker, "w", encoding="utf-8") as f:
            f.write("1")
    except Exception:
        pass

    return result


def enable_coco_cron_jobs(chat_id: str) -> dict:
    """经纪人自助开启定时任务（2026-08-12 加）：注册 _AVAILABLE_JOBS 全部任务

    供工具 enable_cron 调用。与 register_coco_cron_jobs 不同：不受 COCO_ENABLE_CRON
    环境变量限制，经纪人一句话即可开启。
    """
    result = {"registered": [], "skipped": []}
    if not _cron_store_ready():
        return {"registered": [], "skipped": [], "error": "cron 存储不可用"}
    for item in _AVAILABLE_JOBS:
        job_name, schedule, name = item[0], item[1], item[2]
        if _job_exists(name):
            result["skipped"].append(name)
            continue
        try:
            from cron.jobs import create_job
            create_job(
                prompt=item[3],
                schedule=schedule,
                name=name,
                deliver=f"feishu:{chat_id}",
                enabled_toolsets=["real_estate"],
            )
            result["registered"].append(name)
            logger.info("[Coco] cron job enabled: %s -> %s", name, chat_id)
        except Exception as e:
            logger.warning("[Coco] cron job %s enable failed: %s", name, e)
            result["skipped"].append(f"{name}(error)")
    return result


def disable_coco_cron_jobs() -> dict:
    """经纪人自助关闭定时任务（2026-08-12 加）：删除已注册的 _AVAILABLE_JOBS 任务"""
    removed = []
    try:
        from cron.jobs import list_jobs, remove_job
        known = {item[2] for item in _AVAILABLE_JOBS}
        for job in list_jobs(include_disabled=True):
            name = job.get("name") or ""
            if name in known:
                remove_job(job.get("id"))
                removed.append(name)
                logger.info("[Coco] cron job disabled: %s", name)
    except Exception as e:
        logger.warning("[Coco] disable_coco_cron_jobs failed: %s", e)
        return {"removed": removed, "error": str(e)}
    return {"removed": removed}


def remove_duplicate_coco_jobs() -> int:
    """清理重复注册的 Coco 任务，保留每个任务第一个，返回删除数"""
    removed = 0
    try:
        from cron.jobs import list_jobs, remove_job
        seen = set()
        for job in list_jobs(include_disabled=True):
            name = job.get("name") or ""
            if name.startswith("coco_"):
                if name in seen:
                    try:
                        remove_job(job.get("id"))
                        removed += 1
                        logger.info("[Coco] removed duplicate job: %s (%s)", name, job.get("id"))
                    except Exception as e:
                        logger.warning("[Coco] failed to remove duplicate %s: %s", name, e)
                else:
                    seen.add(name)
    except Exception as e:
        logger.warning("[Coco] remove_duplicate_coco_jobs failed: %s", e)
    return removed
