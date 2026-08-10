"""
Coco 房产助理 - 定时任务自动注册
首次对话时自动注册每日早报/午间检查/跟进提醒到飞书会话
"""
import logging
import os

logger = logging.getLogger(__name__)

# 标记文件：防止重复注册
_MARKER = "~/.hermes/.coco_cron_registered"
_CRON_JOBS = (
    ("coco_daily_report", "0 9 * * *", "coco_daily_report",
     "你是Coco房产助理。请调用 daily_report 工具生成每日早报，然后用简洁清单体向经纪人汇报：今日待跟进客户、S/A级客户状态、逾期预警。不要添加额外内容。"),
    ("coco_midday_check", "0 13 * * *", "coco_midday_check",
     "你是Coco房产助理。请调用 midday_check 工具做午间检查，汇报：逾期未跟进客户、今日剩余任务。没有异常就简短回复'今日无异常'。"),
    ("coco_overdue_check", "*/30 * * * *", "coco_overdue_check",
     "你是Coco房产助理。请调用 get_overdue 工具检查逾期客户。如果有逾期客户，列出客户名和逾期天数，提醒经纪人尽快跟进。如果没有逾期客户，回复[NO_ALERT]表示无异常。"),
    ("coco_birthday_check", "0 8 * * *", "coco_birthday_check",
     "你是Coco房产助理。请调用 birthday_check 工具检查今天和明天过生日的客户。如果有，列出客户名和生日，提醒经纪人发送祝福维护关系。如果没有，回复[NO_ALERT]表示无异常。"),
)


def _cron_store_ready() -> bool:
    """确认 cron 存储可用"""
    try:
        from cron.jobs import get_cron_output_dir
        get_cron_output_dir()
        return True
    except Exception:
        return False


def _job_exists(job_name: str) -> bool:
    """检查同名任务是否已注册"""
    try:
        from cron.jobs import _current_cron_store
        store = _current_cron_store()
        jobs_file = store.jobs_file
        import json
        if os.path.exists(jobs_file):
            with open(jobs_file, encoding="utf-8") as f:
                data = json.load(f)
            for job in data:
                if job.get("name") == job_name:
                    return True
    except Exception:
        pass
    return False


def register_coco_cron_jobs(chat_id: str) -> dict:
    """注册 Coco 定时任务到指定飞书会话（仅一次）

    Args:
        chat_id: 飞书会话 ID

    Returns:
        dict: {"registered": [job names], "skipped": [job names]}
    """
    result = {"registered": [], "skipped": []}
    marker = os.path.expanduser(_MARKER)
    if os.path.exists(marker):
        # 已注册过，检查是否缺失任务（补注册）
        pass

    if not _cron_store_ready():
        logger.warning("[Coco] cron store not ready, skip cron registration")
        return result

    for job_name, schedule, name, prompt in _CRON_JOBS:
        if _job_exists(name):
            result["skipped"].append(name)
            continue
        try:
            from cron.jobs import create_job
            create_job(
                prompt=prompt,
                schedule=schedule,
                name=name,
                deliver=f"feishu:{chat_id}",
                enabled_toolsets=["real_estate"],
            )
            result["registered"].append(name)
            logger.info("[Coco] cron job registered: %s -> %s", name, chat_id)
        except Exception as e:
            logger.warning("[Coco] cron job %s registration failed: %s", name, e)
            result["skipped"].append(f"{name}(error)")

    # 写标记（即使部分失败也写，避免每次对话重试；缺失任务下次会补注册）
    try:
        os.makedirs(os.path.dirname(marker), exist_ok=True)
        with open(marker, "w", encoding="utf-8") as f:
            f.write("1")
    except Exception:
        pass

    return result
