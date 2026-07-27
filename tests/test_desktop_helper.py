import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
HELPER_DIR = ROOT / "desktop_helper"
MAC_HELPER_DIR = ROOT / "desktop_helper_macos"
DESKTOP_SOURCE = HELPER_DIR / "SportsCaveFilesDesktop.cs"


class DesktopHelperContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = DESKTOP_SOURCE.read_text(encoding="utf-8")
        cls.install = (HELPER_DIR / "Install.ps1").read_text(encoding="utf-8")
        cls.uninstall = (HELPER_DIR / "Uninstall.ps1").read_text(encoding="utf-8")
        cls.open_helper = (HELPER_DIR / "SportsCaveFilesHelper.ps1").read_text(
            encoding="utf-8"
        )

    def test_installer_builds_per_user_windowless_persistent_webview_host(self):
        self.assertIn("SportsCaveFilesDesktop.cs", self.install)
        self.assertIn("-OutputType WindowsApplication", self.install)
        self.assertIn("Microsoft.Web.WebView2.Core.dll", self.install)
        self.assertIn("Microsoft.Web.WebView2.Wpf.dll", self.install)
        self.assertIn("WebView2Loader.dll", self.install)
        self.assertIn("HelperVersion = 5", self.install)
        self.assertIn("CurrentVersion\\Run", self.install)
        self.assertIn('" --background', self.install)
        self.assertIn("Sports Cave OS Desktop.lnk", self.install)
        self.assertNotIn("HKLM:\\Software\\Classes", self.install)
        self.assertIn("SportsCaveOSDesktop", self.uninstall)

    def test_shell_is_persistent_and_custom_protocol_only_shows_or_opens(self):
        self.assertIn("new Mutex(true, InstanceName(MutexName)", self.source)
        self.assertIn("false, EventResetMode.AutoReset, InstanceName(ShowEventName)", self.source)
        self.assertIn('request.Host == "app"', self.source)
        self.assertIn('request.Host == "open"', self.source)
        self.assertIn("window.ShowAndFocus", self.source)
        self.assertNotIn("sports-cave-files://drag", self.source)
        self.assertNotIn("TcpListener", self.source)

    def test_webview_bridge_is_origin_scoped_and_action_allowlisted(self):
        self.assertIn("browser.CoreWebView2.WebMessageReceived += OnWebMessage", self.source)
        self.assertIn("config.Allows(args.Source)", self.source)
        self.assertIn("AllowedOrigins.Contains", self.source)
        for action in ("drag", "copyFile", "copyImage", "openFile"):
            self.assertIn(f'action != "{action}"', self.source)
        self.assertIn("Settings.AreHostObjectsAllowed = false", self.source)
        self.assertIn("navigationArgs.Cancel = true", self.source)
        self.assertNotIn("Dropbox", self.source.split("internal sealed class TransferGrant")[0])

    def test_unsigned_desktop_files_route_opens_the_existing_sign_in_flow(self):
        self.assertIn("NavigationCompleted +=", self.source)
        self.assertIn("navigationArgs.HttpStatusCode == 403", self.source)
        self.assertIn('"/files-window"', self.source)
        self.assertIn("current.GetLeftPart(UriPartial.Authority) + \"/\"", self.source)

    def test_native_drag_and_clipboard_use_real_windows_file_drop_copy(self):
        self.assertIn("System.Windows.DataFormats.FileDrop", self.source)
        self.assertIn('data.SetData("Preferred DropEffect"', self.source)
        self.assertIn("BitConverter.GetBytes(1U)", self.source)
        self.assertIn("System.Windows.DragDrop.DoDragDrop(", self.source)
        self.assertIn("DragDropEffects.Copy", self.source)
        self.assertIn("SetClipboardData(data)", self.source)
        self.assertIn("for (int attempt = 0; attempt < 8; attempt++)", self.source)
        self.assertIn("System.Windows.Clipboard.SetDataObject(data, true)", self.source)
        self.assertIn('"clipboard_busy"', self.source)
        self.assertIn("GetAsyncKeyState(1)", self.source)
        self.assertIn("DoDragDrop(\n                        this, data", self.source)
        self.assertNotIn("File.Move(paths", self.source)

    def test_validated_items_use_the_configured_local_dropbox_root_before_cache(self):
        self.assertIn('raw.ContainsKey("RootPath")', self.source)
        self.assertIn("cache = new NativeCache(config.RootPath)", self.source)
        self.assertIn("ResolveLocalRoots(manifest)", self.source)
        self.assertIn('entry["source_relative_path"]', self.source)
        self.assertIn("EnsureInside(localRoot, target)", self.source)
        self.assertIn("Directory.Exists(target)", self.source)
        self.assertIn("File.Exists(target)", self.source)
        self.assertIn("return localPaths", self.source)
        self.assertLess(
            self.source.index("return localPaths"),
            self.source.index('var items = manifest["items"] as IList'),
        )

    def test_image_clipboard_sets_pixels_and_png_transparency_payload(self):
        self.assertIn("PngBitmapEncoder", self.source)
        self.assertIn('data.SetData("PNG"', self.source)
        self.assertIn("data.SetImage(bitmap)", self.source)
        self.assertIn("BitmapCacheOption.OnLoad", self.source)

    def test_cache_is_revision_keyed_sanitized_bounded_and_preserves_leases(self):
        self.assertIn('"SportsCaveOS", "FileCache"', self.source)
        self.assertIn('Convert.ToString(item["cache_key"])', self.source)
        self.assertIn("SafeRelativePath", self.source)
        self.assertIn("Path.GetInvalidFileNameChars()", self.source)
        self.assertIn("Path.IsPathRooted(raw)", self.source)
        self.assertIn('part == "." || part == ".."', self.source)
        self.assertIn('File.WriteAllText(Path.Combine(lease, ".active")', self.source)
        self.assertIn('File.WriteAllText(Path.Combine(lease, ".lease")', self.source)
        self.assertIn("TimeSpan.FromDays(7)", self.source)
        self.assertIn("TimeSpan.FromDays(14)", self.source)
        self.assertIn("CreateHardLink", self.source)

    def test_transfer_client_uses_only_short_lived_server_grant(self):
        self.assertIn("X-Sports-Cave-Transfer-Secret", self.source)
        self.assertIn("/api/files-native-transfer/manifest", self.source)
        self.assertIn("/api/files-native-transfer/content", self.source)
        self.assertNotIn("refresh_token", self.source.casefold())
        self.assertNotIn("access_token", self.source.casefold())
        self.assertNotIn("signed_url", self.source.casefold())

    def test_diagnostics_are_non_sensitive(self):
        log = self.source[self.source.index("internal static class DesktopLog") :]
        for field in ("action=", "status=", "code=", "items="):
            self.assertIn(field, log)
        self.assertNotIn("BaseUrl", log)
        self.assertNotIn("Ticket", log)
        self.assertNotIn("Secret", log)

    def test_legacy_open_helper_remains_root_scoped(self):
        self.assertIn("[System.IO.Path]::IsPathRooted($RelativePath)", self.open_helper)
        self.assertIn('$RelativePath.Contains(":")', self.open_helper)
        self.assertIn('$_ -in @(".", "..")', self.open_helper)
        self.assertIn("$target.StartsWith($rootPrefix", self.open_helper)
        self.assertIn("Find-Photoshop", self.open_helper)

    def test_macos_helper_is_unchanged_and_root_scoped(self):
        helper = (MAC_HELPER_DIR / "SportsCaveFilesHelper.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('parsed.scheme != "sports-cave-files"', helper)
        self.assertIn("target.relative_to(root)", helper)


@unittest.skipUnless(
    os.name == "nt" and shutil.which("powershell.exe"),
    "Windows desktop build test",
)
class DesktopWindowsBuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.executable = self.base / "SportsCaveOSDesktop.exe"
        self._copy_runtime()

    def tearDown(self):
        self.temporary.cleanup()

    def _copy_runtime(self):
        shutil.copy2(HELPER_DIR / "lib" / "Microsoft.Web.WebView2.Core.dll", self.base)
        shutil.copy2(HELPER_DIR / "lib" / "Microsoft.Web.WebView2.Wpf.dll", self.base)
        shutil.copy2(
            HELPER_DIR / "runtimes" / "win-x64" / "native" / "WebView2Loader.dll",
            self.base,
        )
        shutil.copy2(HELPER_DIR / "SportsCaveFilesHelper.ps1", self.base)
        (self.base / "config.json").write_text(
            json.dumps(
                {
                    "AppUrl": "http://127.0.0.1:8501/files-window",
                    "RootPath": "",
                    "AllowedOrigins": ["http://127.0.0.1:8501"],
                    "HelperVersion": 5,
                }
            ),
            encoding="utf-8",
        )

    def _compile(self):
        source = str(DESKTOP_SOURCE).replace("'", "''")
        output = str(self.executable).replace("'", "''")
        core = str(HELPER_DIR / "lib" / "Microsoft.Web.WebView2.Core.dll").replace(
            "'", "''"
        )
        wpf = str(HELPER_DIR / "lib" / "Microsoft.Web.WebView2.Wpf.dll").replace(
            "'", "''"
        )
        script = (
            "Add-Type -AssemblyName PresentationFramework; "
            "Add-Type -AssemblyName PresentationCore; "
            "Add-Type -AssemblyName WindowsBase; "
            "Add-Type -AssemblyName System.Xaml; "
            f"$source=Get-Content -LiteralPath '{source}' -Raw; "
            "$refs=@('System.dll','System.Core.dll','System.Net.Http.dll',"
            "'System.Web.Extensions.dll',[System.Windows.DependencyObject].Assembly.Location,"
            "[System.Windows.Media.ImageSource].Assembly.Location,"
            "[System.Windows.Window].Assembly.Location,[System.Xaml.XamlReader].Assembly.Location,"
            f"'{core}','{wpf}')|Select-Object -Unique; "
            f"Add-Type -TypeDefinition $source -Language CSharp -ReferencedAssemblies $refs "
            f"-OutputAssembly '{output}' -OutputType WindowsApplication"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_compiled_background_host_stays_running_without_console(self):
        self._compile()
        process = subprocess.Popen(
            [str(self.executable), "--background"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            env={
                **os.environ,
                "SPORTS_CAVE_FILE_CACHE": str(self.base / "cache"),
                "SPORTS_CAVE_DESKTOP_INSTANCE": "test",
            },
        )
        try:
            time.sleep(1)
            self.assertIsNone(process.poll())
        finally:
            process.terminate()
            process.wait(timeout=5)


@unittest.skipUnless(
    os.name == "nt" and shutil.which("powershell.exe"),
    "Windows helper test",
)
class DesktopHelperOpenValidationTests(unittest.TestCase):
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
            json.dumps({"RootPath": str(self.dropbox_root)}), encoding="utf-8"
        )

    def tearDown(self):
        self.temporary.cleanup()

    def validate(self, relative_path):
        uri = f"sports-cave-files://open?path={quote(relative_path, safe='')}&kind=file"
        return subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass", "-File", str(self.helper), uri,
                "-ValidateOnly", "-NoDialog",
            ],
            capture_output=True,
            encoding="utf-8",
            text=True,
            timeout=10,
            check=False,
        )

    def test_special_characters_and_traversal_validation(self):
        target = self.dropbox_root / "Designs" / "O'Neal & J\u00fcrgen.psd"
        target.write_bytes(b"test")
        valid = self.validate("Designs/O'Neal & J\u00fcrgen.psd")
        self.assertEqual(valid.returncode, 0, valid.stderr)
        self.assertEqual(Path(valid.stdout.strip()), target)
        self.assertNotEqual(self.validate("../outside.psd").returncode, 0)
        self.assertNotEqual(self.validate(str(self.base / "outside.psd")).returncode, 0)


if __name__ == "__main__":
    unittest.main()
