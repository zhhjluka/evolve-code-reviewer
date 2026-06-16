"""Feedback Collector — 审查反馈的收集和统计

每次人工审查操作产生反馈信号：
- accept: 采纳 AI 建议
- reject: 驳回（含原因）
- evolve_accept: 采纳 OpenEvolve 进化后的代码
"""

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class FeedbackEntry:
    pr_id: str
    issue_id: str
    action: str            # accept / reject / evolve_accept
    reviewer: str = ""
    reason: str = ""       # 驳回原因
    agent: str = ""        # 来源 Agent
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class FeedbackCollector:
    """基于 JSONL 文件的反馈收集器"""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _filepath(self, pr_id: str) -> Path:
        return self.data_dir / f"{pr_id}.jsonl"

    def record(self, pr_id: str, issue_id: str, action: str,
               reviewer: str = "", reason: str = "", agent: str = ""):
        """记录一条反馈"""
        entry = FeedbackEntry(
            pr_id=pr_id, issue_id=issue_id, action=action,
            reviewer=reviewer, reason=reason, agent=agent,
        )
        with open(self._filepath(pr_id), "a") as f:
            f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")

    def load(self, pr_id: str) -> list[FeedbackEntry]:
        """加载某个 PR 的所有反馈"""
        filepath = self._filepath(pr_id)
        if not filepath.exists():
            return []

        entries = []
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                entries.append(FeedbackEntry(**data))
        return entries

    def stats(self) -> dict:
        """按 Agent 统计采纳率"""
        stats: dict[str, dict] = {}
        for filepath in self.data_dir.glob("*.jsonl"):
            for entry in self.load(filepath.stem):
                agent = entry.agent or "unknown"
                if agent not in stats:
                    stats[agent] = {"total": 0, "accepted": 0, "rejected": 0, "reasons": []}
                stats[agent]["total"] += 1
                if entry.action == "accept":
                    stats[agent]["accepted"] += 1
                elif entry.action == "reject":
                    stats[agent]["rejected"] += 1
                    if entry.reason:
                        stats[agent]["reasons"].append(entry.reason)

        for agent, s in stats.items():
            s["acceptance_rate"] = s["accepted"] / s["total"] if s["total"] > 0 else 0.0

        return stats
