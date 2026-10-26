using System;
using System.Collections.Generic;
class NativeDownloadWindowAnchorChecks {
    static int checks;
    static void Require(bool value,string reason){checks++;if(!value)throw new Exception(reason);}
    static void Reject(Action action,string reason){checks++;try{action();}catch{return;}throw new Exception(reason);}
    static Dictionary<string,object> Target(){return new Dictionary<string,object>{
        {"download",new Dictionary<string,object>{{"url","http://127.0.0.1:18963/sample.txt?sc_download=49c3a012-8dfc-426f-8b35-7b2aca074aff"},{"filename","sample.txt"},{"save_as",true}}},
        {"browser",new Dictionary<string,object>{{"profile","56578ebe-3793-47ba-b81f-fbc2c2755cf9"},{"page","http://127.0.0.1:18963/recorder-acceptance/tab-a"},{"frame","top"},{"control","id:save-as"}}}};}
    static int Main(){
        Require(BrowserDownload.CaptureWindowAnchor(new Dictionary<string,object>())==null,"ordinary controls keep normal window validation");
        var target=Target();var original=(Dictionary<string,object>)target["browser"];
        var anchor=BrowserDownload.CaptureWindowAnchor(target);
        Require(BrowserIdentity.SameControl(anchor,original),"Save As retains exact browser source");
        Require(!Object.ReferenceEquals(anchor,original),"window metadata must not mutate saved source identity");
        anchor["control"]="document";Require((string)original["control"]=="id:save-as","source control remains unchanged");
        target=Target();((Dictionary<string,object>)target["download"])["save_as"]=false;
        Require(BrowserDownload.CaptureWindowAnchor(target)==null,"ordinary downloads do not relax owner validation");
        target=Target();target.Remove("browser");Reject(()=>BrowserDownload.CaptureWindowAnchor(target),"missing browser identity");
        target=Target();target["browser"]="not an identity";Reject(()=>BrowserDownload.CaptureWindowAnchor(target),"wrong identity type");
        target=Target();((Dictionary<string,object>)target["browser"])["profile"]="invalid";Reject(()=>BrowserDownload.CaptureWindowAnchor(target),"invalid browser profile");
        target=Target();((Dictionary<string,object>)target["browser"])["page"]="http://127.0.0.1:18962/recorder-acceptance/tab-a";Reject(()=>BrowserDownload.CaptureWindowAnchor(target),"source/page origin mismatch");
        target=Target();((Dictionary<string,object>)target["browser"])["page"]="https://example.org/";Reject(()=>BrowserDownload.CaptureWindowAnchor(target),"unsupported page");
        target=Target();((Dictionary<string,object>)target["download"])["filename"]="../sample.txt";Reject(()=>BrowserDownload.CaptureWindowAnchor(target),"unsafe download path");
        target=Target();target["download"]=null;Reject(()=>BrowserDownload.CaptureWindowAnchor(target),"missing download source");
        Console.WriteLine("PASS "+checks+" download window anchor checks; no desktop input.");return 0;
    }
}
