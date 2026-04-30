#!/usr/bin/env python3
"""
小红书评论区获客模块

基于 xiaohongshu-mcp HTTP API + DeepSeek LLM 实现全自动评论区获客。

流程:
  [搜索]    → MCP API 搜索关键词笔记
  [评分]    → LLM 4维评分（热度40 + 互动30 + 时效20 + 质量10）
  [详情]    → 获取笔记正文和评论区上下文
  [生成评论] → LLM 根据笔记内容生成小红书风格评论
  [发送]    → MCP API 发表评论
  [记录]    → JSON 持久化已评论笔记，避免重复

使用:
  # 手动指定关键词运行
  python3 xhs_comment_acquisition.py --keyword "AI工具" --product-url "https://ai.hcrzx.com"

  # 自动模式（AI生成关键词 + 搜索 + 评论）
  python3 xhs_comment_acquisition.py --auto --product-url "https://ai.hcrzx.com" --product-name "慧辰AI分析"

  # 安全测试（不真正发送）
  python3 xhs_comment_acquisition.py --keyword "数据分析" --dry-run

  # 指定每日评论上限
  python3 xhs_comment_acquisition.py --auto --max-comments 10
"""
import argparse
import json
import logging
import os
import random
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import quote_plus

import requests

logger = logging.getLogger("xhs-comment-acquisition")

# ── 目录配置 ────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.absolute()
SKILL_DIR = SCRIPT_DIR.parent  # xhs-adb-publisher/
DATA_DIR = SKILL_DIR / "data"
CONFIG_DIR = SKILL_DIR / "config"
TEMPLATES_DIR = SKILL_DIR / "templates"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── 常量配置 ────────────────────────────────────────

MCP_BASE_URL = os.environ.get("XHS_MCP_URL", "http://localhost:18060")
MCP_TIMEOUT = 60

# 评分权重
SCORE_WEIGHTS = {"heat": 40, "interaction": 30, "timeliness": 20, "quality": 10}

# 反爬策略
ANTI_CRAWL = {
    "active_hours": (8, 23),       # 工作时间 8:00-23:00
    "max_comments_per_day": 20,     # 每天最多评论数
    "max_comments_per_hour": 5,     # 每小时最多评论数
    "min_interval_seconds": 60,     # 最小间隔（秒）
    "base_interval_seconds": 180,   # 基础间隔（秒）
    "jitter_ratio": 0.3,            # 抖动比例 ±30%
}

COMMENT_MAX_LENGTH = 280  # 小红书评论字数上限

# ── 路径配置 ────────────────────────────────────────

HISTORY_FILE = DATA_DIR / "commented-history.json"
CONFIG_FILE = CONFIG_DIR / "keywords.json"
COMMENT_PROMPT_FILE = TEMPLATES_DIR / "comment-prompt.md"

LLM_API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-v4-flash"

# ════════════════════════════════════════════════════════
#  工具函数
# ════════════════════════════════════════════════════════

def _get_llm_key() -> str:
    """获取 DeepSeek API Key"""
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key
    try:
        cfg = os.path.expanduser("~/.openclaw/openclaw.json")
        if os.path.exists(cfg):
            with open(cfg) as f:
                env = json.load(f).get("env", {})
                if isinstance(env, dict):
                    key = env.get("DEEPSEEK_API_KEY")
                    if key:
                        return key
    except Exception:
        pass
    raise EnvironmentError("未找到 DEEPSEEK_API_KEY。请配置环境变量或 ~/.openclaw/openclaw.json")


def call_llm(system: str, user: str, temperature: float = 0.7,
             max_tokens: int = 2048) -> str:
    """调用 DeepSeek LLM"""
    api_key = _get_llm_key()
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    try:
        resp = requests.post(LLM_API_URL, headers=headers, json=payload, timeout=180)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"LLM 调用失败: {e}")
        raise


def call_llm_json(system: str, user: str, temperature: float = 0.7,
                  max_tokens: int = 2048) -> dict:
    """调用 LLM 并解析 JSON 返回"""
    content = call_llm(system, user, temperature, max_tokens)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', content, re.DOTALL)
        if m:
            return json.loads(m.group())
        raise ValueError(f"LLM 返回非 JSON: {content[:200]}")


