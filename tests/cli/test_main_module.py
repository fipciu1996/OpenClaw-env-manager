from __future__ import annotations

import runpy
import unittest
from unittest.mock import patch


class MainModuleTests(unittest.TestCase):
    def test_module_entrypoint_exits_with_cli_status_code(self) -> None:
        with patch("openenv.cli.main", return_value=7):
            with self.assertRaises(SystemExit) as ctx:
                runpy.run_module("clawopenenv.__main__", run_name="__main__")

        self.assertEqual(ctx.exception.code, 7)
