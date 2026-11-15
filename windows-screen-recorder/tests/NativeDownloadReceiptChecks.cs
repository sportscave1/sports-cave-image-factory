using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Web.Script.Serialization;

// Exercises the native verifier used by the candidate, without Edge, input,
// the live receipt bridge, clipboard contents, or existing download files.
class NativeDownloadReceiptChecks {
    static int checks;
    static readonly string[] Keys={"SC_RECORDER_DOWNLOAD_EVENTS","SC_RECORDER_DOWNLOAD_SESSION","SC_RECORDER_DOWNLOAD_DIRECTORY"};
    sealed class Fixture : IDisposable {
        public readonly string Root=Path.Combine(Path.GetTempPath(),"recorder-receipt-"+Guid.NewGuid().ToString("N"));
        readonly string[] before=new string[3];
        public readonly Dictionary<string,object> Source;
        public readonly DateTime Clicked=DateTime.UtcNow;
        public readonly BrowserDownload.Session Session;
        public readonly byte[] Body=Encoding.UTF8.GetBytes("Current run\r\nUnicode \u5c71 \ud83e\udd98\ncomplete value");
        public string Events {get{return Path.Combine(Root,"events");}}
        public Fixture() {
            Directory.CreateDirectory(Events);
            for(int i=0;i<Keys.Length;i++)before[i]=Environment.GetEnvironmentVariable(Keys[i]);
            Environment.SetEnvironmentVariable(Keys[0],Events);
            Environment.SetEnvironmentVariable(Keys[1],"isolated-receipt-check");
            Environment.SetEnvironmentVariable(Keys[2],Root);
            File.WriteAllText(Path.Combine(Root,"sample.txt"),"existing file stays untouched");
            Source=new Dictionary<string,object>{{"url","http://127.0.0.1:18963/sample.txt?sc_download="+Guid.NewGuid()},{"filename","sample.txt"},{"save_as",true}};
            Session=new BrowserDownload.Session();
        }
        public Dictionary<string,object> Receipt(string id="new-id",string filename="sample (1).txt") {
            string path=Path.Combine(Root,filename);File.WriteAllBytes(path,Body);
            return new Dictionary<string,object>{{"session","isolated-receipt-check"},{"url",Source["url"]},{"final_url",Source["url"]},
                {"started",Clicked.ToString("o")},{"id",id},{"state","complete"},{"filename",path},{"bytes",Body.Length}};
        }
        public void Write(Dictionary<string,object> receipt) {
            File.WriteAllText(Path.Combine(Events,Guid.NewGuid()+".json"),new JavaScriptSerializer().Serialize(receipt));
        }
        public Dictionary<string,object> Wait() {
            var timer=Stopwatch.StartNew();
            return Session.Wait(Source,Clicked,()=>{if(timer.ElapsedMilliseconds>1000)throw new Exception("test wait cancelled");});
        }
        public void Dispose() {
            for(int i=0;i<Keys.Length;i++)Environment.SetEnvironmentVariable(Keys[i],before[i]);
            string resolved=Path.GetFullPath(Root),parent=Path.GetFullPath(Path.GetTempPath());
            if(!resolved.StartsWith(parent,StringComparison.OrdinalIgnoreCase)||!Path.GetFileName(resolved).StartsWith("recorder-receipt-"))throw new Exception("Invalid isolated fixture cleanup path");
            Directory.Delete(resolved,true);
        }
    }
    static void Require(bool condition,string name) {if(!condition)throw new Exception(name);}
    static void Rejected(Action action,string reason) {
        try {action();}catch(Exception error){Require(error.Message.Contains(reason),"Unexpected rejection: "+error.Message);checks++;return;}
        throw new Exception("Unsafe receipt accepted: "+reason);
    }
    static int Main() {
        using(var f=new Fixture()) {
            var receipt=f.Receipt();f.Write(receipt);var result=f.Wait();string hash;
            using(var sha=SHA256.Create())hash=BitConverter.ToString(sha.ComputeHash(f.Body)).Replace("-","").ToLowerInvariant();
            Require(Equals(result["path"],receipt["filename"])&&Equals(result["download_id"],"new-id")&&Convert.ToInt64(result["bytes"])==f.Body.Length&&Equals(result["sha256"],hash),"New exact receipt/file/hash mismatch");
            Require(File.ReadAllText(Path.Combine(f.Root,"sample.txt"))=="existing file stays untouched","Older duplicate filename changed");checks++;
        }
        using(var f=new Fixture()) {var r=f.Receipt();r["filename"]=Path.Combine(f.Root,"sample.txt");f.Write(r);Rejected(()=>f.Wait(),"not a new completed file");}
        using(var f=new Fixture()) {var r=f.Receipt();r["bytes"]=f.Body.Length+1;f.Write(r);Rejected(()=>f.Wait(),"bytes or file identity");}
        using(var f=new Fixture()) {var r=f.Receipt(filename:"sample.crdownload");f.Write(r);Rejected(()=>f.Wait(),"not a new completed file");}
        using(var f=new Fixture()) {var r=f.Receipt();r["final_url"]="http://127.0.0.1:18963/different";f.Write(r);Rejected(()=>f.Wait(),"redirected");}
        using(var f=new Fixture()) {f.Write(f.Receipt("one","one.txt"));f.Write(f.Receipt("two","two.txt"));Rejected(()=>f.Wait(),"More than one download");}
        using(var f=new Fixture()) {var r=f.Receipt();r["state"]="interrupted";f.Write(r);Rejected(()=>f.Wait(),"cancelled or interrupted");}
        using(var f=new Fixture()) {var r=f.Receipt();r["session"]="previous-session";f.Write(r);Rejected(()=>f.Wait(),"test wait cancelled");}
        using(var f=new Fixture()) {var r=f.Receipt();r["started"]=f.Clicked.AddMinutes(-1).ToString("o");f.Write(r);Rejected(()=>f.Wait(),"test wait cancelled");}
        using(var f=new Fixture()) {f.Write(f.Receipt());Rejected(()=>f.Session.Wait(f.Source,f.Clicked,()=>{throw new Exception("Stop requested");}),"Stop requested");}
        using(var f=new Fixture()) {Environment.SetEnvironmentVariable(Keys[0],Path.Combine(f.Root,"missing"));var absent=new BrowserDownload.Session();Rejected(()=>absent.Wait(f.Source,f.Clicked,()=>{}),"receipt bridge is unavailable");}
        Console.WriteLine("PASS "+checks+" native receipt/file/cancellation guards; isolated synthetic receipts, no browser or desktop input.");return 0;
    }
}
