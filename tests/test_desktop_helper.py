import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
HELPER_DIR = ROOT / "desktop_helper"
MAC_HELPER_DIR = ROOT / "desktop_helper_macos"


class DesktopHelperContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helper_source = (HELPER_DIR / "SportsCaveFilesHelper.ps1").read_text(
            encoding="utf-8"
        )
        cls.install_source = (HELPER_DIR / "Install.ps1").read_text(encoding="utf-8")
        cls.uninstall_source = (HELPER_DIR / "Uninstall.ps1").read_text(encoding="utf-8")

    def test_installer_is_current_user_only_and_persists_approved_root(self):
        self.assertIn('HKCU:\\Software\\Classes\\sports-cave-files', self.install_source)
        self.assertIn("RootPath = $DropboxRoot", self.install_source)
        self.assertIn("$env:LOCALAPPDATA", self.install_source)
        self.assertNotIn("HKLM:\\Software\\Classes\\sports-cave-files", self.install_source)
        self.assertIn("Remove-Item -LiteralPath $protocolKey", self.uninstall_source)
        wrapper = (HELPER_DIR / "Install.cmd").read_text(encoding="utf-8")
        self.assertIn("-ExecutionPolicy Bypass", wrapper)
        self.assertIn('"%~dp0Install.ps1"', wrapper)
        self.assertIn('" "%1"', self.install_source)

    def test_helper_rejects_commands_and_resolves_only_inside_configured_root(self):
        source = self.helper_source
        self.assertIn("[System.IO.Path]::IsPathRooted($relative)", source)
        self.assertIn('$relative.Contains(":")', source)
        self.assertIn('$_ -in @(".", "..")', source)
        self.assertIn("$target.StartsWith($rootPrefix", source)
        self.assertIn('".exe"', source)
        self.assertIn('".ps1"', source)
        self.assertIn('$_ -notin @("path", "kind")', source)

    def test_psd_prefers_photoshop_then_uses_windows_association(self):
        source = self.helper_source
        self.assertIn('$extension -in @(".psd", ".psb")', source)
        self.assertIn("Find-Photoshop", source)
        self.assertIn("Start-Process -FilePath $photoshop", source)
        self.assertIn("Start-Process -FilePath $target -ErrorAction Stop", source)
        self.assertIn('Start-Process -FilePath "explorer.exe"', source)
        self.assertIn("Request-FileHydration $target", source)

    def test_ai_prefers_illustrator_then_uses_windows_association(self):
        source = self.helper_source
        self.assertIn('$extension -eq ".ai"', source)
        self.assertIn("Find-Illustrator", source)
        self.assertIn("Start-Process -FilePath $illustrator", source)

    def test_macos_helper_is_separate_root_scoped_and_uses_native_open(self):
        helper = (MAC_HELPER_DIR / "SportsCaveFilesHelper.py").read_text(encoding="utf-8")
        installer = (MAC_HELPER_DIR / "Install.command").read_text(encoding="utf-8")
        self.assertIn('parsed.scheme != "sports-cave-files"', helper)
        self.assertIn("target.relative_to(root)", helper)
        self.assertIn('"Adobe Photoshop"', helper)
        self.assertIn('"Adobe Illustrator"', helper)
        self.assertIn('["/usr/bin/open", str(target)]', helper)
        self.assertIn("CFBundleURLSchemes", installer)
        self.assertIn("sports-cave-files", installer)
        self.assertNotIn("powershell", installer.casefold())


@unittest.skipUnless(os.name == "nt" and shutil.which("powershell.exe"), "Windows helper test")
class DesktopHelperWindowsValidationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.helper_dir = self.base / "helper"
        self.helper_dir.mkdir()
        self.helper = self.helper_dir / "SportsCaveFilesHelper.ps1"
        shutil.copy2(HELPER_DIR / "SportsCaveFilesHelper.ps1", self.helper)
        self.dropbox_root = self.base / "Sportscave Team Folder"
        (self.dropbox_root / "Designs").mkdir(parents=True)
        (self.helper_dir / "config.json").write_text(
            json.dumps({"RootPath": str(self.dropbox_root)}),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def validate(self, relative_path):
        uri = f"sports-cave-files://open?path={quote(relative_path, safe='')}&kind=file"
        return subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.helper),
                uri,
                "-ValidateOnly",
                "-NoDialog",
            ],
            capture_output=True,
            encoding="utf-8",
            text=True,
            timeout=10,
            check=False,
        )

    def test_spaces_ampersands_apostrophes_and_unicode_resolve_exactly(self):
        target = self.dropbox_root / "Designs" / "O'Neal & All Rise - J\u00fadge.psd"
        target.write_bytes(b"test")

        result = self.validate("Designs/O'Neal & All Rise - J\u00fadge.psd")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()), target)

    def test_jpg_png_psd_and_pdf_are_safe_supported_files(self):
        for filename in ("Photo.jpg", "Artwork.png", "Design.psd", "Proof.pdf"):
            target = self.dropbox_root / "Designs" / filename
            target.write_bytes(b"test")

            result = self.validate(f"Designs/{filename}")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(Path(result.stdout.strip()), target)

    def test_traversal_absolute_and_executable_paths_are_rejected(self):
        outside = self.base / "outside.txt"
        outside.write_text("private", encoding="utf-8")
        executable = self.dropbox_root / "Designs" / "unsafe.cmd"
        executable.write_text("echo blocked", encoding="utf-8")

        traversal = self.validate("../outside.txt")
        absolute = self.validate(str(outside))
        blocked = self.validate("Designs/unsafe.cmd")

        self.assertNotEqual(traversal.returncode, 0)
        self.assertNotEqual(absolute.returncode, 0)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("not allowed", traversal.stderr.casefold())
        self.assertIn("cannot be opened", blocked.stderr.casefold())


if __name__ == "__main__":
    unittest.main()
