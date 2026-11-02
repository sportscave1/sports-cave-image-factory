using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Automation;

// Isolated simulator acceptance only. Never admits ChatGPT or a cloud store.
static class LocalFollowupResult {
    public const string Page="http://127.0.0.1:18963/chat";
    public const string Conversation="6ae2d62d-1338-83ec-8619-6ea3635a7fa0";
    public static bool Supports(Dictionary<string,object> target) {
        object raw;
        if(!Equals(target["control_type"],"Button")||!Equals(target["automation_id"],"send")||
            !Equals(target["name"],"Submit once to local simulator")||!target.TryGetValue("browser",out raw))return false;
        var b=(Dictionary<string,object>)raw;
        return Equals(b["page"],Page)&&Equals(b["frame"],"top")&&Equals(b["control"],"id:send");
    }
    static AutomationElement Unique(IntPtr window,string id) {
        var all=AutomationElement.FromHandle(window).FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.AutomationIdProperty,id));
        if(all.Count!=1||all[0].Current.IsOffscreen)throw new Exception("Local follow-up control unavailable or ambiguous.");
        return all[0];
    }
    public static string ExpectedPrompt() {
        string path=Path.GetFullPath(Path.Combine(Path.GetDirectoryName(typeof(LocalFollowupResult).Assembly.Location),"..","phase7-saved-replay-pass-20261029","prompt.txt"));
        string prompt=File.ReadAllText(path).Replace("\r\n","\n");
        if(prompt.Length>1048576||!prompt.StartsWith("1. SELECTED ACTION AND PRODUCT CONTEXT\nUpload to Draft\n",StringComparison.Ordinal))
            throw new Exception("Retained local Draft prompt is unavailable.");
        return prompt;
    }
    public static void Prepare(IntPtr window,Dictionary<string,object> target,Action check,int timeout) {
        if(!Supports(target)||!BrowserIdentity.SamePage(BrowserIdentity.Current(window),(Dictionary<string,object>)target["browser"]))
            throw new Exception("Local follow-up scope changed. Nothing sent.");
        string prompt=ExpectedPrompt();var editor=Unique(window,"prompt");object raw;
        if(!editor.TryGetCurrentPattern(ValuePattern.Pattern,out raw))throw new Exception("Local composer lacks verified value support.");
        var value=(ValuePattern)raw;string before=RunTransfer.ReadEditor(editor,false,false,true).Replace("\r\n","\n");
        if(before!=""&&before!=prompt)throw new Exception("Local composer contains a different prompt. Nothing overwritten.");
        if(before==""){check();value.SetValue(prompt);}
        var timer=Stopwatch.StartNew();
        while(timer.ElapsedMilliseconds<timeout){
            check();
            if(!BrowserIdentity.SamePage(BrowserIdentity.Current(window),(Dictionary<string,object>)target["browser"]))throw new Exception("Local conversation changed. Nothing sent.");
            // Chromium can acknowledge SetValue before UIA exposes the new value.
            // Observe the fresh editor; never issue a second replacement or Send.
            string current=RunTransfer.ReadEditor(Unique(window,"prompt"),false,false,true);
            if(RunTransfer.SameEditorText(current,prompt)&&Unique(window,"send").Current.IsEnabled)return;
            Thread.Sleep(50);
        }
        throw new Exception("Local follow-up readiness not verified. Nothing sent.");
    }
    public static bool ValidResult(string json,string prompt) {
        try {
            var result=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(json);
            return Equals(result["conversation"],Conversation)&&Equals(result["prompt_sha256"],ChatSubmission.Digest(prompt))&&
                Equals(result["state"],"completed")&&Equals(result["simulated"],true)&&Convert.ToInt32(result["submissions"])==1&&
                Equals(result["psd_attached"],false)&&Convert.ToInt32(result["edition_changes"])==0&&Convert.ToInt32(result["production_jobs"])==0&&
                Equals(result["business_outcome"],"SIMULATED ONLY — no Shopify product created");
        }catch{return false;}
    }
    public static void Wait(IntPtr window,Dictionary<string,object> target,Action check,int timeout) {
        string prompt=ExpectedPrompt();var timer=Stopwatch.StartNew();
        while(timer.ElapsedMilliseconds<timeout){
            check();
            if(!BrowserIdentity.SamePage(BrowserIdentity.Current(window),(Dictionary<string,object>)target["browser"]))throw new Exception("Local conversation changed after submission. Inspect before retrying.");
            var result=Unique(window,"result");object raw;string text;
            if(result.TryGetCurrentPattern(ValuePattern.Pattern,out raw))text=((ValuePattern)raw).Current.Value;
            else if(result.TryGetCurrentPattern(TextPattern.Pattern,out raw))text=((TextPattern)raw).DocumentRange.GetText(20000);
            else text=result.Current.Name;
            if(ValidResult(text,prompt))return;
            Thread.Sleep(50);
        }
        throw new Exception("Local acknowledgement not verified. Submit was not repeated.");
    }
}
