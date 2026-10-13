import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HELPER=ROOT/'desktop_helper'


def dropbox_hash(data):
    hashes=b''.join(hashlib.sha256(data[i:i+4194304]).digest() for i in range(0,len(data),4194304))
    return hashlib.sha256(hashes).hexdigest()


@unittest.skipUnless(os.name=='nt' and shutil.which('powershell.exe'),'Native Windows test')
class NativePhotoshopWindowsTests(unittest.TestCase):
    def test_actual_compiled_helper_hash_hydration_path_and_launch_spec(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);local=base/'Sportscave Team Folder';target=local/'02_TASKS'/'03_DESIGNS-LIVE-ONLINE-UPLOADED'/"Renamed - O'Neal & J\u00fcrgen.psd";target.parent.mkdir(parents=True)
            data=b'8BPS'+bytes(range(256))*17000;target.write_bytes(data)
            manifest={'purpose':'photoshop_master','roots':[{'source_relative_path':target.relative_to(local).as_posix(),'is_directory':False}],
                      'items':[{'dropbox_id':'id:real-mapping-mocked','is_directory':False,'name':target.name,'size':len(data),'content_hash':dropbox_hash(data)}]}
            (base/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
            for name in ('Microsoft.Web.WebView2.Core.dll','Microsoft.Web.WebView2.Wpf.dll'):
                shutil.copy2(HELPER/'lib'/name,base/name)
            harness='''public static class NativePsdHarness {
              public static string Check(string root,string json) {
                try { var manifest=new System.Web.Script.Serialization.JavaScriptSerializer().DeserializeObject(json) as System.Collections.Generic.Dictionary<string,object>;
                  var cache=new NativeCache(root);var target=cache.ResolvePhotoshopMaster(manifest);
                  var items=(System.Collections.IList)manifest["items"];var item=(System.Collections.Generic.Dictionary<string,object>)items[0];
                  NativePhotoshop.VerifyMasterAsync(target,root,System.Convert.ToInt64(item["size"]),System.Convert.ToString(item["content_hash"]),System.Threading.CancellationToken.None).GetAwaiter().GetResult();
                  return "verified"; } catch(DesktopException error) { return error.Code; }
              }
              public static bool DefaultApp(string target) { return NativePhotoshop.DefaultAppStartInfo(target).UseShellExecute; }
              public static string MissingPhotoshop(string target) { try{NativePhotoshop.StartInfo("",target);return "unexpected";}catch(DesktopException error){return error.Code;} }
              public static string LaunchSpec(string target) {
                string executable=NativePhotoshop.FindRequiredApplication();var spec=NativePhotoshop.StartInfo(executable,target);
                return new System.Web.Script.Serialization.JavaScriptSerializer().Serialize(new { executable=System.IO.Path.GetFileName(spec.FileName),arguments=spec.Arguments,shell=spec.UseShellExecute,version=Program.HelperVersion });
              }
            }'''
            (base/'harness.cs').write_text(harness)
            script='''param([string]$Helper,[string]$TestRoot)
            $ErrorActionPreference='Stop'
            Add-Type -AssemblyName PresentationFramework;Add-Type -AssemblyName PresentationCore;Add-Type -AssemblyName WindowsBase;Add-Type -AssemblyName System.Xaml
            $env:SPORTS_CAVE_FILE_CACHE=Join-Path $TestRoot 'cache'
            $source=(Get-Content -LiteralPath (Join-Path $Helper 'SportsCaveFilesDesktop.cs') -Raw)+[Environment]::NewLine+(Get-Content -LiteralPath (Join-Path $TestRoot 'harness.cs') -Raw)
            $refs=@('System.dll','System.Core.dll','System.Net.Http.dll','System.Web.Extensions.dll',[System.Windows.DependencyObject].Assembly.Location,[System.Windows.Media.ImageSource].Assembly.Location,[System.Windows.Window].Assembly.Location,[System.Xaml.XamlReader].Assembly.Location,(Join-Path $TestRoot 'Microsoft.Web.WebView2.Core.dll'),(Join-Path $TestRoot 'Microsoft.Web.WebView2.Wpf.dll'))|Select-Object -Unique
            [void][Reflection.Assembly]::LoadFrom((Join-Path $TestRoot 'Microsoft.Web.WebView2.Core.dll'))
            [void][Reflection.Assembly]::LoadFrom((Join-Path $TestRoot 'Microsoft.Web.WebView2.Wpf.dll'))
            Add-Type -TypeDefinition $source -Language CSharp -ReferencedAssemblies $refs
            $root=Join-Path $TestRoot 'Sportscave Team Folder'
            $manifest=Get-Content -LiteralPath (Join-Path $TestRoot 'manifest.json') -Raw
            $data=$manifest|ConvertFrom-Json
            $target=Join-Path $root $data.roots[0].source_relative_path
            $result=@{}
            $result.verified=[NativePsdHarness]::Check($root,$manifest)
            $result.defaultApp=[NativePsdHarness]::DefaultApp($target)
            $result.unavailablePhotoshop=[NativePsdHarness]::MissingPhotoshop($target)
            $result.launchSpec=[NativePsdHarness]::LaunchSpec($target)|ConvertFrom-Json
            $data.items[0].content_hash='0000000000000000000000000000000000000000000000000000000000000000'
            $result.stale=[NativePsdHarness]::Check($root,($data|ConvertTo-Json -Depth 6))
            $data.roots[0].source_relative_path='02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/Missing.psd';$data.items[0].name='Missing.psd'
            $result.missing=[NativePsdHarness]::Check($root,($data|ConvertTo-Json -Depth 6))
            $data.roots[0].source_relative_path='02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/99_PSD_NEEDS_REVIEW_DO_NOT_DELETE/Missing.psd'
            $result.review=[NativePsdHarness]::Check($root,($data|ConvertTo-Json -Depth 6))
            $data.roots[0].source_relative_path='../outside.psd'
            $result.traversal=[NativePsdHarness]::Check($root,($data|ConvertTo-Json -Depth 6))
            $data= $manifest|ConvertFrom-Json;$data.purpose='files'
            $result.untrustedGrant=[NativePsdHarness]::Check($root,($data|ConvertTo-Json -Depth 6))
            $result|ConvertTo-Json -Depth 6
            '''
            (base/'harness.ps1').write_text(script)
            run=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(base/'harness.ps1'),str(HELPER),str(base)],capture_output=True,text=True,encoding='utf-8',timeout=45)
            self.assertEqual(run.returncode,0,run.stderr)
            result=json.loads(run.stdout)
            self.assertTrue(result['defaultApp']);self.assertEqual(result['verified'],'verified');self.assertEqual(result['unavailablePhotoshop'],'photoshop_unavailable')
            self.assertEqual(result['stale'],'master_sync_pending');self.assertEqual(result['missing'],'master_not_synced');self.assertEqual(result['review'],'master_scope_denied');self.assertEqual(result['traversal'],'unsafe_path');self.assertEqual(result['untrustedGrant'],'master_required')
            self.assertEqual(result['launchSpec']['executable'],'Photoshop.exe');self.assertEqual(result['launchSpec']['arguments'],'"'+str(target)+'"');self.assertFalse(result['launchSpec']['shell']);self.assertEqual(result['launchSpec']['version'],11)
            self.assertEqual(target.read_bytes(),data)
            print('Actual Windows helper: compiled, >4MB content hash verified, Photoshop.exe launch specification validated; no Photoshop process or real master was opened.')