def mcp_request(method: str, path: str, json_data: dict = None) -> dict:
    """调用 xiaohongshu-mcp HTTP API"""
    url = f"{MCP_BASE_URL}{path}"
    try:
        if method.upper() == "GET":
            resp = requests.get(url, timeout=MCP_TIMEOUT)
        else:
            resp = requests.post(url, json=json_data, timeout=MCP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(f"MCP API 错误: {data.get('error', '未知错误')}")
        return data
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"无法连接到 MCP 服务器 ({MCP_BASE_URL})。请确保 xiaohongshu-mcp 正在运行。"
        )


def jitter_delay(sec: float, ratio: float = 0.3) -> float:
    """带随机抖动的等待"""
    actual = sec * (1 + random.uniform(-ratio, ratio))
    time.sleep(max(actual, 0.5))
    return actual


# ════════════════════════════════════════════════════════
#  历史记录管理
# ════════════════════════════════════════════════════════

def load_history() -> List[dict]:
    """加载已评论笔记历史"""
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception):
            return []
    return []


def save_history(history: List[dict]):
    """保存评论历史"""
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def is_already_commented(feed_id: str, history: List[dict]) -> bool:
    """检查是否已经评论过"""
    return any(h.get("feed_id") == feed_id for h in history)


def add_to_history(feed_id: str, keyword: str, comment: str,
                   score: float, note_title: str, note_author: str):
    """记录一条评论历史"""
    history = load_history()
    history.append({
        "feed_id": feed_id,
        "keyword": keyword,
        "comment": comment,
        "score": score,
        "note_title": note_title,
        "note_author": note_author,
        "commented_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
    })
    # 保留最近500条
    if len(history) > 500:
        history = history[-500:]
    save_history(history)


# ════════════════════════════════════════════════════════
#  关键词管理
# ════════════════════════════════════════════════════════

def load_keywords() -> List[str]:
    """从配置文件加载种子关键词"""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                cfg = json.load(f)
                return cfg.get("seed_keywords", [])
        except Exception:
            return []
    return []


def ai_generate_keywords(product_url: str, product_name: str,
                         count: int = 10) -> List[str]:
    """AI 动态生成关键词"""
    system = (
        "你是一个小红书运营专家，擅长为产品找到用户真正在搜索的关键词。\n"
        "请基于产品信息，生成适合在小红书搜索潜在客户的关键词。\n"
        "要求：\n"
        "1. 关键词要是小红书用户真实搜索的词\n"
        "2. 涵盖不同角度：痛点词、解决方案词、场景词\n"
        "3. 不要包含品牌名，要像真实用户搜索词\n"
        "4. 输出 JSON 数组格式\n"
    )
    user = (
        f"产品名称: {product_name or '未知'}\n"
        f"产品链接: {product_url or '未知'}\n\n"
        f"请生成 {count} 个小红书获客关键词，输出 JSON 数组:\n"
        f'{{"keywords": ["关键词1", "关键词2", ...]}}'
    )
    try:
        result = call_llm_json(system, user, temperature=0.8, max_tokens=1024)
        keywords = result.get("keywords", [])
        if keywords and len(keywords) >= 3:
            logger.info(f"AI 生成 {len(keywords)} 个关键词: {keywords[:5]}...")
            return keywords
    except Exception as e:
        logger.warning(f"AI 生成关键词失败: {e}")
    return []


# ════════════════════════════════════════════════════════
#  搜索 & 评分
# ════════════════════════════════════════════════════════

def search_notes(keyword: str, sort_by: str = "综合",
                 note_type: str = "不限", max_results: int = 20) -> List[dict]:
    """通过 MCP API 搜索笔记"""
    logger.info(f"搜索关键词: '{keyword}' (排序={sort_by})")

    filters = {"sort_by": sort_by, "note_type": note_type}
    raw = mcp_request("POST", "/api/v1/feeds/search", {
        "keyword": keyword,
        "filters": filters,
    })

    feeds = raw.get("data", {}).get("feeds", [])
    if not feeds:
        logger.info(f"关键词 '{keyword}' 无搜索结果")
        return []

    # 格式化返回
    results = []
    for f in feeds[:max_results]:
        nc = f.get("noteCard", {})
        user = nc.get("user", {})
        interact = nc.get("interactInfo", {})

        results.append({
            "feed_id": f.get("id"),
            "xsec_token": f.get("xsecToken"),
            "title": nc.get("displayTitle", ""),
            "author": user.get("nickname", user.get("nickName", "未知")),
            "author_id": user.get("userId", ""),
            "liked_count": _safe_int(interact.get("likedCount", "0")),
            "collected_count": _safe_int(interact.get("collectedCount", "0")),
            "comment_count": _safe_int(interact.get("commentCount", "0")),
        })

    logger.info(f"搜索到 {len(results)} 篇笔记")
    return results


