import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from tests.premium_compat import compose
ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(os.name=='nt','Windows native build validation')
class PremiumNativeTests(unittest.TestCase):
    def test_os_chooser_spec_and_current_psd_helper_compatibility_without_launching(self):
        parent_root=Path(os.environ['PSD_SOURCE_ROOT']) if os.environ.get('PSD_SOURCE_ROOT') else ROOT
        parent=(parent_root/'desktop_helper/SportsCaveFilesDesktop.cs').read_text(encoding='utf-8')
        source=compose('desktop_helper/SportsCaveFilesDesktop.cs',parent) if parent_root!=ROOT else parent
        if parent_root!=ROOT:
            self.assertIn('openPhotoshop',source);self.assertIn('openPsdApp',source)
            for name in ['NativeCache','NativePhotoshop','TransferGrant']:
                def section(text):
                    start=text.index('class '+name);end=text.find('\ninternal ',start)
                    return text[start:end] if end>=0 else text[start:]
                self.assertEqual(section(source),section(parent),name)
        harness=r"""public static class ChooserHarness {
          public static string Check(string root) {
            var path=System.IO.Path.Combine(root,"fixture.psd");System.IO.File.WriteAllText(path,"safe test");
            var info=NativeFileOpening.OptionsFor(path);var defaults=NativeFileOpening.DefaultAppsInfo();
            var result=new System.Collections.Generic.Dictionary<string,object>{{"flags",info.Flags},{"file",info.File},{"defaults",defaults.FileName},{"shell",defaults.UseShellExecute}};
            foreach(var name in new[]{"missing.psd","blocked.exe"}){var item=System.IO.Path.Combine(root,name);if(name.EndsWith(".exe"))System.IO.File.WriteAllText(item,"not executable");try{NativeFileOpening.OptionsFor(item);result[name]="unexpected";}catch(DesktopException e){result[name]=e.Code;}}
            return new System.Web.Script.Serialization.JavaScriptSerializer().Serialize(result);
          }
        }"""
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);(base/'source.cs').write_text(source+'\n'+harness,encoding='utf-8')
            helper=parent_root/'desktop_helper'
            for name in ['Microsoft.Web.WebView2.Core.dll','Microsoft.Web.WebView2.Wpf.dll']:shutil.copy2(helper/'lib'/name,base/name)
            script=r"""param($Root)
            $ErrorActionPreference='Stop'
            Add-Type -AssemblyName PresentationFramework,PresentationCore,WindowsBase,System.Xaml
            $refs=@('System.dll','System.Core.dll','System.Net.Http.dll','System.Web.Extensions.dll',[System.Windows.DependencyObject].Assembly.Location,[System.Windows.Media.ImageSource].Assembly.Location,[System.Windows.Window].Assembly.Location,[System.Xaml.XamlReader].Assembly.Location,(Join-Path $Root 'Microsoft.Web.WebView2.Core.dll'),(Join-Path $Root 'Microsoft.Web.WebView2.Wpf.dll'))|Select-Object -Unique
            [void][Reflection.Assembly]::LoadFrom((Join-Path $Root 'Microsoft.Web.WebView2.Core.dll'))
            [void][Reflection.Assembly]::LoadFrom((Join-Path $Root 'Microsoft.Web.WebView2.Wpf.dll'))
            Add-Type -TypeDefinition (Get-Content -LiteralPath (Join-Path $Root 'source.cs') -Raw) -Language CSharp -ReferencedAssemblies $refs
            [ChooserHarness]::Check($Root)
            """
            (base/'build.ps1').write_text(script)
            run=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(base/'build.ps1'),str(base)],capture_output=True,text=True,timeout=45)
            self.assertEqual(run.returncode,0,run.stderr);result=json.loads(run.stdout)
            self.assertEqual(result['flags'],4);self.assertEqual(result['defaults'],'ms-settings:defaultapps');self.assertTrue(result['shell'])
            self.assertEqual(result['missing.psd'],'open_with_denied');self.assertEqual(result['blocked.exe'],'open_with_denied')
            self.assertEqual((base/'fixture.psd').read_text(),'safe test')
        print('Actual helper compiled; OS chooser flags and scoped targets validated; retained Photoshop methods unchanged; no chooser/app/settings launched.')

if __name__=='__main__':unittest.main()
