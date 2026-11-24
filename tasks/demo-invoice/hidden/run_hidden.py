"""Run the hidden tests and print one JSON line: {"passed": n, "total": m, "failed": [...]}.

Started with `python3 -I`, so neither the working directory nor a planted sitecustomize can change how tests run;
the workspace root is put on the path explicitly.
"""

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(1, str(HERE))

suite = unittest.defaultTestLoader.loadTestsFromName("test_hidden")
result = unittest.TestResult()
suite.run(result)
failed = sorted({test.id().rsplit(".", 1)[-1] for test, _ in result.failures + result.errors})
print(json.dumps({"passed": result.testsRun - len(failed), "total": result.testsRun, "failed": failed}))
