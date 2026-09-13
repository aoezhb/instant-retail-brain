from __future__ import annotations

import unittest

from ird.agents import RuleBasedAgent


class AgentTests(unittest.TestCase):
    def test_rule_agent_only_explains_record(self) -> None:
        record = {"result_summary": {"aggregate": {"recommended_order_qty": 4, "expected_cost": 8}, "items": []}}
        agent = RuleBasedAgent()
        self.assertIn("4", agent.explain(record))
        self.assertNotIn("None", agent.explain(record))
        self.assertIn("deterministic", agent.orchestrate("review", record))


if __name__ == "__main__":
    unittest.main()
