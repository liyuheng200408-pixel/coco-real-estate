"""定时任务的提示词同步（2026-09-23 加，方案 1）

问题：定时任务的提示词是**注册时写进任务记录**的（cron/jobs.json），代码里改文案不会
覆盖已经存在的任务——三条注册路径遇到同名任务一律跳过，于是"改了代码，早报还按旧口径报"。
真实教训：早报指令原文只点"S/A级客户状态"，改成四级全列后，经纪人机器上那条老任务
仍是旧文案，早报继续漏 B 级。

修法：`_refresh_coco_job_prompts()` 在注册/开启时把名字与 `_AVAILABLE_JOBS` 一致、
且提示词不一致的任务，用官方 `update_job` 对齐到代码最新文案（只动 coco_ 三个任务）。
"""
from __future__ import annotations

import cron.jobs as cron_jobs

import agent.coco_cron as cc


def _daily():
    return next(item for item in cc._AVAILABLE_JOBS if item[2] == "coco_daily_report")


def _jobs(*pairs):
    return [{"id": f"id-{name}", "name": name, "prompt": prompt} for name, prompt in pairs]


class TestPromptRefresh:
    def test_stale_prompt_is_refreshed(self, monkeypatch):
        item = _daily()
        calls = []
        monkeypatch.setattr(cron_jobs, "list_jobs", lambda include_disabled=False: _jobs((item[2], "旧文案：只点 S/A 级")))
        monkeypatch.setattr(cron_jobs, "update_job", lambda jid, updates: calls.append((jid, updates)) or {"id": jid})

        assert cc._refresh_coco_job_prompts() == [item[2]]
        assert calls == [(f"id-{item[2]}", {"prompt": item[3]})]

    def test_matching_prompt_is_left_alone(self, monkeypatch):
        item = _daily()
        calls = []
        monkeypatch.setattr(cron_jobs, "list_jobs", lambda include_disabled=False: _jobs((item[2], item[3])))
        monkeypatch.setattr(cron_jobs, "update_job", lambda jid, updates: calls.append(jid))

        assert cc._refresh_coco_job_prompts() == []
        assert calls == []

    def test_only_coco_jobs_are_touched(self, monkeypatch):
        item = _daily()
        calls = []
        monkeypatch.setattr(
            cron_jobs, "list_jobs",
            lambda include_disabled=False: _jobs(("my_own_job", "经纪人自己建的任务"), (item[2], "旧文案")),
        )
        monkeypatch.setattr(cron_jobs, "update_job", lambda jid, updates: calls.append(jid) or {"id": jid})

        assert cc._refresh_coco_job_prompts() == [item[2]]
        assert calls == [f"id-{item[2]}"]

    def test_absent_jobs_are_not_touched(self, monkeypatch):
        calls = []
        monkeypatch.setattr(cron_jobs, "list_jobs", lambda include_disabled=False: [])
        monkeypatch.setattr(cron_jobs, "update_job", lambda jid, updates: calls.append(jid))

        assert cc._refresh_coco_job_prompts() == []
        assert calls == []

    def test_script_jobs_are_skipped(self, monkeypatch):
        """脚本型任务（dict 提示词）不属于提示词任务，不能刷"""
        calls = []
        monkeypatch.setattr(cc, "_AVAILABLE_JOBS", (("script_job", "0 3 * * *", "script_job", {"script": "x.sh"}),))
        monkeypatch.setattr(cron_jobs, "list_jobs", lambda include_disabled=False: _jobs(("script_job", "anything")))
        monkeypatch.setattr(cron_jobs, "update_job", lambda jid, updates: calls.append(jid))

        assert cc._refresh_coco_job_prompts() == []
        assert calls == []

    def test_store_failure_does_not_raise(self, monkeypatch):
        def boom(*_a, **_k):
            raise RuntimeError("cron store 挂了")

        monkeypatch.setattr(cron_jobs, "list_jobs", boom)
        assert cc._refresh_coco_job_prompts() == []

    def test_vanished_job_is_reported_not_raised(self, monkeypatch):
        item = _daily()
        monkeypatch.setattr(cron_jobs, "list_jobs", lambda include_disabled=False: _jobs((item[2], "旧文案")))
        monkeypatch.setattr(cron_jobs, "update_job", lambda jid, updates: None)

        assert cc._refresh_coco_job_prompts() == []


class TestRegistrationWiring:
    def test_register_path_refreshes_and_reports(self, monkeypatch, tmp_path):
        monkeypatch.setenv("COCO_ENABLE_CRON", "1")
        marker = tmp_path / ".coco_cron_registered"
        marker.write_text("1", encoding="utf-8")
        monkeypatch.setattr(cc, "_marker_path", lambda: str(marker))
        monkeypatch.setattr(cc, "_cron_store_ready", lambda: True)
        monkeypatch.setattr(cc, "_job_exists", lambda name: True)
        monkeypatch.setattr(
            cron_jobs, "list_jobs",
            lambda include_disabled=False: _jobs(*[(item[2], "旧文案") for item in cc._AVAILABLE_JOBS]),
        )
        monkeypatch.setattr(cron_jobs, "update_job", lambda jid, updates: {"id": jid})

        result = cc.register_coco_cron_jobs("oc_test")

        assert set(result.get("refreshed") or []) == {item[2] for item in cc._AVAILABLE_JOBS}
        assert result["registered"] == []

    def test_refresh_runs_even_when_registration_is_off(self, monkeypatch):
        """任务已存在（例如经纪人是靠工具开启的）时，环境开关没开也要对齐文案"""
        monkeypatch.delenv("COCO_ENABLE_CRON", raising=False)
        monkeypatch.setattr(
            cron_jobs, "list_jobs",
            lambda include_disabled=False: _jobs(*[(item[2], "旧文案") for item in cc._AVAILABLE_JOBS]),
        )
        monkeypatch.setattr(cron_jobs, "update_job", lambda jid, updates: {"id": jid})

        result = cc.register_coco_cron_jobs("oc_test")

        assert set(result.get("refreshed") or []) == {item[2] for item in cc._AVAILABLE_JOBS}
        assert result["registered"] == []

    def test_enable_path_refreshes_too(self, monkeypatch):
        monkeypatch.setattr(cc, "_cron_store_ready", lambda: True)
        monkeypatch.setattr(cc, "_job_exists", lambda name: True)
        monkeypatch.setattr(
            cron_jobs, "list_jobs",
            lambda include_disabled=False: _jobs(*[(item[2], "旧文案") for item in cc._AVAILABLE_JOBS]),
        )
        monkeypatch.setattr(cron_jobs, "update_job", lambda jid, updates: {"id": jid})

        result = cc.enable_coco_cron_jobs("oc_test")

        assert set(result.get("refreshed") or []) == {item[2] for item in cc._AVAILABLE_JOBS}
