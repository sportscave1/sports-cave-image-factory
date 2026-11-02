using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Automation;

// Explicit isolated-renderer receipt contract. Never recognizes a live cloud page.
static class LocalSaveResult {
    public const string Contract="sports-cave.local-save.v1";
    public sealed class Witness { public string Path,Source; public long Written; }
    public static bool Supports(Dictionary<string,object> target) {
        return target.ContainsKey("postcondition")&&Equals(target["postcondition"],Contract)&&
            Equals(target["name"],"Save all")&&Equals(target["control_type"],"Button");
    }
    public static Witness Read(IntPtr window) {
        if(!BrowserTabs.Chromium(window))return null;
        var root=AutomationElement.FromHandle(window);
        var docs=root.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Document));
        int matched=0;
        foreach(AutomationElement doc in docs)if(Equals(doc.GetCurrentPropertyValue(ValuePattern.ValueProperty,true),"http://127.0.0.1:18964/"))matched++;
        if(matched!=1)return null;
        var texts=root.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Text));
        var paths=new List<string>();var sources=new List<string>();
        foreach(AutomationElement text in texts) {
            string name=text.Current.Name;
            if(name.StartsWith("Local save receipt: "))paths.Add(name.Substring(20));
            if(name.StartsWith("Source run: "))sources.Add(name.Substring(12));
        }
        if(paths.Count!=1||sources.Count!=1)return null;
        string path=System.IO.Path.GetFullPath(paths[0]);
        string allowed=System.IO.Path.GetFullPath(System.IO.Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"..","phase7-disk-save-longpath-20261029"))+System.IO.Path.DirectorySeparatorChar;
        Guid id;string leaf=System.IO.Path.GetFileNameWithoutExtension(path);
        if(!path.StartsWith(allowed,StringComparison.OrdinalIgnoreCase)||!leaf.StartsWith("save-receipt-")||
            !Guid.TryParseExact(leaf.Substring(13),"D",out id)||System.IO.Path.GetExtension(path)!=".json")return null;
        return new Witness{Path=path,Source=sources[0],Written=File.Exists(path)?File.GetLastWriteTimeUtc(path).Ticks:0};
    }
    public static bool Complete(string json,string source) {
        var body=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(json);
        if(!Equals(body["source_run"],source))throw new Exception("Saved source run changed.");
        var receipt=(Dictionary<string,object>)body["receipt"];
        if(receipt.ContainsKey("cancelled")&&Equals(receipt["cancelled"],true))throw new Exception("Save destination conflict. Inspect before retrying.");
        if(((IList)receipt["failures"]).Count!=0)throw new Exception("Save is incomplete. Inspect the per-file receipt before retrying.");
        var items=(IList)receipt["successes"];
        if(items.Count!=8)return false;
        var names=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach(Dictionary<string,object> item in items) {
            string name=(string)item["relative_path"];
            var metadata=(Dictionary<string,object>)item["metadata"];
            string hash=(string)metadata["content_hash"];
            if(!name.StartsWith("WEBP/")||!name.EndsWith(".webp")||name.Contains("..")||!names.Add(name)||
                Convert.ToInt64(metadata["size"])<=0||!System.Text.RegularExpressions.Regex.IsMatch(hash,"^[a-f0-9]{64}$"))
                throw new Exception("Incomplete or ambiguous saved WEBP receipt.");
        }
        return true;
    }
    public static Dictionary<string,object> CopyProof(string json,string source,string prompt) {
        if(prompt!=null)prompt=prompt.Replace("\r\n","\n"); // Windows text-file transport, like the clipboard transport.
        if(!Complete(json,source)||String.IsNullOrEmpty(prompt)||prompt.Length>ProductPromptProof.MaxBytes)
            throw new Exception("Complete local save and bounded prepared prompt required.");
        var body=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(json);
        var receipt=(Dictionary<string,object>)body["receipt"];
        if(!prompt.StartsWith("1. SELECTED ACTION AND PRODUCT CONTEXT\nUpload to Draft\n")||
            !prompt.Contains((string)receipt["save_token"]))throw new Exception("Prepared prompt does not match the saved operation.");
        foreach(Dictionary<string,object> item in (IList)receipt["successes"]) {
            var metadata=(Dictionary<string,object>)item["metadata"];
            if(!prompt.Contains((string)metadata["name"])||!prompt.Contains((string)metadata["id"]))
                throw new Exception("Prepared prompt does not bind all saved files.");
        }
        return new Dictionary<string,object>{{"sha256",CopyText.Hash(prompt)},{"utf16_length",prompt.Length},{"utf8_length",System.Text.Encoding.UTF8.GetByteCount(prompt)}};
    }
    public static Dictionary<string,object> ReadCopyProof(IntPtr window,Dictionary<string,object> target) {
        if(!Equals(target["name"],"Copy Upload Prompt")||!Equals(target["automation_id"],"copy")||
            !Equals(target["window_key"],"Sports Cave recorder save test - Google Chrome"))return null;
        var witness=Read(window);if(witness==null)return null;
        string promptPath=System.IO.Path.Combine(System.IO.Path.GetDirectoryName(witness.Path),"prepared-upload-prompt.txt");
        if(!File.Exists(witness.Path)||!File.Exists(promptPath)||File.GetLastWriteTimeUtc(promptPath).Ticks<witness.Written)
            throw new Exception("Current saved prompt is not ready. No Copy input sent.");
        return CopyProof(File.ReadAllText(witness.Path),witness.Source,File.ReadAllText(promptPath));
    }
    public static void Wait(IntPtr window,Witness before,Action check,Action heartbeat,int timeout) {
        if(before==null)throw new Exception("Prepare the isolated save receipt before clicking Save all.");
        var timer=Stopwatch.StartNew();
        while(timer.ElapsedMilliseconds<timeout) {
            check();heartbeat();
            if(Native.Root(Native.GetForegroundWindow())!=window)throw new Exception("Focus left the save window. Save was not repeated.");
            try {
                var current=Read(window);
                if(current!=null) {
                    if(current.Path!=before.Path||current.Source!=before.Source)throw new Exception("Save receipt identity changed.");
                    if(current.Written>before.Written&&Complete(File.ReadAllText(current.Path),before.Source))return;
                }
            }catch(ElementNotAvailableException){}catch(IOException){}catch(ArgumentException){} // In-progress atomic UI/file publication; observation only.
            Thread.Sleep(100);
        }
        throw new Exception("A fresh complete save receipt was not observed. Save was not repeated.");
    }
}
