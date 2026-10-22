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
           uri.Scheme!="http"||uri.Host!="127.0.0.1"||(uri.Port!=18962&&uri.Port!=18963)||uri.UserInfo!=""||uri.Fragment!=""||
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
    public static void Persist(Dictionary<string,object> result) {
        string folder=Path.Combine(Environment.GetEnvironmentVariable("SC_RECORDER_DOWNLOAD_EVENTS"),"verified-files");
        Directory.CreateDirectory(folder);
        File.WriteAllText(Path.Combine(folder,Guid.NewGuid().ToString()+".json"),Json.Serialize(result),new UTF8Encoding(false));
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
        public Dictionary<string,object> Wait(Dictionary<string,object> source,DateTime clicked,Action check,Action tick=null) {
            Validate(source);
            if(String.IsNullOrEmpty(events)||!Directory.Exists(events))throw new Exception("The local Edge download receipt bridge is unavailable. Draft preserved.");
            var watch=Stopwatch.StartNew();string id=null;Dictionary<string,object> complete=null;
            while(watch.ElapsedMilliseconds<30000) {
                check();if(tick!=null)tick();
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
            throw new Exception("Download completion deadline exceeded. No older file substituted.");
        }
    }
}
