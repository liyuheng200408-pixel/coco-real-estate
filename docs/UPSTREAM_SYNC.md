# Coco 同步官方上游（UPSTREAM SYNC）作业手册

> 适用场景：官方 Hermes 发布新版本，需要把 Coco 的底座同步过去。
> 这是一份**照着走**的清单。每一步都有对应的检查项，因为它对应着过去真实踩过的坑。

---

## 零、动手前的三个前提

- [ ] **仓库历史保持线性**（经纪人的更新命令用的是 `git pull --ff-only`）。
      任何 rebase / 强推都会让所有老实例更新失败。**这是铁律。**
- [ ] **Gitee 仓库未超配额**：免费版单仓库上限 **500MB**，超了平台会**锁死推拉**。
      同步前先记录当前体积（见第五步），超过 350MB 就要开始准备预案。
- [ ] **不在生产实例上直接试**。先在本地仓库和测试实例上走完流程，再让经纪人更新。

---

## 一、同步流程（七步）

### 第 1 步｜记录基线
```bash
cd ~/hermes-agent   # 或本地分析仓库
git log --oneline -1                 # 当前提交
cat VERSION                          # Coco 版本
du -sh .git                          # 仓库体积（记下来，用于对比）
python3 scripts/check_coco_hooks.py  # 同步前的挂钩点状态（应全 PASS）
```

### 第 2 步｜拉取官方新版本快照并替换官方层
```bash
bash scripts/sync_upstream.sh v2026.9.14   # 换成实际的官方版本 tag
```
脚本会：拉官方快照 → 替换官方层文件 → **保留 Coco 自有文件** → 打印
「需要人工处理的改动点」。

### 第 3 步｜逐处重新应用 Coco 的改动
按 `patches/README.md` 的语义说明，在新版代码里重新实现 **7 处改动**：

| 编号 | 文件 | 优先确认 |
|---|---|---|
| 01 | `toolsets.py` | 定义 + 被 hermes-feishu 引用，两个条件都要 |
| 02 | `agent/prompt_builder.py` | 身份常量名是否变 |
| 03 | `agent/system_prompt.py` | 是否仍拼在"稳定片段"（会破坏 prompt 缓存的话要调） |
| 04 | `agent/agent_init.py` | CLI 初始化入口位置 |
| 05 | `hermes_cli/config_defaults.py` | 压缩阈值 0.8 / protect_last_n 40 |
| 06 | `plugins/platforms/feishu/adapter.py` | 欢迎语 + 密钥提醒 + 注册定时任务，三件都要 |
| 07 | `gateway/run.py` | 开场白 + 关闭官方 profile-build 引导 |

### 第 4 步｜自检 + 处理部署体系
```bash
python3 scripts/check_coco_hooks.py    # 24 项应全 PASS
```
再检查官方是否改动了这些**我们自建**的东西所依赖的机制：
- [ ] `install.sh` 的网关环境补丁（`setup_gateway_env_patch`）：官方若改了
      `hermes gateway install` 的机制，补丁可能失效 → **幽灵库事故会重现**
      （症状：机器人回复"登记成功"，库里却没有数据）
- [ ] `scripts/update.sh` 的 7 步流程是否仍然适用
- [ ] `scripts/migrate.py` 的迁移执行器与官方数据库结构是否冲突

### 第 5 步｜三层验收（缺一不可）

| 关卡 | 命令 | 通过标准 | 谁跑 |
|---|---|---|---|
| ① 部署体检 | `python3 scripts/healthcheck.py` | 11 项无 FAIL | 我 |
| ② 工具冒烟 | `python3 scripts/smoke_test_real_estate.py` | 67 个工具逐个真实调用，无 EXC | 我 |
| ③ 单元测试 | `.venv-dev/bin/python -m pytest tests/real_estate/ -q` | 全绿 | 我 |
| ④ **飞书全量实测** | 按 `docs/TESTING_FEISHU_FULL.md` 发 51 条指令 | 逐条对照，关键链路查库确认 | **老板** |

> ⚠️ **冒烟 ≠ 没问题**：冒烟只证明"工具本身能跑"，证明不了"模型会在该用的时候调用它"。
> 第 ④ 关必须真人在飞书里走一遍，且**每测一项都查数据库确认落库**，不能只看回复文本。

### 第 6 步｜灰度发布
1. 先在你自己的服务器（测试实例）跑完整更新链路：
   `cd ~/hermes-agent && source venv/bin/activate && git pull && bash scripts/update.sh`
