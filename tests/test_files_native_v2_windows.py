import hashlib, http.server, json, os, shutil, subprocess, tempfile, threading, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(os.name=='nt','Windows helper compile/cache validation')
class NativeWindowsV2Tests(unittest.TestCase):
    def test_protocol_verified_synced_cold_warm_repeat_cache_without_apps(self):
        body=b'x'*(16*1024*1024+7)
        content_hash=hashlib.sha256(b''.join(hashlib.sha256(body[i:i+4*1024*1024]).digest() for i in range(0,len(body),4*1024*1024))).hexdigest()
        count={'downloads':0}
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.headers.get('X-Sports-Cave-Transfer-Secret')!='s'*43:self.send_error(403);return
                count['downloads']+=1;self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            def log_message(self,*args):pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as folder:
                root=Path(folder);helper=ROOT/'desktop_helper'
                for name in ['Microsoft.Web.WebView2.Core.dll','Microsoft.Web.WebView2.Wpf.dll']:shutil.copy2(helper/'lib'/name,root/name)
                synced=root/'synced';synced.mkdir();(synced/'Fixture.psd').write_bytes(body)
                manifest={'purpose':'native_open','total_bytes':len(body),'items':[{'dropbox_id':'id:fixture','revision':'r1','cache_key':'a'*64,'content_hash':content_hash,'name':'Fixture.psd','size':len(body),'is_directory':False,'token':'token'}],'roots':[{'source_relative_path':'Fixture.psd','name':'Fixture.psd','is_directory':False,'revision':'r1'}]}
                (root/'manifest.json').write_text(json.dumps(manifest))
                harness=r"""public static class NativeV2Harness {
                  public static string Run(string root,string origin,string json) {
                    var ser=new System.Web.Script.Serialization.JavaScriptSerializer();var m=ser.DeserializeObject(json) as System.Collections.Generic.Dictionary<string,object>;
                    var cfg=new DesktopConfig {AllowedOrigins=new System.Collections.Generic.HashSet<string>{origin}};
                    string code=new string('x',43);var errors=new System.Collections.Generic.List<string>();
                    foreach(string u in new[]{"sports-cave-files://launch?origin="+System.Uri.EscapeDataString(origin)+"&path=bad#"+code,"sports-cave-files://launch?origin=https%3A%2F%2Fevil.test#"+code,"sports-cave-files://launch?origin="+System.Uri.EscapeDataString(origin)+"#short"}){
                      try {BrowserFileLaunch.Resolve(new System.Uri(u),cfg);errors.Add("unexpected");}catch(DesktopException e){errors.Add(e.Code);}}
                    string valid=BrowserFileLaunch.Resolve(new System.Uri("sports-cave-files://launch?origin="+System.Uri.EscapeDataString(origin)+"#"+code),cfg);
                    var grant=new TransferGrant{BaseUrl=origin,Ticket=new string('t',32),Secret=new string('s',43)};
                    var results=new System.Collections.Generic.Dictionary<string,object>{{"protocol",valid},{"invalid",errors},{"version",Program.HelperVersion}};
                    foreach(string mode in new[]{"baseline_synced","v2_synced","v2_cold","v2_warm_repeat"}) {
                      var samples=new System.Collections.Generic.List<double>();
                      for(int i=0;i<9;i++) {
                        string cacheRoot=System.IO.Path.Combine(root,"cache-"+(mode=="v2_cold"?i.ToString():"shared"));System.Environment.SetEnvironmentVariable("SPORTS_CAVE_FILE_CACHE",cacheRoot);
                        var cache=new NativeCache(mode.Contains("synced")?System.IO.Path.Combine(root,"synced"):"");
                        if(mode=="v2_warm_repeat" && i==0) cache.MaterializeNativeOpenAsync(grant,m,System.Threading.CancellationToken.None,null).GetAwaiter().GetResult();
                        var watch=System.Diagnostics.Stopwatch.StartNew();
                        var item=(System.Collections.Generic.Dictionary<string,object>)((System.Collections.IList)m["items"])[0];
                        if(mode=="baseline_synced") NativePhotoshop.VerifyMasterAsync(System.IO.Path.Combine(root,"synced","Fixture.psd"),System.IO.Path.Combine(root,"synced"),System.Convert.ToInt64(item["size"]),System.Convert.ToString(item["content_hash"]),System.Threading.CancellationToken.None).GetAwaiter().GetResult();
                        else {string path=cache.MaterializeNativeOpenAsync(grant,m,System.Threading.CancellationToken.None,null).GetAwaiter().GetResult()[0];NativeFileOpening.OptionsFor(path);}
                        watch.Stop();samples.Add(watch.Elapsed.TotalMilliseconds);
                      }samples.Sort();results[mode]=new {median=samples[4],p95=samples[8]};
                    }
                    var renamed=(System.Collections.Generic.Dictionary<string,object>)((System.Collections.IList)m["items"])[0];
                    renamed["name"]="Renamed.psd";((System.Collections.Generic.Dictionary<string,object>)((System.Collections.IList)m["roots"])[0])["source_relative_path"]="Renamed.psd";
                    results["renamed_cache"]=System.IO.Path.GetFileName(new NativeCache("").MaterializeNativeOpenAsync(grant,m,System.Threading.CancellationToken.None,null).GetAwaiter().GetResult()[0]);
                    var cancelled=new System.Threading.CancellationTokenSource();cancelled.Cancel();
                    try{new NativeCache("").MaterializeNativeOpenAsync(grant,m,cancelled.Token,null).GetAwaiter().GetResult();results["cancelled"]="unexpected";}catch(System.OperationCanceledException){results["cancelled"]="cancelled";}
                    var blocked=(System.Collections.Generic.Dictionary<string,object>)((System.Collections.IList)m["items"])[0];blocked["name"]="bad.exe";((System.Collections.Generic.Dictionary<string,object>)((System.Collections.IList)m["roots"])[0])["source_relative_path"]="bad.exe";
                    try{new NativeCache("").MaterializeNativeOpenAsync(grant,m,System.Threading.CancellationToken.None,null).GetAwaiter().GetResult();results["executable"]="unexpected";}catch(DesktopException e){results["executable"]=e.Code;}
                    return ser.Serialize(results);
                  }
                }"""
                (root/'source.cs').write_text((helper/'SportsCaveFilesDesktop.cs').read_text(encoding='utf-8')+'\n'+harness,encoding='utf-8')
                script=r"""param($Root,$Origin)
                $ErrorActionPreference='Stop'
                Add-Type -AssemblyName PresentationFramework,PresentationCore,WindowsBase,System.Xaml
                $refs=@('System.dll','System.Core.dll','System.Net.Http.dll','System.Web.Extensions.dll',[System.Windows.DependencyObject].Assembly.Location,[System.Windows.Media.ImageSource].Assembly.Location,[System.Windows.Window].Assembly.Location,[System.Xaml.XamlReader].Assembly.Location,(Join-Path $Root 'Microsoft.Web.WebView2.Core.dll'),(Join-Path $Root 'Microsoft.Web.WebView2.Wpf.dll'))|Select-Object -Unique
                [void][Reflection.Assembly]::LoadFrom((Join-Path $Root 'Microsoft.Web.WebView2.Core.dll'))
                [void][Reflection.Assembly]::LoadFrom((Join-Path $Root 'Microsoft.Web.WebView2.Wpf.dll'))
                Add-Type -TypeDefinition (Get-Content -LiteralPath (Join-Path $Root 'source.cs') -Raw) -Language CSharp -ReferencedAssemblies $refs
                [NativeV2Harness]::Run($Root,$Origin,(Get-Content -LiteralPath (Join-Path $Root 'manifest.json') -Raw))
                """
                (root/'build.ps1').write_text(script)
                run=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(root/'build.ps1'),str(root),f'http://127.0.0.1:{server.server_port}'],capture_output=True,text=True,timeout=60)
                self.assertEqual(run.returncode,0,run.stderr);result=json.loads(run.stdout)
                self.assertEqual(result['version'],11);self.assertNotIn('unexpected',result['invalid']);self.assertEqual(result['executable'],'file_type_denied')
                self.assertEqual(count['downloads'],10);self.assertEqual(result['renamed_cache'],'Renamed.psd');self.assertEqual(result['cancelled'],'cancelled')
                self.assertEqual((synced/'Fixture.psd').read_bytes(),body)
                result['payload_bytes']=len(body);result['master_downloads']=count['downloads'];result['native_app_launches']=0
                (ROOT/'output').mkdir(exist_ok=True);(ROOT/'output/native_v2_windows_bench.json').write_text(json.dumps(result,indent=2))
                print('Actual Windows helper compiled/cache exercised (16 MiB fixture), no OS chooser/app launched: '+json.dumps(result))
        finally:server.shutdown();server.server_close()

