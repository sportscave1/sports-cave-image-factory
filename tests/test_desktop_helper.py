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
        cls.launcher_source = (HELPER_DIR / "PhotoshopProtocolLauncher.cs").read_text(
            encoding="utf-8"
        )

    def test_installer_is_current_user_only_and_persists_approved_root(self):
        self.assertIn('HKCU:\\Software\\Classes\\sports-cave-files', self.install_source)
        self.assertIn('HKCU:\\Software\\Classes\\sports-cave-photoshop', self.install_source)
        self.assertIn("RootPath = $DropboxRoot", self.install_source)
        self.assertIn("$env:LOCALAPPDATA", self.install_source)
        self.assertNotIn("HKLM:\\Software\\Classes\\sports-cave-files", self.install_source)
        self.assertIn("Remove-Item -LiteralPath $protocolKey", self.uninstall_source)
        wrapper = (HELPER_DIR / "Install.cmd").read_text(encoding="utf-8")
        self.assertIn("-ExecutionPolicy Bypass", wrapper)
        self.assertIn('"%~dp0Install.ps1"', wrapper)
        self.assertIn('" "%1"', self.install_source)

    def test_psd_protocol_is_labelled_photoshop_and_forwards_to_secure_helper(self):
        self.assertIn('Register-Protocol $photoshopProtocolKey "Open in Photoshop" "Photoshop"', self.install_source)
        self.assertIn('"Sports Cave Photoshop Launcher.exe"', self.install_source)
        self.assertIn('request.Scheme, "sports-cave-photoshop"', self.launcher_source)
        self.assertIn('"SportsCaveFilesHelper.ps1"', self.launcher_source)
        self.assertIn("UseShellExecute = false", self.launcher_source)
        self.assertIn("CreateNoWindow = true", self.launcher_source)
        self.assertIn('"HKCU:\\Software\\Classes\\sports-cave-photoshop"', self.uninstall_source)

    def test_helper_rejects_commands_and_resolves_only_inside_configured_root(self):
        source = self.helper_source
        self.assertIn("[System.IO.Path]::IsPathRooted($RelativePath)", source)
        self.assertIn('$RelativePath.Contains(":")', source)
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

    def test_windows_clipboard_uses_real_file_drop_and_preferred_effect(self):
        source = self.helper_source
        self.assertIn("SetFileDropList($fileList)", source)
        self.assertIn('SetData("Preferred DropEffect"', source)
        self.assertIn('if ($Effect -eq "move") { [uint32]2 } else { [uint32]1 }', source)
        self.assertIn("[System.Windows.Forms.Clipboard]::SetDataObject($data, $true)", source)
        self.assertIn("Request-FileHydration $targetPath", source)
        self.assertIn('$uri.Host -eq "clipboard"', source)
        self.assertIn('"paths", "effect"', source)
        self.assertIn(" -Sta -WindowStyle Hidden ", self.install_source)

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

    def validate(self, relative_path, scheme="sports-cave-files"):
        uri = f"{scheme}://open?path={quote(relative_path, safe='')}&kind=file"
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

    def validate_clipboard(self, relative_paths, effect="copy"):
        encoded_paths = quote(json.dumps(relative_paths, ensure_ascii=False), safe="")
        uri = f"sports-cave-files://clipboard?paths={encoded_paths}&effect={effect}"
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

    def test_photoshop_protocol_accepts_only_psd_and_psb(self):
        psd = self.dropbox_root / "Designs" / "Approved.psd"
        pdf = self.dropbox_root / "Designs" / "Not Photoshop.pdf"
        psd.write_bytes(b"test")
        pdf.write_bytes(b"test")

        psd_result = self.validate("Designs/Approved.psd", "sports-cave-photoshop")
        pdf_result = self.validate("Designs/Not Photoshop.pdf", "sports-cave-photoshop")

        self.assertEqual(psd_result.returncode, 0, psd_result.stderr)
        self.assertNotEqual(pdf_result.returncode, 0)
        self.assertIn("only supports PSD and PSB", pdf_result.stderr)

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

    def test_multi_item_clipboard_resolves_special_paths_and_rejects_traversal(self):
        first = self.dropbox_root / "Designs" / "O'Neal & All Rise.jpg"
        second = self.dropbox_root / "Designs" / "J\u00fcrgen Final.png"
        first.write_bytes(b"one")
        second.write_bytes(b"two")

        result = self.validate_clipboard(
            ["Designs/O'Neal & All Rise.jpg", "Designs/J\u00fcrgen Final.png"],
            effect="move",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            [Path(line) for line in result.stdout.splitlines() if line.strip()],
            [first, second],
        )
        denied = self.validate_clipboard(["../outside.txt"])
        self.assertNotEqual(denied.returncode, 0)
        self.assertIn("not allowed", denied.stderr.casefold())


if __name__ == "__main__":
    unittest.main()
