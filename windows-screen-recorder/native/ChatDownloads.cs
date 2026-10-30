using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Automation;

// Retained-response downloads: each selected UI image is bound to previously
// inspected original bytes, not to series order or the newest Downloads file.
static class ChatDownloads {
    [ThreadStatic] public static string Stage;
    public static bool CollisionName(string source,string actual) {
        return SafeName(source)&&SafeName(actual)&&Regex.IsMatch(actual,"^"+Regex.Escape(Path.GetFileNameWithoutExtension(source))+@"(?: \([1-9][0-9]*\))?"+Regex.Escape(Path.GetExtension(source))+"$",RegexOptions.IgnoreCase);
    }
    static bool SafeName(string s){return !String.IsNullOrEmpty(s)&&s.Length<=180&&Path.GetFileName(s)==s&&s.IndexOfAny(Path.GetInvalidFileNameChars())<0&&!s.EndsWith(".")&&!s.EndsWith(" ");}
    static string Hash(byte[] bytes){using(var h=SHA256.Create())return BitConverter.ToString(h.ComputeHash(bytes)).Replace("-","").ToLowerInvariant();}
    public static void Validate(Dictionary<string,object> value) {
        Guid id;if(!Guid.TryParseExact((string)value["request_id"],"D",out id)||!ChatSubmission.Conversation((string)value["conversation"]))throw new Exception("Invalid retained response.");
        string directory=(string)value["directory"];
        if(!Path.IsPathRooted(directory)||!Directory.Exists(directory)||directory.Split('\\','/').Contains(".."))throw new Exception("Prepare the explicit Downloads folder.");
        var roles=new HashSet<string>();var hashes=new HashSet<string>();var titles=new HashSet<string>();var indexes=new HashSet<int>();
        var items=(IList)value["images"];
        if(items.Count!=3)throw new Exception("Exactly three witnessed image bindings required.");
        foreach(Dictionary<string,object> item in items) {
            string role=(string)item["role"],title=(string)item["title"],name=(string)item["filename"],hash=(string)item["sha256"];int index=Convert.ToInt32(item["index"]);
            if(!new[]{"Man Cave","Office","Living Room"}.Contains(role)||!roles.Add(role)||index<1||index>3||!indexes.Add(index)||
                String.IsNullOrWhiteSpace(title)||title.Length>180||!titles.Add(title)||!SafeName(name)||!name.EndsWith(".png",StringComparison.OrdinalIgnoreCase)||
                !Regex.IsMatch(hash,"^[a-f0-9]{64}$")||!hashes.Add(hash))throw new Exception("Incomplete or ambiguous image binding.");
        }
        if(!Regex.IsMatch((string)value["csv_sha256"],"^[a-f0-9]{64}$"))throw new Exception("Original CSV digest required.");
    }
    static AutomationElement One(AutomationElement root,ControlType type,string name,bool visible=true){return ChatOutputs.One(root,type,name,visible);}
    static void Invoke(AutomationElement node,Action check){ChatOutputs.Invoke(node,check);}
    static AutomationElement Await(Func<AutomationElement> find,Action check) {
        var timer=Stopwatch.StartNew();while(timer.ElapsedMilliseconds<8000){check();var node=find();if(node!=null)return node;Thread.Sleep(100);}throw new Exception("Expected gallery control was not ready.");
    }
    public static string NewCompleted(string directory,string filename,string digest,HashSet<string> before) {
        var matching=Directory.GetFiles(directory).Where(p=>!before.Contains(p)&&CollisionName(filename,Path.GetFileName(p))).ToArray();
        if(matching.Length>1)throw new Exception("Concurrent matching downloads are ambiguous. No newest file guessed.");
        if(matching.Length==0)return null;
        string path=matching[0];
        if(File.Exists(path+".crdownload"))return null;
        try {
            byte[] bytes;using(var file=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.Read)) {
                if(file.Length<1||file.Length>50*1024*1024)throw new Exception("Downloaded file size is invalid.");
                bytes=new byte[(int)file.Length];int offset=0;while(offset<bytes.Length){int n=file.Read(bytes,offset,bytes.Length-offset);if(n==0)return null;offset+=n;}
            }
            if(Hash(bytes)!=digest)throw new Exception("Downloaded bytes differ from the witnessed original. Mapping refused.");
            if(filename.EndsWith(".png",StringComparison.OrdinalIgnoreCase))using(var memory=new MemoryStream(bytes))using(var image=System.Drawing.Image.FromStream(memory,true,true)){
                if(image.Width<1||image.Height<1)throw new Exception("Invalid downloaded image.");
            }
            return path;
        }catch(IOException){return null;}
    }
    static string Download(IntPtr window,AutomationElement button,string directory,string name,string digest,Action check,bool gallery) {
        var before=new HashSet<string>(Directory.GetFiles(directory),StringComparer.OrdinalIgnoreCase);
        object action;check();
        if(button==null||!button.Current.IsEnabled)throw new Exception("The selected image download control is unavailable.");
        if(button.TryGetCurrentPattern(InvokePattern.Pattern,out action))((InvokePattern)action).Invoke();
        else if(gallery&&button.TryGetCurrentPattern(ExpandCollapsePattern.Pattern,out action))((ExpandCollapsePattern)action).Expand();
        else throw new Exception("The download control exposes neither Invoke nor Expand.");
        bool menuInvoked=false;var timer=Stopwatch.StartNew();string prior=null;int stable=0;
        while(timer.ElapsedMilliseconds<30000) {
            check();
            if(gallery&&!menuInvoked) {
                var menu=One(AutomationElement.FromHandle(window),ControlType.Menu,"Download");
                var item=menu==null?null:One(menu,ControlType.MenuItem,"Download image");
                if(item!=null){Invoke(item,check);menuInvoked=true;}
            }
            string path=NewCompleted(directory,name,digest,before);
            stable=path!=null&&path==prior?stable+1:0;prior=path;
            if(stable>=2)return path;
            Thread.Sleep(200);
        }
        throw new Exception("Download did not complete with the expected original bytes. No click was retried.");
    }
    public static Dictionary<string,object> Run(IntPtr window,Dictionary<string,object> value,Action check,Action heartbeat) {
        Stage="preflight";
        Validate(value);string id=(string)value["request_id"],page=(string)value["conversation"],directory=(string)value["directory"];
        var json=new JavaScriptSerializer();
        var ack=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(ChatSubmission.ReceiptDirectory,id+".json.ack")));
        if(!Equals(ack["request_id"],id)||!Equals(ack["conversation"],page)||!Equals(ack["acknowledged"],true))throw new Exception("Download response is not acknowledged.");
        Action verify=()=>{check();heartbeat();if(Native.Root(Native.GetForegroundWindow())!=window)throw new Exception("Download window focus changed.");
            Dictionary<string,object> current=null;var readiness=Stopwatch.StartNew();
            do {check();heartbeat();if(Native.Root(Native.GetForegroundWindow())!=window)throw new Exception("Download window focus changed.");
                current=BrowserIdentity.Current(window);
                if(current==null){var modal=One(AutomationElement.FromHandle(window),ControlType.Window,"Image preview");var anchor=modal==null?null:One(modal,ControlType.Button,"Generated image 2");if(anchor!=null)current=BrowserIdentity.Read(anchor);}
                if(current!=null)break;Thread.Sleep(100);
            }while(readiness.ElapsedMilliseconds<3000);
            if(current==null||!Equals(current["page"],page)||!Equals(current["profile"],ack["profile"]))throw new Exception("Download conversation changed.");};
        verify();Stage="open_gallery";var root=AutomationElement.FromHandle(window);
        var preview=One(root,ControlType.Window,"Image preview");
        if(preview==null){Invoke(One(root,ControlType.Button,"Generated image 1"),verify);preview=Await(()=>One(root,ControlType.Window,"Image preview"),verify);}
        var outputs=new List<Dictionary<string,object>>();
        foreach(Dictionary<string,object> item in (IList)value["images"]) {
            int index=Convert.ToInt32(item["index"]);
            Stage="select_image_"+index;
            Invoke(Await(()=>One(preview,ControlType.Button,"Generated image "+index),verify),verify);
            Await(()=>One(preview,ControlType.Button,"File actions for "+(string)item["title"]),verify);
            Await(()=>One(preview,ControlType.Image,"Generated image "+index),verify);
            Stage="download_image_"+index;
            string path=Download(window,Await(()=>One(preview,ControlType.Button,"Download"),verify),directory,(string)item["filename"],(string)item["sha256"],verify,true);
            outputs.Add(new Dictionary<string,object>{{"role",item["role"]},{"title",item["title"]},{"source_filename",item["filename"]},{"path",path},{"sha256",item["sha256"]}});
        }
        Stage="close_gallery";Invoke(One(preview,ControlType.Button,"Close viewer"),verify);
        Await(()=>BrowserIdentity.Current(window)==null?null:root,verify);
        // Original manifest is retained, not rewritten in place. UIA Invoke on
        // the exact response download supports offscreen response attachments.
        Stage="download_csv";string csv=Download(window,One(root,ControlType.Button,"Download file",false),directory,"mockup-outputs.csv",(string)value["csv_sha256"],verify,false);
        string runId=Guid.NewGuid().ToString("D");
        var receipt=new Dictionary<string,object>{{"request_id",id},{"conversation",page},{"run_id",runId},{"images",outputs},{"original_csv",csv},{"original_csv_sha256",value["csv_sha256"]},{"mapping_basis","response role context + selected gallery title + verified original SHA256; original CSV aliases retained separately"}};
        string destination=Path.Combine(ChatSubmission.ReceiptDirectory,id+".downloads-"+runId+".json");
        File.WriteAllText(destination,json.Serialize(receipt));receipt["receipt_path"]=destination;
        return receipt;
    }
}