def _safe_int(val) -> int:
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


def get_note_detail(feed_id: str, xsec_token: str) -> dict:
    """获取笔记详情（包括正文和评论）"""
    raw = mcp_request("POST", "/api/v1/feeds/detail", {
        "feed_id": feed_id,
        "xsec_token": xsec_token,
        "load_all_comments": False,  # 只要前几条评论做上下文
    })
    data = raw.get("data", {}).get("data", {})
    note = data.get("note", {})
    comments = data.get("comments", {}).get("list", [])

    # 取前3条评论做上下文
    top_comments = []
    for c in comments[:3]:
        ui = c.get("userInfo", {})
        top_comments.append({
            "user": ui.get("nickname", "匿名"),
            "content": c.get("content", ""),
        })

    return {
        "title": note.get("title", ""),
        "desc": note.get("desc", ""),
        "author": note.get("user", {}).get("nickname", "未知"),
        "time": note.get("time", 0),
        "top_comments": top_comments,
        "liked_count": _safe_int(note.get("interactInfo", {}).get("likedCount", "0")),
        "collected_count": _safe_int(note.get("interactInfo", {}).get("collectedCount", "0")),
        "comment_count": _safe_int(note.get("interactInfo", {}).get("commentCount", "0")),
    }


def ai_score_note(note: dict, detail: dict) -> Tuple[float, str]:
    """AI 4维评分笔记"""
    liked = detail.get("liked_count", note.get("liked_count", 0))
    collected = detail.get("collected_count", note.get("collected_count", 0))
    commented = detail.get("comment_count", note.get("comment_count", 0))

    # 1. 热度评分 (40分) — 总互动量归一化
    total_interact = liked + collected * 2 + commented * 3  # 收藏>点赞>评论权重
    heat_score = min(40, total_interact / 50 * 40)

    # 2. 互动评分 (30分) — 评论/点赞比，越高说明讨论度越高
    if liked > 0:
        interact_rate = commented / liked
        interaction_score = min(30, interact_rate * 100 * 30)
    else:
        interaction_score = 0

    # 3. 时效评分 (20分) — 发布时间越近越高
    now_ts = datetime.now().timestamp()
    delta_days = (now_ts - detail.get("time", 0)) / 86400 if detail.get("time") else 30
    if delta_days <= 1:
        timeliness_score = 20
    elif delta_days <= 7:
        timeliness_score = 15
    elif delta_days <= 30:
        timeliness_score = 10
    elif delta_days <= 90:
        timeliness_score = 5
    else:
        timeliness_score = 2

    # 4. 质量评分 (10分) — AI 评估
    quality_score = ai_quality_score(
        detail.get("title", ""), detail.get("desc", ""),
        total_interact, commented
    )

    total_score = heat_score + interaction_score + timeliness_score + quality_score
    return round(total_score, 1), (
        f"热度={heat_score:.1f}/40 + "
        f"互动={interaction_score:.1f}/30 + "
        f"时效={timeliness_score:.1f}/20 + "
        f"质量={quality_score:.1f}/10"
    )


def ai_quality_score(title: str, desc: str, total_interact: int,
                     comment_count: int) -> float:
    """AI 评估内容质量（0-10分）"""
    system = (
        "你是一个小红书内容质量评估专家。请根据标题和正文，评估笔记的内容质量。\n"
        "评分维度:\n"
        "  - 标题吸引力（0-3分）：是否吸引点击\n"
        "  - 内容价值（0-4分）：是否有干货/情绪价值/实用性\n"
        "  - 互动潜力（0-3分）：是否容易引发讨论\n"
        "输出: 仅返回一个数字（0-10），不要有其他文字。"
    )
    user = (
        f"标题: {title[:50]}\n"
        f"正文: {desc[:200]}\n"
        f"总互动量: {total_interact}\n"
        f"评论数: {comment_count}\n\n"
        f"请给出内容质量评分（0-10分，一位小数）:"
    )
    try:
        content = call_llm(system, user, temperature=0.3, max_tokens=32)
        score = float(content.strip())
        return max(0, min(10, round(score, 1)))
    except Exception:
        # 降级：用互动量估算
        if total_interact > 1000:
            return 8.0
        elif total_interact > 500:
            return 6.0
        elif total_interact > 100:
            return 4.0
        elif total_interact > 50:
            return 3.0
        return 2.0


