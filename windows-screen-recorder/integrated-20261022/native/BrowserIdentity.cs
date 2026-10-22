using System;
using System.Collections.Generic;
using System.Web.Script.Serialization;
using System.Windows.Automation;

// Browser-provided semantic identity; never persist HWND, UIA runtime IDs,
// extension tab IDs or document instance IDs across a saved-task restart.
static class BrowserIdentity {
    const string Prefix="Sports Cave browser v2: ";
    public static Dictionary<string,object> Read(AutomationElement e) {
        return ReadHelp(e.Current.HelpText);
    }
    public static Dictionary<string,object> ReadHelp(string help) {
        foreach(string line in help.Split('\n'))if(line.StartsWith(Prefix,StringComparison.Ordinal)) {
            if(line.Length>6000)throw new Exception("Browser identity exceeded its bound.");
            var raw=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(Uri.UnescapeDataString(line.Substring(Prefix.Length)));
            var result=new Dictionary<string,object>();
            foreach(string key in new[]{"profile","page","frame","control"}) {
                if(!raw.ContainsKey(key)||!(raw[key] is string))throw new Exception("Incomplete browser identity.");
                string value=(string)raw[key];if(value.Length==0||value.Length>(key=="page"?500:180))throw new Exception("Unbounded browser identity.");
                Capture.Safe(value);result[key]=value;
            }
            Guid profile;if(!Guid.TryParse((string)result["profile"],out profile))throw new Exception("Invalid browser profile identity.");
            Uri url;if(!Uri.TryCreate((string)result["page"],UriKind.Absolute,out url)||url.Scheme!="http"||url.Host!="127.0.0.1"||
                (url.Port!=18962&&url.Port!=18963)||url.UserInfo!=""||url.Fragment!="")throw new Exception("Browser page is outside the permitted preview origins.");
            foreach(string part in url.Query.TrimStart('?').Split('&')) {
                if(part.Length==0)continue;
                string key=Uri.UnescapeDataString(part.Split('=')[0]);
                if(key!="page"&&key!="upload"&&key!="sync_map")throw new Exception("Unsupported browser page identity field.");
            }
            if(raw.ContainsKey("product")) {
                if(!(raw["product"] is string)||!System.Text.RegularExpressions.Regex.IsMatch((string)raw["product"],"^[a-f0-9]{64}$"))
                    throw new Exception("Invalid prepared product identity.");
                result["product"]=raw["product"];
            }
            return result;
        }
        return null;
    }
    public static bool SamePage(Dictionary<string,object> a,Dictionary<string,object> b) {
        return a!=null&&b!=null&&Equals(a["profile"],b["profile"])&&Equals(a["page"],b["page"])&&
            a.ContainsKey("product")==b.ContainsKey("product")&&(!a.ContainsKey("product")||Equals(a["product"],b["product"]));
    }
    public static bool SameControl(Dictionary<string,object> a,Dictionary<string,object> b) {
        return SamePage(a,b)&&Equals(a["frame"],b["frame"])&&Equals(a["control"],b["control"]);
    }
    public static Dictionary<string,object> Current(IntPtr window) {
        if(!BrowserTabs.Edge(window))return null;
        var items=AutomationElement.FromHandle(window).FindAll(TreeScope.Descendants,
            new PropertyCondition(AutomationElement.AutomationIdProperty,"sc-recorder-document"));
        Dictionary<string,object> found=null;
        foreach(AutomationElement item in items){
            if(item.Current.IsOffscreen)continue;
            var value=Read(item);if(value==null||(string)value["frame"]!="top")continue;
            if(found!=null)throw new Exception("More than one active browser document. No page guessed.");
            found=value;
        }
        return found;
    }
    public static AutomationElement Resolve(IntPtr window,Dictionary<string,object> target) {
        var expected=(Dictionary<string,object>)target["browser"];
        if(!SamePage(Current(window),expected))throw new Exception("The prepared browser profile or page changed. No action sent.");
        var type=ControlType.LookupById(TypeId((string)target["control_type"]));
        var items=AutomationElement.FromHandle(window).FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,type));
        if(items.Count>2000)throw new Exception("Browser control search exceeded its bound.");
        AutomationElement found=null;
        foreach(AutomationElement item in items){
            if(item.Current.IsOffscreen||!SameControl(Read(item),expected))continue;
            if(found!=null)throw new Exception("Browser control identity is ambiguous. No target guessed.");
            found=item;
        }
        if(found==null)throw new DesktopPlayback.ControlNotReadyException("The recorded browser control is missing or its frame changed.");
        return found;
    }
    static int TypeId(string type) {
        foreach(var field in typeof(ControlType).GetFields(System.Reflection.BindingFlags.Public|System.Reflection.BindingFlags.Static))
            if(field.Name==type)return ((ControlType)field.GetValue(null)).Id;
        throw new Exception("Unsupported browser control type.");
    }
}
