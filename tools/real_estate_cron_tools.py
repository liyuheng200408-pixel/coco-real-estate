"""
Coco 房产工具 - 定时任务自助开关（2026-08-12 加）
经纪人一句话开启/关闭定时提醒（早报/午间/逾期），无需操作服务器。
"""
import json
from tools.registry import registry


def _get_chat_id(task_id: str = None, **kwargs) -> str:
    """获取飞书会话 ID：框架注入 > session_id 提取 > task_id > 环境变量 COCO_CHAT_ID

    2026-08-13 修复：原 handler 丢弃框架注入的 session_id，且 session_id 是复合格式
    （agent:main:feishu:dm:oc_xxx），自动获取路径全部失效，只能手动配 COCO_CHAT_ID。
    现支持从 session_id 各段中提取 oc_/ou_ 开头的会话 ID，全自动，无需再配环境变量。
    """
    # 1. 框架显式注入的会话 ID
    for key in ('chat_id', 'channel_id', 'conversation_id'):
        v = kwargs.get(key)
        if v:
            return str(v)
    # 2. session_id 复合格式提取（agent:main:feishu:dm:oc_xxx → oc_xxx；
    #    群聊含 user_id/thread_id 段时也能定位到 oc_/ou_ 段）
    sid = kwargs.get('session_id')
    if sid:
        for seg in str(sid).split(':'):
            if seg.startswith(('oc_', 'ou_')):
                return seg
    # 3. task_id（注册任务时由调用方传入）
    if task_id and str(task_id).startswith(('oc_', 'ou_')):
        return task_id
    # 4. 环境变量兜底（.env.db 配置 COCO_CHAT_ID=oc_xxx）
    import os
    return os.getenv('COCO_CHAT_ID', '')


def enable_cron(task_id: str = None, **kwargs) -> str:
    """开启定时任务（每日早报/午间检查/逾期提醒）"""
    from agent.coco_cron import enable_coco_cron_jobs
    chat_id = _get_chat_id(task_id, **kwargs)
    if not chat_id:
        return json.dumps({
            "success": False,
            "error": "无法确定推送会话，请在 .env.db 配置 COCO_CHAT_ID=oc_你的飞书会话ID 后重试",
        }, ensure_ascii=False)
    result = enable_coco_cron_jobs(chat_id)
    registered = result.get('registered', [])
    skipped = result.get('skipped', [])
    if result.get('error'):
        return json.dumps({"success": False, "error": result['error']}, ensure_ascii=False)
    if registered:
        return json.dumps({
            "success": True,
            "enabled": registered,
            "message": f"定时任务已开启：{'、'.join(registered)}（早报 09:00 / 午间 13:00 / 逾期每 30 分钟）",
        }, ensure_ascii=False)
    if skipped:
        # 区分"已存在跳过"与"注册失败"（2026-08-13 加：注册失败必须如实报错，
        # 不能报"已经在运行中"误导——真实案例：本地缺 croniter 时全部注册失败仍报成功）
        errors = [s for s in skipped if s.endswith('(error)')]
        if errors:
            return json.dumps({
                "success": False,
                "error": f"定时任务注册失败：{'、'.join(errors)}，请稍后重试或检查服务日志",
            }, ensure_ascii=False)
        return json.dumps({
            "success": True,
            "enabled": [],
            "message": "定时任务已经在运行中，无需重复开启",
        }, ensure_ascii=False)
    return json.dumps({"success": False, "error": "没有可开启的定时任务"}, ensure_ascii=False)


def disable_cron(task_id: str = None) -> str:
    """关闭定时任务"""
    from agent.coco_cron import disable_coco_cron_jobs
    result = disable_coco_cron_jobs()
    removed = result.get('removed', [])
    if result.get('error'):
        return json.dumps({"success": False, "error": result['error']}, ensure_ascii=False)
    if removed:
        return json.dumps({
            "success": True,
            "disabled": removed,
            "message": f"定时任务已关闭：{'、'.join(removed)}",
        }, ensure_ascii=False)
    return json.dumps({
        "success": True,
        "disabled": [],
        "message": "当前没有运行中的定时任务",
    }, ensure_ascii=False)


registry.register(
    name="enable_cron",
    toolset="real_estate",
    schema={"name": "enable_cron", "description": "开启定时任务（每日早报 09:00 / 午间检查 13:00 / 逾期提醒每 30 分钟），经纪人要求开启定时提醒时调用", "parameters": {
        "type": "object",
        "properties": {},
    }},
    handler=lambda args, **kw: enable_cron(
        **{k: v for k, v in {
            'task_id': kw.get('task_id'),
            'session_id': kw.get('session_id'),
            'chat_id': kw.get('chat_id'),
            'channel_id': kw.get('channel_id'),
            'conversation_id': kw.get('conversation_id'),
        }.items() if v is not None and k not in args},
        **args,
    ),
)

registry.register(
    name="disable_cron",
    toolset="real_estate",
    schema={"name": "disable_cron", "description": "关闭定时任务（早报/午间/逾期提醒全部停止），经纪人要求关闭定时提醒时调用", "parameters": {
        "type": "object",
        "properties": {},
    }},
    handler=lambda args, **kw: disable_cron(**args),
)