# ════════════════════════════════════════════════════════
#  AI 评论生成
# ════════════════════════════════════════════════════════

def load_comment_prompt_template() -> str:
    """加载评论提示词模板"""
    if COMMENT_PROMPT_FILE.exists():
        with open(COMMENT_PROMPT_FILE, encoding="utf-8") as f:
            return f.read()
    return ""


def ai_generate_comment(note_title: str, note_desc: str,
                        top_comments: List[dict],
                        product_info: str = "") -> dict:
    """AI 生成小红书风格评论"""
    system = load_comment_prompt_template()
    if not system:
        system = (
            "你是一位小红书资深用户，擅长在笔记下写自然、真诚的评论。\n"
            "你的评论要有价值、有共鸣、能引发对话。\n"
            "输出 JSON 格式: {\"style\": \"风格\", \"comment\": \"评论内容\", \"reason\": \"理由\"}\n"
            "评论长度30-100字，不超过280字。"
        )

    comments_context = "\n".join(
        [f"  - {c['user']}: {c['content'][:80]}" for c in top_comments[:3]]
    )

    user = (
        f"笔记标题: {note_title}\n"
        f"笔记正文: {note_desc[:500]}\n"
        f"已有评论:\n{comments_context}\n\n"
    )
    if product_info:
        user += (
            f"背景信息（不要直接提产品，如有合适时机自然融入）:\n"
            f"{product_info}\n\n"
        )
    user += "请根据以上笔记内容，生成一条自然、真诚的评论（JSON格式）:"

    result = call_llm_json(system, user, temperature=0.85, max_tokens=1024)
    comment = result.get("comment", "").strip()

    # 裁剪评论长度
    if len(comment) > COMMENT_MAX_LENGTH:
        # 尝试在最后一个标点处截断
        truncated = comment[:COMMENT_MAX_LENGTH - 3]
        last_punct = max(
            truncated.rfind("。"), truncated.rfind("！"),
            truncated.rfind("？"), truncated.rfind("~"),
            truncated.rfind("."), truncated.rfind("!"),
            truncated.rfind("?"),
        )
        if last_punct > COMMENT_MAX_LENGTH // 2:
            comment = truncated[:last_punct + 1]
        else:
            comment = truncated + "..."

    return {
        "style": result.get("style", "共鸣型"),
        "comment": comment,
        "reason": result.get("reason", ""),
    }


# ════════════════════════════════════════════════════════
#  评论发送
# ════════════════════════════════════════════════════════

def post_comment_mcp(feed_id: str, xsec_token: str, content: str) -> bool:
    """通过 MCP API 发表评论"""
    logger.info(f"发表评论到 {feed_id}: '{content[:30]}...'")
    try:
        raw = mcp_request("POST", "/api/v1/feeds/comment", {
            "feed_id": feed_id,
            "xsec_token": xsec_token,
            "content": content,
        })
        success = raw.get("data", {}).get("success", False)
        if success:
            logger.info(f"✅ 评论成功")
        else:
            logger.warning(f"❌ 评论失败: {raw.get('data', {}).get('message', '未知')}")
        return success
    except Exception as e:
        logger.error(f"评论发送异常: {e}")
        return False


# ════════════════════════════════════════════════════════
#  反爬 & 节奏控制
# ════════════════════════════════════════════════════════

def check_rate_limit(history: List[dict]) -> Tuple[bool, str]:
    """检查是否超过频率限制"""
    now = datetime.now(timezone(timedelta(hours=8)))
    today = now.strftime("%Y-%m-%d")
    current_hour = now.hour

    # 检查活跃时段
    active_start, active_end = ANTI_CRAWL["active_hours"]
    if not (active_start <= current_hour < active_end):
        return False, f"不在活跃时段（{active_start}:00-{active_end}:00）"

    # 每日评论数
    today_count = sum(
        1 for h in history
        if h.get("commented_at", "").startswith(today)
    )
    if today_count >= ANTI_CRAWL["max_comments_per_day"]:
        return False, f"已达每日上限（{ANTI_CRAWL['max_comments_per_day']}条）"

    # 每小时评论数
    hour_key = now.strftime("%Y-%m-%dT%H")
    hour_count = sum(
        1 for h in history
        if h.get("commented_at", "").startswith(hour_key)
    )
    if hour_count >= ANTI_CRAWL["max_comments_per_hour"]:
        return False, f"已达每小时上限（{ANTI_CRAWL['max_comments_per_hour']}条）"

    return True, "ok"


