# -*- coding: utf-8 -*-
"""记忆质量审计（只读）：按 docs/memory-writing-rules.md 的规则检查现有条目。

检查项：
1. 关键词数量（8–13 个为佳）
2. 关键词里是否含项目名（规则说不要用项目名当关键词）
3. 关键词是否全是泛词（太短、太通用）
4. topic 是否缺少时间信息
5. topic 是否超过 300 字
6. 一条记忆里是否写了多件事（另外/顺便/还有一个）
7. 关键词为空

输出按严重度分组，只读，不改任何数据。
"""
import json
import os
import re

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_here = os.path.dirname(os.path.abspath(__file__))
for _up in range(1, 5):
    _pc = os.path.join(_here, *([".."] * _up), "py-core")
    if os.path.isdir(_pc):
        sys.path.insert(0, _pc)
        break
import sys

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from mem_db import DB, fetch  # 契约层统一（支持 DSH_MEMORY_DB 覆盖）
TIERS = ["soul", "user", "project", "fact", "lesson", "topic", "rules"]
PROJECT_NAMES = {"dsh", "全局"}          # 不该出现在关键词里的项目名
GENERIC_WORDS = {
    # 原有：任何一条记忆都可能出现的抽象词
    "问题", "记忆", "事情", "东西", "内容", "信息", "情况", "时候", "一个", "这个", "那个",
    # 2026-11-23 扩：实测的噪音源。
    # 这些词本身没错，但**当关键词等于没写**——任何提到它们的对话都会命中这条记忆，
    # 于是自动注入被它们占满（今天实测：讲 VMT 时被「插件」「文件」类词拖出无关记忆）。
    # 判据：**这个词能区分"这条"和"别的记忆"吗？** 不能就是泛词。
    "插件", "文件", "配置", "安装", "工具", "脚本", "方法", "路径", "版本", "升级",
    "远程", "本地", "命令", "代码", "文档", "测试", "修复", "检查", "处理", "设置",
}
TIME_PAT = re.compile(r"\d{4}-\d{1,2}|\d{1,2}\s*月|\d{1,2}\s*日|今天|昨天|昨晚|今早|刚才|上个月|昨晚|凌晨|上午|下午|晚上|周末")
MULTI_TOPIC_PAT = re.compile(r"另外|顺便|还有一个|再者|补充一点")
# 2026-11-19：引号内容常是「引用用户原话」，不能当正文判
# （实测误报：「另外两个的具体理由是什么？」被当成「写了多件事」）
QUOTED_PAT = re.compile(r'「[^」]{1,200}」|『[^』]{1,200}』|“[^”]{1,200}”')

serious = []   # 必须修
minor = []     # 建议修


def load_keywords(raw):
    if not raw:
        return []
    try:
        v = json.loads(raw)
        if isinstance(v, list):
            return [str(x) for x in v]
    except Exception:
        pass
    return [x for x in str(raw).replace("/", ",").split(",") if x.strip()]


def audit(tier, iid, title, content, keywords_raw, importance, status):
    if status == "archived":   # 已归档=作废，不该再报
        return [], [], []
    name = iid[:12]
    kws = load_keywords(keywords_raw)
    content = content or ""
    title = title or ""

    # 1 关键词为空
    if not kws:
        serious.append("%s %s：关键词为空" % (tier, name))
        return

    # 2 数量
    if len(kws) < 8:
        minor.append("%s %s：关键词只有 %d 个（建议 8–13）" % (tier, name, len(kws)))
    elif len(kws) > 13:
        minor.append("%s %s：关键词 %d 个（建议 8–13）" % (tier, name, len(kws)))

    # 3 项目名混进关键词
    bad_proj = [k for k in kws if k.strip().lower() in PROJECT_NAMES]
    if bad_proj:
        serious.append("%s %s：关键词含项目名 %s" % (tier, name, bad_proj))

    # 4 泛词过多
    generic = [k for k in kws if k.strip() in GENERIC_WORDS or len(k.strip()) <= 1]
    if len(generic) >= 3:
        minor.append("%s %s：泛词过多 %s" % (tier, name, generic[:4]))

    # 5 topic 缺时间
    if tier == "topic":
        if not TIME_PAT.search(content):
            minor.append("%s %s：topic 未写具体时间" % (tier, name))
        if len(content) > 300:
            minor.append("%s %s：topic 超 300 字（%d）" % (tier, name, len(content)))

    # 6 一条多事
    # 2026-11-19 改：去掉引号内容再判（引用用户原话不是「写了多件事」）
    body_nq = QUOTED_PAT.sub("", content or "")
    m_multi = MULTI_TOPIC_PAT.search(body_nq)
    if m_multi:
        _st = max(0, m_multi.start() - 22)
        _en = min(len(body_nq), m_multi.end() + 22)
        _ctx = body_nq[_st:_en].replace(chr(10), " ")
        minor.append("%s %s：正文含「%s」可能写了多件事 → …%s…"
                     % (tier, name, m_multi.group(0), _ctx))

    # 7 fact 过长
    body = re.sub(r"^\[[^\]]{1,40}\]\s*", "", content)  # 来源标记不算正文长度
    if tier == "fact" and len(body) > 60 * 3:   # 放宽：允许 180 字内
        # 2026-11-19 改：不只说"偏长"，给出超了多少 + 该怎么办
        over = len(body) - 180
        hint = ("可删细节" if over <= 40 else "建议拆成两条 fact 或降为 lesson")
        minor.append("%s %s：fact 偏长（%d 字，超 %d 字）→ %s"
                     % (tier, name, len(body), over, hint))


total = 0
for t in TIERS:
    try:
        rows = fetch(t, ["id", "title", "content", "keywords", "importance", "status"])
    except Exception:
        import traceback, os as _os, sys as _sys
        try:
            from mem_db import report_exception as _rep_exc
            _rep_exc(_os.path.basename(__file__), traceback.format_exc()[-400:])
        except Exception:
            pass
        continue
    for iid, title, content, kws, imp, st in rows:
        total += 1
        audit(t, iid, title, content, kws, imp, st)

print("=== 审计范围：%d 条 active+全部状态 ===" % total)
print()
print("=== 必须修（%d）===" % len(serious))
for s in serious:
    print("  ! " + s)
print()
print("=== 建议修（%d）===" % len(minor))
# 2026-11-24：加 `--all` 看全部。
# 默认只显示前 40 条（不让正常使用被 74 行淹没），但**测试/排查时需要看全**——
# 之前没有这个开关，造了已知该报的数据却"看不见"，差点误判成漏报。
_show_all = "--all" in sys.argv or "-a" in sys.argv
for s in (minor if _show_all else minor[:40]):
    print("  - " + s)
if len(minor) > 40 and not _show_all:
    print("  …… 还有 %d 条（要全看加 --all）" % (len(minor) - 40))
