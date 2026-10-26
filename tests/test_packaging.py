"""The Arch package and desktop launcher must stay in step with the Python package."""

import configparser
from pathlib import Path
import re
import tomllib
import unittest
import xml.dom.minidom

ROOT = Path(__file__).resolve().parent.parent
PACKAGING = ROOT / 'packaging'


class PackagingTest(unittest.TestCase):
    def setUp(self):
        if not PACKAGING.is_dir():
            self.skipTest('packaging files are not part of this source copy')
        self.project = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']

    def test_pkgbuild_version_matches_pyproject(self):
        pkgbuild = (PACKAGING / 'arch' / 'PKGBUILD').read_text()
        self.assertEqual(re.search(r'^pkgver=(.+)$', pkgbuild, re.M).group(1), self.project['version'])
        self.assertNotIn('-', self.project['version'], 'pacman versions cannot contain hyphens')

    def test_desktop_entry_launches_installed_command_with_icon(self):
        entry = configparser.ConfigParser(interpolation=None)
        entry.optionxform = str
        entry.read(PACKAGING / 'mediashrink.desktop')
        desktop = entry['Desktop Entry']
        self.assertIn(desktop['Exec'], self.project['gui-scripts'])
        self.assertTrue((PACKAGING / f"{desktop['Icon']}.svg").is_file())
        self.assertEqual(desktop['StartupWMClass'], 'mediashrink')
        xml.dom.minidom.parse(str(PACKAGING / f"{desktop['Icon']}.svg"))


if __name__ == '__main__':
    unittest.main()
