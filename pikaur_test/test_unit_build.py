"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""
# mypy: disable-error-code=no-untyped-def

from contextlib import chdir
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest import mock

from pikaur.build import PackageBuild
from pikaur.pikatypes import AURPackageInfo
from pikaur.spawn import spawn
from pikaur_test.helpers import PikaurTestCase


class PackageBuildTest(PikaurTestCase):

    def test_clone_from_unavailable_cwd(self):
        # HTTP uses Git's remote helper, unlike a local file:// clone.
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source"
            for command in (
                    ["git", "init", str(source_path)],
                    [
                        "git", "-C", str(source_path),
                        "-c", "user.name=Pikaur Test",
                        "-c", "user.email=pikaur-test@example.com",
                        "-c", "commit.gpgsign=false",
                        "commit", "--allow-empty", "-m", "Initial commit",
                    ],
                    ["git", "-C", str(source_path), "update-server-info"],
            ):
                result = spawn(command)
                self.assertEqual(result.returncode, 0, result.stderr_text)

            server = HTTPServer(
                ("127.0.0.1", 0),
                partial(SimpleHTTPRequestHandler, directory=str(temp_path)),
            )
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                package_name = "test-clone-from-unavailable-cwd-784165"
                aur_package = AURPackageInfo(
                    name=package_name, packagebase=package_name, version="1.0",
                )
                repo_url = f"http://127.0.0.1:{server.server_port}/source/.git"
                cwd = temp_path / "cwd"
                cwd.mkdir()
                with (
                        mock.patch(
                            "pikaur.build.find_aur_packages", return_value=([aur_package], []),
                        ),
                        mock.patch("pikaur.build.AurReposCachePath", return_value=temp_path),
                        mock.patch("pikaur.build.BuildCachePath", return_value=temp_path / "build"),
                        mock.patch("pikaur.build.PikaurConfig") as config,
                        mock.patch("pikaur.build.get_repo_url", return_value=repo_url),
                        mock.patch("pikaur.build.wrap_proxy_env", side_effect=lambda cmd: cmd),
                        mock.patch("pikaur.build.isolate_root_cmd", side_effect=lambda cmd: cmd),
                ):
                    config.return_value.build.KeepDevBuildDir.get_bool.return_value = False
                    config.return_value.build.IgnoreArch.get_bool.return_value = False
                    build = PackageBuild(package_names=[package_name])

                    self.assertEqual(build.repo_path, temp_path / package_name)
                    with chdir(cwd):
                        # Removing the cwd also exercises the failure when running as root.
                        cwd.rmdir()
                        clone_result = build.update_aur_repo()

                if clone_result is None:
                    self.fail("Expected a clone command")
                self.assertEqual(clone_result.returncode, 0, clone_result.stderr_text)
                result = spawn(["git", "-C", str(build.repo_path), "rev-parse", "HEAD"])
                self.assertEqual(result.returncode, 0, result.stderr_text)
            finally:
                server.shutdown()
                thread.join()
                server.server_close()
