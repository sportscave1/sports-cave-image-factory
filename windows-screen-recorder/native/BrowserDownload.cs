using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Collections.Generic;
using System.Diagnostics;
using System.Security.Cryptography;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Automation;

// No latest-file guesses. A new Edge download ID, exact nonce-bearing source,
// completion receipt, new destination and stable complete bytes are all required.
static class BrowserDownload {
    const string Prefix="Sports Cave download v1: ";
    static readonly JavaScriptSerializer Json=new JavaScriptSerializer();
    // Choosing a destination is human interaction, separate from network/file
    // completion. Only a verified owned Save As dialog can extend capture's
    // ordinary 30-second deadline. Neither reopening it nor late receipts reset
    // the absolute five-minute choice budget.
    public sealed class WaitBudget {
        bool sawDialog;
        long? dialogClosedAt;
        public bool Expired(long elapsed,bool ownedDialogOpen) {
            if(ownedDialogOpen&&!dialogClosedAt.HasValue)sawDialog=true;
            if(sawDialog&&!ownedDialogOpen&&!dialogClosedAt.HasValue)dialogClosedAt=elapsed;
            long deadline=!sawDialog?30000:dialogClosedAt.HasValue?Math.Min(dialogClosedAt.Value+30000,330000):300000;
            return elapsed>=deadline;
        }
    }
    public static Dictionary<string,object> Read(AutomationElement e) {
        foreach(string line in e.Current.HelpText.Split('\n'))if(line.StartsWith(Prefix)) {
            if(line.Length>3000)throw new Exception("Download metadata exceeded its bound.");
            var value=Json.Deserialize<Dictionary<string,object>>(Uri.UnescapeDataString(line.Substring(Prefix.Length)));
            Validate(value);return value;
        }
        return null;
    }
    public static void Validate(Dictionary<string,object> value) {
        Uri uri;Guid nonce;
        if(value.Count!=3||!value.ContainsKey("url")||!value.ContainsKey("filename")||!value.ContainsKey("save_as")||
           !(value["save_as"] is bool)||!Uri.TryCreate(value["url"] as string,UriKind.Absolute,out uri)||
           !((uri.Scheme=="http"&&uri.Host=="127.0.0.1"&&(uri.Port==18962||uri.Port==18963))||(uri.Scheme=="https"&&uri.Host=="sports-cave-image-factory.onrender.com"&&uri.Port==443))||uri.UserInfo!=""||uri.Fragment!=""||
           !Guid.TryParse(System.Web.HttpUtility.ParseQueryString(uri.Query)["sc_download"],out nonce))
            throw new Exception("Download source is outside the supported preview contract.");
        string name=value["filename"] as string;
        if(String.IsNullOrWhiteSpace(name)||name.Length>180||Path.GetFileName(name)!=name||name.IndexOfAny(Path.GetInvalidFileNameChars())>=0)
            throw new Exception("Download filename is not supported.");
        Capture.Safe(name);
    }
    public static bool SameSource(Dictionary<string,object> a,Dictionary<string,object> b) {
        Validate(a);Validate(b);
        var left=new UriBuilder((string)a["url"]);var right=new UriBuilder((string)b["url"]);
        var l=System.Web.HttpUtility.ParseQueryString(left.Query);var r=System.Web.HttpUtility.ParseQueryString(right.Query);
        l.Remove("sc_download");r.Remove("sc_download");left.Query=l.ToString();right.Query=r.ToString();
        return left.Uri==right.Uri&&Equals(a["filename"],b["filename"])&&Equals(a["save_as"],b["save_as"]);
    }
    public static Dictionary<string,object> CaptureWindowAnchor(Dictionary<string,object> target) {
        // All capture paths must carry the identified Save As source into the
        // window-switch observation. The owned file dialog can disable Edge
        // between source identification and that observation. This does not
        // permit invoking disabled controls: WindowAction still requires an
        // exactly owned, process-verified Save As before using metadata only.
        object raw;
        if(!target.TryGetValue("download",out raw))return null;
        var source=raw as Dictionary<string,object>;
        if(source==null)throw new Exception("Invalid download source window context.");
        Validate(source);
        if(!(bool)source["save_as"])return null;
        if(!target.TryGetValue("browser",out raw)||!(raw is Dictionary<string,object>))
            throw new Exception("Save As source is missing its verified browser identity. Draft preserved.");
        var browser=BrowserIdentity.ReadHelp("Sports Cave browser v2: "+Uri.EscapeDataString(Json.Serialize(raw)));
        if(browser==null||new Uri((string)source["url"]).GetLeftPart(UriPartial.Authority)!=new Uri((string)browser["page"]).GetLeftPart(UriPartial.Authority))
            throw new Exception("Save As source differs from its browser page. Draft preserved.");
        return browser;
    }
    public static Dictionary<string,object> WitnessDownload(Dictionary<string,object> raw,Dictionary<string,object> identity,
        Native.Point point,System.Windows.Rect bounds,uint dpi) {
        if(!raw.ContainsKey("download"))return null;
        if(raw.Count!=5||!raw.ContainsKey("pointer"))throw new Exception("Incomplete browser download witness.");
        var source=raw["download"] as Dictionary<string,object>;
        var position=raw["pointer"] as Dictionary<string,object>;
        if(source==null||position==null||position.Count!=5||new[]{"x","y","width","height","scale"}.Any(k=>!position.ContainsKey(k)))
            throw new Exception("Invalid browser download witness.");
        Validate(source);
        if(!(bool)source["save_as"]||new Uri((string)source["url"]).GetLeftPart(UriPartial.Authority)!=new Uri((string)identity["page"]).GetLeftPart(UriPartial.Authority))
            throw new Exception("Download witness source differs from its page.");
        var numbers=new[]{"x","y","width","height","scale"}.Select(k=>Convert.ToDouble(position[k])).ToArray();
        if(numbers.Any(n=>Double.IsNaN(n)||Double.IsInfinity(n))||numbers[4]<.5||numbers[4]>4||
            Math.Abs(numbers[4]-dpi/96.0)>.05||Math.Abs(numbers[2]-bounds.Width)>8||Math.Abs(numbers[3]-bounds.Height)>8||
            Math.Abs(bounds.Left+numbers[0]-point.X)>8||Math.Abs(bounds.Top+numbers[1]-point.Y)>8||!bounds.Contains(new System.Windows.Point(point.X,point.Y)))
            throw new Exception("Download witness does not match the physical click or display scale. Draft preserved.");
        return source;
    }
    public static void Persist(Dictionary<string,object> result) {
        string folder=Path.Combine(Environment.GetEnvironmentVariable("SC_RECORDER_DOWNLOAD_EVENTS"),"verified-files");
        Directory.CreateDirectory(folder);
        File.WriteAllText(Path.Combine(folder,Guid.NewGuid().ToString()+".json"),Json.Serialize(result),new UTF8Encoding(false));
    }
    public static bool OwnedSaveDialog(IntPtr hit,IntPtr browser) {
        if(browser==IntPtr.Zero||hit==IntPtr.Zero)return false;
        var dialog=Native.GetAncestor(hit,2);
        if(dialog==IntPtr.Zero||dialog==browser||Native.GetAncestor(dialog,3)!=browser)return false;
        var name=new StringBuilder(256);Native.GetClassName(dialog,name,256);
        return name.ToString()=="#32770"&&Native.Title(dialog)=="Save As";
    }
    public static void ValidateSaveDialogProcess(IntPtr dialog,IntPtr browser) {
        // Edge may host its owned file dialog in a separate process. Exact
        // ownership is mandatory; executable/session/elevation checks run on
        // the worker, never inside the input hook's bounded modal filter.
        if(!OwnedSaveDialog(dialog,browser))throw new Exception("Save As ownership changed.");
        Native.CheckProcess(browser);Native.CheckProcess(dialog);
        using(var owner=Native.ProcessFor(browser))using(var modal=Native.ProcessFor(dialog)) {
            if(!String.Equals(owner.MainModule.FileName,modal.MainModule.FileName,StringComparison.OrdinalIgnoreCase))
                throw new Exception("Save As process does not match its browser executable.");
        }
    }
    public sealed class SaveAs {
        readonly IntPtr browser;
        readonly string directory, filename;
        string destination;
        bool invoked, prepared;
        public SaveAs(IntPtr browser,string directory,string filename) {
            this.browser=browser;this.directory=Path.GetFullPath(directory);this.filename=filename;
            NewDestination(directory,filename); // Retain the folder/filename validation contract.
        }
        public static string NewDestination(string directory,string filename) {
            string full=Path.GetFullPath(directory);
            var allowed=new[]{Environment.GetEnvironmentVariable("SC_RECORDER_DOWNLOAD_DIRECTORY"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),"Downloads")};
            if(!Directory.Exists(full)||!allowed.Where(x=>!String.IsNullOrEmpty(x)).Any(x=>String.Equals(Path.GetFullPath(x).TrimEnd('\\'),full.TrimEnd('\\'),StringComparison.OrdinalIgnoreCase)))
                throw new Exception("Save As destination is not an approved local download folder.");
            if(String.IsNullOrWhiteSpace(filename)||Path.GetFileName(filename)!=filename||filename.IndexOfAny(Path.GetInvalidFileNameChars())>=0)
                throw new Exception("Save As filename is invalid.");
            return Path.Combine(full,Path.GetFileNameWithoutExtension(filename)+"-"+Guid.NewGuid().ToString("N")+Path.GetExtension(filename));
        }
        public static string SuggestedDestination(string directory,string filename,string shown) {
            NewDestination(directory,filename);
            if(String.IsNullOrWhiteSpace(shown)||shown!=Path.GetFileName(shown)||shown.IndexOfAny(Path.GetInvalidFileNameChars())>=0)
                throw new Exception("Save As proposed an unsupported filename. Nothing saved.");
            string extension=Path.GetExtension(filename);
            // The shell may hide a known extension in its filename field.
            if(Path.GetExtension(shown)=="")shown+=extension;
            if(!ExpectedFilename(filename,shown))throw new Exception("Save As proposed a different file. Nothing saved.");
            string result=Path.Combine(Path.GetFullPath(directory),shown);
            if(File.Exists(result))throw new Exception("Save As proposed an existing destination. Nothing overwritten.");
            return result;
        }
        static bool ExpectedFilename(string expected,string name) {
            string pattern="^"+System.Text.RegularExpressions.Regex.Escape(Path.GetFileNameWithoutExtension(expected))+
                @"(?: \([1-9][0-9]*\))?"+System.Text.RegularExpressions.Regex.Escape(Path.GetExtension(expected))+"$";
            return System.Text.RegularExpressions.Regex.IsMatch(name,pattern,System.Text.RegularExpressions.RegexOptions.IgnoreCase);
        }
        public void Poll(Action check) {
            if(invoked)return;
            check();var matches=new List<IntPtr>();
            Native.EnumWindows((h,l)=>{if(Native.IsWindowVisible(h)&&OwnedSaveDialog(h,browser))matches.Add(h);return true;},IntPtr.Zero);
            if(matches.Count==0)return;
            if(matches.Count!=1)throw new Exception("More than one owned Save As dialog is open. No target guessed.");
            var dialog=matches[0];ValidateSaveDialogProcess(dialog,browser);
            if(Native.GetAncestor(Native.GetForegroundWindow(),2)!=dialog)throw new Exception("Save As lost focus. No filename entered.");
            var root=AutomationElement.FromHandle(dialog);
            var fields=root.FindAll(TreeScope.Descendants,new AndCondition(new PropertyCondition(AutomationElement.AutomationIdProperty,"1001"),new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Edit)));
            var saves=root.FindAll(TreeScope.Descendants,new AndCondition(new PropertyCondition(AutomationElement.AutomationIdProperty,"1"),new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Button)));
            if(fields.Count!=1||saves.Count!=1||fields[0].Current.IsPassword||fields[0].Current.Name!="File name:"||saves[0].Current.Name!="Save")
                throw new Exception("Unsupported Save As controls. No filename entered.");
            object value,invoke;
            if(!fields[0].TryGetCurrentPattern(ValuePattern.Pattern,out value)||!saves[0].TryGetCurrentPattern(InvokePattern.Pattern,out invoke))
                throw new Exception("Save As controls do not expose supported patterns.");
            check();string proposed=SuggestedDestination(directory,filename,((ValuePattern)value).Current.Value);
            if(!prepared) {
                // The recording stores its folder and source filename, not an
                // artificial GUID rename. Keep Edge's new, uniquified proposal.
                // A filename edit's UIA readback did not prove shell commitment.
                destination=proposed;prepared=true;return;
            }
            check();if(proposed!=destination||!OwnedSaveDialog(dialog,browser)||Native.GetAncestor(Native.GetForegroundWindow(),2)!=dialog)
                throw new Exception("Save As destination or owning dialog changed. Nothing saved.");
            // Mark before invoking: an uncertain Save must never be repeated.
            invoked=true;((InvokePattern)invoke).Invoke();
        }
        // Called only after Session.Wait has independently verified a new current-run
        // receipt, source nonce, complete file identity and stable contents.
        public bool MatchesVerifiedResult(string path) {
            path=Path.GetFullPath(path);
            if(invoked)return String.Equals(path,destination,StringComparison.OrdinalIgnoreCase);
            if(!String.Equals(Path.GetDirectoryName(path),directory,StringComparison.OrdinalIgnoreCase))return false;
            return ExpectedFilename(filename,Path.GetFileName(path));
        }
        public bool Invoked {get{return invoked;}}
        public bool Prepared {get{return prepared;}}
        public string Destination {get{return destination;}}
    }
    public sealed class Session {
        readonly string events,session;
        readonly string[] roots;
        readonly HashSet<string> existing=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        readonly DateTime armed=DateTime.UtcNow;
        public Session() {
            events=Environment.GetEnvironmentVariable("SC_RECORDER_DOWNLOAD_EVENTS");
            session=Environment.GetEnvironmentVariable("SC_RECORDER_DOWNLOAD_SESSION");
            roots=new[]{Environment.GetEnvironmentVariable("SC_RECORDER_DOWNLOAD_DIRECTORY"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),"Downloads")}
                .Where(x=>!String.IsNullOrEmpty(x)&&Directory.Exists(x)).Select(Path.GetFullPath).Distinct().ToArray();
            foreach(string root in roots)foreach(string path in Directory.EnumerateFiles(root,"*",SearchOption.TopDirectoryOnly))existing.Add(path);
        }
        public Dictionary<string,object> Wait(Dictionary<string,object> source,DateTime clicked,Action check,Action tick=null,Func<bool> ownedSaveDialogOpen=null) {
            Validate(source);
            if(String.IsNullOrEmpty(events)||!Directory.Exists(events))throw new Exception("The local Edge download receipt bridge is unavailable. Draft preserved.");
            var watch=Stopwatch.StartNew();var budget=new WaitBudget();string id=null;Dictionary<string,object> complete=null;
            while(true) {
                check();if(tick!=null)tick();
                bool choosing=(bool)source["save_as"]&&ownedSaveDialogOpen!=null&&ownedSaveDialogOpen();
                if(budget.Expired(watch.ElapsedMilliseconds,choosing))throw new Exception(choosing?
                    "Save As was not completed within five minutes. Draft preserved; no file substituted.":
                    "Download completion deadline exceeded. No older file substituted.");
                var files=Directory.GetFiles(events,"*.json");
                if(files.Length>4096)throw new Exception("Download receipt limit reached. Start a new candidate session.");
                foreach(string file in files) {
                    var item=Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(file));
                    if(!Equals(item["session"],session)||!Equals(item["url"],source["url"]))continue;
                    DateTime started;
                    if(!DateTime.TryParse(item["started"] as string,out started)||started.ToUniversalTime()<clicked.ToUniversalTime().AddMilliseconds(-100))continue;
                    string current=item["id"] as string;
                    if(id!=null&&id!=current)throw new Exception("More than one download matched the action. No file guessed.");
                    id=current;
                    if(Equals(item["state"],"interrupted"))throw new Exception("Download cancelled or interrupted. No file reference retained.");
                    if(Equals(item["state"],"complete"))complete=item;
                }
                if(complete!=null) {
                    if(!Equals(complete["final_url"],source["url"]))throw new Exception("Download redirected away from its verified source.");
                    string path=Path.GetFullPath((string)complete["filename"]);
                    if(!roots.Any(root=>String.Equals(Path.GetDirectoryName(path),root,StringComparison.OrdinalIgnoreCase))||existing.Contains(path)||
                       !File.Exists(path)||new[]{".crdownload",".part",".tmp"}.Contains(Path.GetExtension(path).ToLowerInvariant()))
                        throw new Exception("Download is not a new completed file in a supported destination.");
                    var before=new FileInfo(path);long length=before.Length;DateTime modified=before.LastWriteTimeUtc;
                    if(before.CreationTimeUtc<armed.AddSeconds(-1)||length!=Convert.ToInt64(complete["bytes"]))
                        throw new Exception("Download bytes or file identity do not match the current browser receipt.");
                    string hash;using(var stream=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.Read))
                    using(var sha=SHA256.Create())hash=BitConverter.ToString(sha.ComputeHash(stream)).Replace("-","").ToLowerInvariant();
                    before.Refresh();if(before.Length!=length||before.LastWriteTimeUtc!=modified)throw new Exception("Download changed while verifying completion.");
                    existing.Add(path);
                    return new Dictionary<string,object>{{"path",path},{"bytes",length},{"sha256",hash},{"download_id",id}};
                }
                Thread.Sleep(50);
            }
        }
    }
}
