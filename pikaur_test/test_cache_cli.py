"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""
# mypy: disable-error-code=no-untyped-def

import os

from pikaur_test.helpers import PikaurDbTestCase, pikaur


class CacheCliTestcase(PikaurDbTestCase):

    def test_cache_clean(self):
        # pylint:disable=import-outside-toplevel
        from pikaur.config import BuildCachePath, PackageCachePath

        pikaur("-S python-pygobject-stubs --rebuild --keepbuild")
        self.assertGreaterEqual(
            len(os.listdir(BuildCachePath())), 1,
        )
        self.assertGreaterEqual(
            len(os.listdir(PackageCachePath())), 1,
        )

        pikaur("-Sc --noconfirm")
        self.assertFalse(
            BuildCachePath().exists(),
        )
        self.assertGreaterEqual(
            len(os.listdir(PackageCachePath())), 1,
        )

    def test_cache_full_clean(self):
        # pylint:disable=import-outside-toplevel
        from pikaur.config import BuildCachePath, PackageCachePath

        pikaur("-S python-pygobject-stubs --rebuild --keepbuild")
        self.assertGreaterEqual(
            len(os.listdir(BuildCachePath())), 1,
        )
        self.assertGreaterEqual(
            len(os.listdir(PackageCachePath())), 1,
        )

        pikaur("-Scc --noconfirm")
        self.assertFalse(
            BuildCachePath().exists(),
        )
        self.assertFalse(
            PackageCachePath().exists(),
        )