# ════════════════════════════════════════════════════════
#  主流程
# ════════════════════════════════════════════════════════

def run(keyword: str = "",
        product_url: str = "",
        product_name: str = "",
        max_comments: int = 5,
        dry_run: bool = False,
        auto_keywords: bool = False) -> dict:
    """
    评论区获客主流程

    Args:
        keyword: 搜索关键词
        product_url: 产品链接
        product_name: 产品名称
        max_comments: 本运行最多评论数
        dry_run: 仅测试不发送
        auto_keywords: 是否AI生成关键词

    Returns:
        运行报告 dict
    """
    result = {
        "status": "ok",
        "keyword": keyword,
        "product_url": product_url,
        "dry_run": dry_run,
        "searched": 0,
        "scored": 0,
        "commented": 0,
        "skipped": 0,
        "errors": [],
        "comments": [],
    }

    logger.info("=" * 50)
    logger.info("小红书评论区获客 启动")
    logger.info(f"关键词: {keyword or '(AI自动生成)'}")
    logger.info(f"产品: {product_name or '(未指定)'}")
    logger.info(f"上限: {max_comments}条/次 | Dry-run: {dry_run}")
    logger.info("=" * 50)

    history = load_history()

    # 1. 生成/选择关键词
    keywords = []
    if auto_keywords and product_url:
        keywords = ai_generate_keywords(product_url, product_name, count=10)
    if not keywords and keyword:
        keywords = [keyword]
    if not keywords:
        keywords = load_keywords()
    if not keywords:
        result["status"] = "error"
        result["errors"].append("未找到关键词，请提供 --keyword 或配置 keywords.json")
        return result

    logger.info(f"使用关键词: {keywords}")

    # 2. 依次搜索每个关键词
    product_info = f"产品: {product_name} ({product_url})" if product_url else ""
    all_candidates = []

    for kw in keywords[:5]:  # 最多搜索5个关键词
        try:
            notes = search_notes(kw, sort_by="综合", max_results=15)
            for n in notes:
                if not is_already_commented(n["feed_id"], history):
                    n["from_keyword"] = kw
                    all_candidates.append(n)
            result["searched"] += len(notes)
        except Exception as e:
            logger.warning(f"搜索关键词 '{kw}' 失败: {e}")
            result["errors"].append(f"搜索失败[{kw}]: {str(e)[:50]}")

        # 搜索间隔
        if len(keywords) > 1:
            jitter_delay(2)

    logger.info(f"找到 {len(all_candidates)} 个未评论过的笔记")

    # 3. 评分筛选
    scored_candidates = []
    for idx, note in enumerate(all_candidates[:30]):  # 最多评30篇
        try:
            # 获取详情
            detail = get_note_detail(note["feed_id"], note["xsec_token"])
            # AI评分
            score, score_detail = ai_score_note(note, detail)
            note["score"] = score
            note["score_detail"] = score_detail
            note["detail"] = detail
            scored_candidates.append(note)
            logger.info(f"评分 {idx+1}/{len(all_candidates)}: {note['title'][:30]} → {score}分 ({score_detail})")
        except Exception as e:
            note["score"] = 0
            note["detail"] = {}
            scored_candidates.append(note)
            logger.warning(f"评分失败 {note['title'][:30]}: {e}")

        # 每3篇间隔一下
        if (idx + 1) % 3 == 0 and idx + 1 < len(all_candidates):
            jitter_delay(1)

    result["scored"] = len(scored_candidates)

    # 按分数排序取前N篇
    scored_candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
    top_notes = scored_candidates[:max_comments]

    logger.info(f"\n评分完成，前{len(top_notes)}篇备选:")
    for n in top_notes:
        logger.info(f"  [{n.get('score', 0):.1f}分] {n['title'][:40]} — @{n['author']}")

    # 4. 生成评论并发送
    for idx, note in enumerate(top_notes):
        detail = note.get("detail", {})
        kw = note.get("from_keyword", keyword)

        # 检查频率限制
        ok, msg = check_rate_limit(history)
        if not ok:
            logger.warning(f"⏸️ 频率限制: {msg}")
            result["skipped"] += 1
            break  # 今天不做了

        try:
            # AI生成评论
            comment_data = ai_generate_comment(
                note_title=note.get("title", ""),
                note_desc=detail.get("desc", ""),
                top_comments=detail.get("top_comments", []),
                product_info=product_info,
            )
            comment_text = comment_data["comment"]

            if not comment_text:
                logger.warning(f"生成评论为空，跳过")
                result["errors"].append(f"评论为空: {note['title'][:20]}")
                continue

            logger.info(f"\n[{idx+1}/{len(top_notes)}] @{note['author']}: {note['title'][:30]}")
            logger.info(f"   风格: {comment_data['style']}")
            logger.info(f"   评论: {comment_text}")

            if dry_run:
                logger.info("   (Dry-run，未实际发送)")
                result["comments"].append({
                    "feed_id": note["feed_id"],
                    "title": note["title"],
                    "author": note["author"],
                    "score": note.get("score", 0),
                    "style": comment_data["style"],
                    "comment": comment_text,
                })
                result["commented"] += 1
            else:
                # 发送评论
                success = post_comment_mcp(
                    note["feed_id"], note["xsec_token"], comment_text
                )
                if success:
                    add_to_history(
                        feed_id=note["feed_id"],
                        keyword=kw,
                        comment=comment_text,
                        score=note.get("score", 0),
                        note_title=note["title"],
                        note_author=note["author"],
                    )
                    result["commented"] += 1
                    result["comments"].append({
                        "feed_id": note["feed_id"],
                        "title": note["title"],
                        "author": note["author"],
                        "score": note.get("score", 0),
                        "style": comment_data["style"],
                        "comment": comment_text,
                    })
                else:
                    result["errors"].append(f"评论发送失败: {note['title'][:20]}")
                    result["skipped"] += 1

        except Exception as e:
            logger.error(f"处理笔记出错: {e}")
            result["errors"].append(f"处理异常: {str(e)[:50]}")
            result["skipped"] += 1

        # 发送间隔
        if idx + 1 < len(top_notes):
            delay = ANTI_CRAWL["base_interval_seconds"]
            jitter_delay(delay, ANTI_CRAWL["jitter_ratio"])

    # 汇总输出
    logger.info("=" * 50)
    logger.info("运行完成")
    logger.info(f"  搜索到: {result['searched']} 篇")
    logger.info(f"  评分: {result['scored']} 篇")
    logger.info(f"  评论: {result['commented']} 篇")
    logger.info(f"  跳过: {result['skipped']} 篇")
    if result["errors"]:
        logger.info(f"  错误: {len(result['errors'])} 个")
    logger.info("=" * 50)

    return result