2. 更新后确认：
   - [ ] 飞书里 Coco 自我介绍正确（不是官方默认文案）
   - [ ] 房产工具可用（例如"看下房源统计"）
   - [ ] **网关进程环境里有 DATABASE_URL**（防幽灵库）：
     `systemctl show -p MainPID --value hermes-gateway | xargs -I{} sudo cat /proc/{}/environ | tr '\0' '\n' | grep DATABASE_URL`
3. 确认无误后，再通知其他经纪人更新。

### 第 7 步｜发版与记账
```bash
# 更新 VERSION、打标签、推送双仓库
bash scripts/push_all.sh
```
每次同步都记一笔（写在提交信息或本文件末尾的记录区）：
本次同步到哪个官方版本 · 改了哪些文件 · 体积涨到多少 · 遇到什么问题 · 怎么解决的。

---

## 二、每次必查清单（对应过去的真实事故）

- [ ] **配置版本号**：官方 `_config_version` 变了没？（对照
      `hermes_cli/config_defaults.py` 的 `"_config_version"` 值）
      变了就确认 `scripts/update.sh` 里有跑 `hermes config migrate`。
      （已知：我们 33 → 官方 0.21.3 是 44）
- [ ] **Python 版本要求**：官方 `pyproject.toml` 的 `requires-python` 变了没？
      （已知 0.21.3 仍是 `>=3.11,<3.14`，与我们一致）
- [ ] **新增依赖**：官方新增的依赖要确保 `pip install -e .` 能装上（走 pyproject）
- [ ] **飞书适配器改动**：官方对 adapter 的改动是否影响我们的挂钩点（第 06 项）
- [ ] **网关环境补丁**：`setup_gateway_env_patch` 是否仍生效（防幽灵库）
- [ ] **身份文案一致性**：改身份时，7 处副本都要同步（adapter 欢迎语、gateway
      开场白、prompt_builder、房产提示词、SOUL.md、技能文件、README）
- [ ] **仓库体积**：记录数值；> 350MB 时启动体积预案
- [ ] **标签格式**：Coco 用语义化 `vX.Y.Z`，官方用日期式 `vYYYY.M.D`；
      继承来的脚本若报"找不到标签"，先看格式匹配（历史坑）

---

## 三、体积预案（Gitee 500MB 天花板）

实测：一次跨版本同步让仓库 **+80MB**（首次引入大批新文件）；同一批文件再同步只 +20MB。
现状：约 70MB。推算：约 1.5-2 年用满 500MB（官方约 6 周一个大版本）。

按顺序触发：
1. **> 350MB**：记录并观察；跑 `git gc --aggressive` 看看能回收多少
2. **> 400MB**：评估切 GitHub 为主源（容量 10GB，但国内访问慢）或升 Gitee 配额
3. **接近 500MB**：一次性重写历史瘦身 —— ⚠️ 会破坏老实例的快进更新，
   **必须提前一个版本铺垫 + 公告经纪人执行一次性重置命令**，属最后手段

---

## 四、回滚手段

| 情况 | 怎么回滚 |
|---|---|
| 代码有问题 | 更新前打的 git tag / 上一个提交：`git reset --hard <tag>` 后推送 |
| 数据有问题 | `scripts/backup_db.py` 在更新前自动备份，按 `docs/BACKUP_MIGRATION.md` 恢复 |
| 仓库不可用 | Gitee / GitHub 双源，一个挂了切另一个（install.sh 会自动探测） |

---

## 五、同步记录

> 每次同步后在此追加一行，便于追踪"我们跟到哪个版本了"。

| 日期 | Coco 版本 | 同步到官方版本 | 体积 | 备注 |
|---|---|---|---|---|
| （待第一次同步） | | | | |

---

## 附：为什么不能直接 `git merge upstream`

Coco 仓库是"复制官方文件后重新初始化 git"的形态：一次性导入了 8,598 个文件，
官方几万个提交的历史被压平成一个提交。**两个仓库没有共同祖先**，
`git pull upstream` 会直接报 unrelated histories；强行加
`--allow-unrelated-histories` 等于把 8,600 个文件全当冲突处理，比重做一遍还慢。

所以采用**快照式同步**（本手册的流程）：把官方新版文件整体替换进来 + 重新应用
我们的 7 处改动。已实测：这种方式下，老实例的 `git pull --ff-only` 能正常快进，
文件替换正确，Coco 自有文件与未跟踪的运行时文件都不会丢。
