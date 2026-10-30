using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Automation;

// An attempted request is never automatically retried, including after a crash.
static class ChatSubmission {
    public static string Digest(string text) {
        using(var hash=SHA256.Create())return BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(text.Replace("\r\n","\n")))).Replace("-","").ToLowerInvariant();
    }
    public static bool Conversation(string page) {
        return page!=null&&Regex.IsMatch(page,@"^https://chatgpt\.com/(?:g/g-p-6a387a17627081918e1700ec2783a12b(?:-sc-mockups-uploads)?/)?c/[a-f0-9-]{36}$");
    }
    public static bool Acknowledged(string profile,string expectedProfile,string page,int userMessages,bool started) {
        return profile==expectedProfile&&Conversation(page)&&userMessages==1&&started;
    }
    public static bool Supports(Dictionary<string,object> target) {
        object raw;
        if(!Equals(target["control_type"],"Button")||!Equals(target["name"],"Send")||
            !WindowIdentity.ChromiumApp((string)target["app"])||!target.TryGetValue("browser",out raw))return false;
        var b=(Dictionary<string,object>)raw;
        return Equals(b["page"],ChatImageAttachment.Page)&&Equals(b["frame"],"top")&&Equals(b["control"],"label:button:Send");
    }
    public static string Begin(string directory,Dictionary<string,object> request,string profile) {
        Guid id;if(!Guid.TryParseExact((string)request["request_id"],"D",out id))throw new Exception("Invalid submission identity.");
        Directory.CreateDirectory(directory);
        string path=Path.Combine(directory,id.ToString("D")+".json");
        byte[] data=Encoding.UTF8.GetBytes(new JavaScriptSerializer().Serialize(new {state="attempted",request=request,profile=profile,utc=DateTime.UtcNow.ToString("o")}));
        try {using(var file=new FileStream(path,FileMode.CreateNew,FileAccess.Write,FileShare.Read)){file.Write(data,0,data.Length);file.Flush(true);}}
        catch(IOException){throw new Exception("This request already has an attempt receipt, or its receipt could not be persisted. Send was not repeated.");}
        return path;
    }
    public static string ReceiptDirectory {
        get{return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"SportsCaveRecorder","submission-receipts-v1");}
    }
    public static AutomationElement Editor(IntPtr window) {
        var all=AutomationElement.FromHandle(window).FindAll(TreeScope.Descendants,new AndCondition(
            new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Edit),new PropertyCondition(AutomationElement.NameProperty,ChatImageAttachment.EditorName)));
        AutomationElement result=null;
        foreach(AutomationElement e in all)if(!e.Current.IsOffscreen){if(result!=null)throw new Exception("Submission composer is ambiguous.");result=e;}
        if(result==null)throw new Exception("The prepared project composer is unavailable.");
        return result;
    }
    public static string Preflight(IntPtr window,AutomationElement send,Dictionary<string,object> target) {
        if(!Supports(target)||!send.Current.IsEnabled||!BrowserIdentity.SamePage(BrowserIdentity.Current(window),(Dictionary<string,object>)target["browser"]))
            throw new Exception("Submission requires the exact prepared project and enabled Send control.");
        var editor=Editor(window);
        if(!ChatImageAttachment.Inspect(editor,false))throw new Exception("Submission requires exactly one completed image and no pending attachment.");
        string text=RunTransfer.ReadEditor(editor,false).Replace("\r\n","\n");
        if(!text.StartsWith("READ FIRST — COMPLETE MOCKUP REQUIREMENTS",StringComparison.Ordinal)||
            !text.Contains("DOWNLOADABLE OUTPUT MANIFEST")||!text.Contains("mockup-outputs.csv"))
            throw new Exception("The complete prepared mockup/CSV request is not present. Nothing sent.");
        return text;
    }
    public static Dictionary<string,object> Execute(IntPtr window,AutomationElement send,Dictionary<string,object> target,
        Dictionary<string,object> request,Action check,Action heartbeat,Action attempted,int timeout) {
        check();string text=Preflight(window,send,target);
        if(!Equals(request["sha256"],Digest(text))||Convert.ToInt32(request["characters"])!=text.Length)
            throw new Exception("Prepared request changed. Nothing sent.");
        object pattern;if(!send.TryGetCurrentPattern(InvokePattern.Pattern,out pattern))throw new Exception("Send does not expose a supported invocation.");
        check();string profile=(string)((Dictionary<string,object>)target["browser"])["profile"];
        string receipt=Begin(ReceiptDirectory,request,profile);
        attempted();check();((InvokePattern)pattern).Invoke(); // Exactly once. Exceptions preserve the attempt receipt.
        return Observe(window,request,profile,receipt,check,heartbeat,timeout);
    }
    public static void SaveAcknowledgement(string path,Dictionary<string,object> result) {
        var json=new JavaScriptSerializer();
        if(File.Exists(path)) {
            var prior=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(path));
            foreach(string key in new[]{"request_id","conversation","profile","acknowledged","generation_started"})
                if(!prior.ContainsKey(key)||!Equals(prior[key],result[key]))throw new Exception("Existing acknowledgement does not match this conversation.");
            return;
        }
        using(var file=new FileStream(path,FileMode.CreateNew,FileAccess.Write,FileShare.Read)) {
            var data=Encoding.UTF8.GetBytes(json.Serialize(result));file.Write(data,0,data.Length);file.Flush(true);
        }
    }
    public static Dictionary<string,object> Observe(IntPtr window,Dictionary<string,object> request,string profile,string receipt,Action check,Action heartbeat,int timeout) {
        if(!File.Exists(receipt))throw new Exception("No durable attempt receipt; acknowledgement cannot be inferred.");
        var timer=Stopwatch.StartNew();
        while(timer.ElapsedMilliseconds<timeout) {
            check();heartbeat();
            var current=BrowserIdentity.Current(window);
            if(current!=null&&Conversation((string)current["page"])) {
                int users=0;bool started=false;
                var root=AutomationElement.FromHandle(window);
                var nodes=root.FindAll(TreeScope.Descendants,new OrCondition(
                    new PropertyCondition(AutomationElement.NameProperty,"You said:"),
                    new PropertyCondition(AutomationElement.NameProperty,"ChatGPT said:"),
                    new PropertyCondition(AutomationElement.NameProperty,"Latest response"),
                    new PropertyCondition(AutomationElement.NameProperty,"Stop streaming"),
                    new PropertyCondition(AutomationElement.NameProperty,"Stop")));
                foreach(AutomationElement node in nodes) {
                    if(node.Current.Name=="You said:")users++;
                    if(node.Current.Name=="ChatGPT said:"||node.Current.Name=="Latest response"||node.Current.ControlType==ControlType.Button)started=true;
                }
                if(Acknowledged((string)current["profile"],profile,(string)current["page"],users,started)) {
                    var result=new Dictionary<string,object>{{"request_id",request["request_id"]},{"conversation",current["page"]},{"profile",profile},{"acknowledged",true},{"generation_started",true}};
                    // Keep the immutable attempt and write a separate acknowledgement.
                    SaveAcknowledgement(receipt+".ack",result);
                    return result;
                }
            }
            Thread.Sleep(150);
        }
        throw new Exception("Submission acknowledgement is uncertain. Attempt receipt retained; Send will not be repeated.");
    }
}