# ════════════════════════════════════════════════════════
#  CLI 入口
# ════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="小红书评论区获客工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    mode = parser.add_argument_group("运行模式")
    mode.add_argument("--keyword", "-k", help="搜索关键词")
    mode.add_argument("--auto", action="store_true",
                      help="自动模式（AI生成关键词+搜索+评论）")
    mode.add_argument("--product-url", "-u",
                      default=os.environ.get("XHS_PRODUCT_URL", ""),
                      help="产品链接")
    mode.add_argument("--product-name", "-n",
                      default=os.environ.get("XHS_PRODUCT_NAME", ""),
                      help="产品名称")

    opt = parser.add_argument_group("选项")
    opt.add_argument("--max-comments", "-m", type=int, default=5,
                     help="本运行最多评论数（默认5）")
    opt.add_argument("--dry-run", action="store_true",
                     help="Dry-run 模式：不真正发送评论")
    opt.add_argument("--verbose", "-v", action="store_true", help="详细日志")

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    log_fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging.basicConfig(
        level=log_level, format=log_fmt,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(str(DATA_DIR / f"acquisition_{datetime.now().strftime('%Y%m%d')}.log"),
                                encoding="utf-8"),
        ],
    )

    if not args.keyword and not args.auto:
        parser.print_help()
        print("\n错误: 请提供 --keyword 或使用 --auto 自动模式")
        sys.exit(1)

    result = run(
        keyword=args.keyword or "",
        product_url=args.product_url,
        product_name=args.product_name,
        max_comments=args.max_comments,
        dry_run=args.dry_run,
        auto_keywords=args.auto,
    )

    print("\n" + json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
