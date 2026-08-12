"""
Coco 房产助理 - 定时任务自动注册
首次对话时自动注册每日早报/午间检查/跟进提醒到飞书会话
"""
import logging
import os

logger = logging.getLogger(__name__)

# 标记文件：防止重复注册（放在 HERMES_HOME 下，与 cron 存储一致）
_MARKER = ".coco_cron_registered"
_CRON_JOBS = (
    ("coco_daily_report", "0 9 * * *", "coco_daily_report",
     "你是Coco房产助理。请直接调用 daily_report 工具生成每日早报（不要使用 tool_call，直接调用工具），然后用简洁清单体向经纪人汇报：今日待跟进客户、S/A级客户状态、逾期预警。不要添加额外内容。"),
    ("coco_midday_check", "0 13 * * *", "coco_midday_check",
     "你是Coco房产助理。请直接调用 midday_check 工具做午间检查（不要使用 tool_call，直接调用工具），汇报：逾期未跟进客户、今日剩余任务。没有异常就简短回复'今日无异常'。"),
    ("coco_overdue_check", "*/30 * * * *", "coco_overdue_check",
     "你是Coco房产助理。请直接调用 get_overdue 工具检查逾期客户（不要使用 tool_call，直接调用工具）。如果有逾期客户，列出客户名和逾期天数，提醒经纪人尽快跟进。如果没有逾期客户，只回复[SILENT]不要输出任何其他内容。"),
    ("coco_birthday_check", "0 8 * * *", "coco_birthday_check",
     "你是Coco房产助理。请直接调用 birthday_check 工具检查今天和明天过生日的客户（不要使用 tool_call，直接调用工具）。如果有，列出客户名和生日，提醒经纪人发送祝福维护关系。如果没有，只回复[SILENT]不要输出任何其他内容。"),
)

# 脚本型 watchdog 任务（no_agent）：不走 LLM，异常才输出告警，正常静默（2026-08-12 加）
_WATCHDOG_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "scripts", "watchdog_alert.py")
_WATCHDOG_JOB = ("coco_watchdog", "0 */6 * * *", "coco_watchdog",
                 "备份/密钥/磁盘/服务 watchdog（每 6 小时，异常告警，正常静默）",
                 {"script": _WATCHDOG_SCRIPT, "no_agent": True})


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
    """注册 Coco 定时任务到指定飞书会话（仅一次）

    Args:
        chat_id: 飞书会话 ID

    Returns:
        dict: {"registered": [job names], "skipped": [job names]}
    """
    result = {"registered": [], "skipped": []}
    marker = _marker_path()
    all_jobs = list(_CRON_JOBS) + [_WATCHDOG_JOB]

    # 标记存在则跳过（幂等）；缺失任务由 _job_exists 兜底补注册
    if os.path.exists(marker):
        # 检查是否有缺失任务需要补注册（兼容 4 元组提示词任务与 5 元组脚本任务）
        missing = [name for item in all_jobs if not _job_exists(item[2])]
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
