"""Agent Ensemble — 并行运行多个审查 Agent"""
from .types import ReviewIssue


def run_all_agents(code: str, agents: list) -> dict[str, list[ReviewIssue]]:
    """运行所有 Agent，返回 {agent_name: [issues]}"""
    results = {}
    for agent in agents:
        results[agent.name] = agent.review(code)
    return results
