"""
Model-free tests for the Phase 0 loop: a scripted fake replaces ollama.chat.

Works whether or not the real `ollama` package is installed. This is the same idea
Day 3 applies to the LangChain agent with a fake chat model.
"""

import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    import ollama  # noqa: F401
except ImportError:  # stub just enough of the module for import to succeed
    stub = types.ModuleType("ollama")
    stub.ResponseError = type("ResponseError", (Exception,), {})
    stub.chat = None
    sys.modules["ollama"] = stub

import phase0_raw_loop as p0  # noqa: E402


def tool_call(name, **args):
    return NS(function=NS(name=name, arguments=args))


def reply(content="", calls=None):
    return NS(message=NS(content=content, tool_calls=calls or []))


class Phase0LoopTest(unittest.TestCase):
    def run_script(self, responses, registry=None):
        messages = [{"role": "system", "content": "test"}]
        patches = [mock.patch.object(p0.ollama, "chat", side_effect=responses, create=True)]
        if registry is not None:
            patches.append(mock.patch.dict(p0.TOOL_REGISTRY, registry, clear=True))
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        with mock.patch("builtins.print"):
            answer = p0.run_turn(messages, "question")
        return answer, messages

    def tool_results(self, messages):
        return [m["content"] for m in messages if isinstance(m, dict) and m.get("role") == "tool"]

    def test_tool_exception_is_reported_not_raised(self):
        def boom():
            raise RuntimeError("internal detail")
        answer, msgs = self.run_script([reply(calls=[tool_call("boom")]), reply("done")],
                                       registry={"boom": boom})
        self.assertEqual(answer, "done")
        self.assertEqual(self.tool_results(msgs), ["ERROR: boom failed with RuntimeError"])

    def test_unknown_tool_and_bad_arguments_are_reported(self):
        answer, msgs = self.run_script([
            reply(calls=[tool_call("nope")]),
            reply(calls=[tool_call("read_file", wrong_arg=1)]),
            reply("done"),
        ])
        results = self.tool_results(msgs)
        self.assertTrue(results[0].startswith("ERROR: unknown tool 'nope'"))
        self.assertTrue(results[1].startswith("ERROR: bad arguments for read_file"))

    def test_runaway_loop_stops_at_max_steps(self):
        loop_forever = [reply(calls=[tool_call("list_dir")])] * p0.MAX_STEPS
        answer, _ = self.run_script(loop_forever)
        self.assertIn(f"Stopped after {p0.MAX_STEPS} steps", answer)


if __name__ == "__main__":
    unittest.main()
