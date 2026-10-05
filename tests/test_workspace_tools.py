"""
Boundary and behavior tests for workspace_tools. Standard library only, no model needed.

Run from the project root:   python -m unittest -v
Each test builds a throwaway workspace plus an "outside" directory holding secrets,
then points workspace_tools.WORKSPACE at it.
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import workspace_tools as wt  # noqa: E402

HAS_SYMLINKS = hasattr(os, "symlink") and os.name != "nt"


class WorkspaceToolsTest(unittest.TestCase):
    def setUp(self):
        # resolve(): on macOS the temp dir lives behind the /var -> /private/var symlink
        self.base = Path(tempfile.mkdtemp()).resolve()
        self.ws = self.base / "ws"
        self.outside = self.base / "outside"
        (self.ws / "app").mkdir(parents=True)
        (self.ws / ".git").mkdir()
        (self.outside / "sub").mkdir(parents=True)

        (self.ws / "app" / "main.py").write_text("def create_token():\n    return 'jwt'\n")
        (self.ws / "long.txt").write_text("".join(f"line {i}\n" for i in range(1, 11)))
        (self.ws / ".env").write_text("DB_PASSWORD=hunter2\n")
        (self.ws / ".env.example").write_text("DB_PASSWORD=changethis\n")
        (self.ws / ".git" / "config").write_text("url=https://TOKEN@github.com\n")
        (self.outside / "secrets.env").write_text("OUTSIDE_SECRET=abc123\n")
        (self.outside / "sub" / "x.txt").write_text("OUTSIDE_DIR_SECRET\n")

        patcher = mock.patch.object(wt, "WORKSPACE", self.ws)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)

    # --- the reported bug: search_code following a file symlink out of the workspace ---

    @unittest.skipUnless(HAS_SYMLINKS, "needs symlinks")
    def test_search_does_not_read_file_symlink_outside(self):
        os.symlink(self.outside / "secrets.env", self.ws / "link.env")
        os.symlink(self.outside / "secrets.env", self.ws / "innocent.txt")
        result = wt.search_code("OUTSIDE_SECRET")
        self.assertNotIn("abc123", result)
        self.assertEqual(result, "No matches.")

    @unittest.skipUnless(HAS_SYMLINKS, "needs symlinks")
    def test_search_does_not_descend_dir_symlink_outside(self):
        os.symlink(self.outside / "sub", self.ws / "linkdir")
        self.assertEqual(wt.search_code("OUTSIDE_DIR_SECRET"), "No matches.")

    @unittest.skipUnless(HAS_SYMLINKS, "needs symlinks")
    def test_search_root_that_is_outside_symlink_is_refused(self):
        os.symlink(self.outside / "sub", self.ws / "linkdir")
        self.assertTrue(wt.search_code("x", path="linkdir").startswith("ERROR"))

    @unittest.skipUnless(HAS_SYMLINKS, "needs symlinks")
    def test_read_and_search_agree_on_outside_symlink(self):
        os.symlink(self.outside / "secrets.env", self.ws / "innocent.txt")
        self.assertTrue(wt.read_file("innocent.txt").startswith("ERROR"))
        self.assertEqual(wt.search_code("OUTSIDE_SECRET"), "No matches.")

    # --- related leaks and crashes in list_dir ---

    @unittest.skipUnless(HAS_SYMLINKS, "needs symlinks")
    def test_list_dir_hides_outside_symlink_and_its_size(self):
        os.symlink(self.outside / "secrets.env", self.ws / "link.env")
        listing = wt.list_dir(".")
        self.assertNotIn("link.env", listing)
        self.assertIn("hidden by workspace policy", listing)

    @unittest.skipUnless(HAS_SYMLINKS, "needs symlinks")
    def test_list_dir_survives_broken_symlink(self):
        os.symlink(self.ws / "does-not-exist", self.ws / "broken")
        listing = wt.list_dir(".")  # original code raised FileNotFoundError here
        self.assertIn("broken  (broken link)", listing)

    # --- symlinks that stay inside are fine ---

    @unittest.skipUnless(HAS_SYMLINKS, "needs symlinks")
    def test_symlink_inside_workspace_is_allowed(self):
        os.symlink(self.ws / "app" / "main.py", self.ws / "alias.py")
        self.assertIn("create_token", wt.read_file("alias.py"))
        self.assertIn("alias.py:1:", wt.search_code("create_token"))

    # --- traversal and absolute paths ---

    def test_traversal_and_absolute_paths_refused_by_every_tool(self):
        for bad in ["../outside/secrets.env", "/etc/hostname", "app/../../outside"]:
            with self.subTest(path=bad):
                self.assertTrue(wt.read_file(bad).startswith("ERROR"))
                self.assertTrue(wt.list_dir(bad).startswith("ERROR"))
                self.assertTrue(wt.search_code("x", path=bad).startswith("ERROR"))

    # --- secret deny-list ---

    def test_secret_files_denied_but_examples_allowed(self):
        self.assertIn("secret policy", wt.read_file(".env"))
        self.assertIn("secret policy", wt.read_file(".git/config"))
        self.assertNotIn("hunter2", wt.search_code("DB_PASSWORD"))
        self.assertIn(".env.example:1:", wt.search_code("DB_PASSWORD"))
        self.assertIn("changethis", wt.read_file(".env.example"))
        self.assertNotIn(".env  (", wt.list_dir("."))

    @unittest.skipUnless(HAS_SYMLINKS, "needs symlinks")
    def test_innocent_name_linking_to_secret_is_denied(self):
        os.symlink(self.ws / ".env", self.ws / "notes.txt")
        self.assertIn("secret policy", wt.read_file("notes.txt"))
        self.assertNotIn("hunter2", wt.search_code("hunter2"))

    # --- non-regular files and bounds ---

    @unittest.skipUnless(hasattr(os, "mkfifo"), "needs mkfifo")
    def test_fifo_is_never_opened(self):
        os.mkfifo(self.ws / "pipe")
        # If the tools opened the FIFO, these calls would block forever.
        self.assertTrue(wt.read_file("pipe").startswith("ERROR"))
        self.assertIn("main.py", wt.search_code("create_token"))

    def test_read_file_paging_and_argument_bounds(self):
        page = wt.read_file("long.txt", start_line=3, max_lines=2)
        self.assertIn("    3 | line 3", page)
        self.assertIn("start_line=5", page)
        self.assertIn("    1 | line 1", wt.read_file("long.txt", start_line=-4, max_lines=1))
        self.assertIn("    1 | line 1", wt.read_file("long.txt", max_lines=-5))
        self.assertIn("past the end", wt.read_file("long.txt", start_line=99))

    def test_oversized_file_skipped_by_search_and_refused_by_read(self):
        with mock.patch.object(wt, "MAX_FILE_BYTES", 10):
            self.assertEqual(wt.search_code("line 1"), "No matches.")
            self.assertIn("larger than", wt.read_file("long.txt"))

    def test_normal_behavior_still_works(self):
        self.assertIn("app/main.py:1: def create_token():", wt.search_code(r"def \w+_token"))
        self.assertIn("app/", wt.list_dir("."))
        self.assertTrue(wt.search_code("(").startswith("ERROR"))  # invalid regex


if __name__ == "__main__":
    unittest.main()
