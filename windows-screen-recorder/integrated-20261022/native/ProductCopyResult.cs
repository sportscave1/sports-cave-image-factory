using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;

// A narrowly scoped application acknowledgement, not clipboard-content proof.
// Resolve validates the stable UIA scope and process/window identity.
static class ProductCopyResult {
    public const string Ready="Copy prompt to clipboard",Success="Prompt copied";
    public const string Component="product_upload_gallery.product_upload_gallery";
    static string Get(Dictionary<string,object> value,string key) {
        object part;return value.TryGetValue(key,out part)?part as string:null;
    }
    static bool Is(Dictionary<string,object> value,string type,string id,string name) {
        return value!=null&&Get(value,"control_type")==type&&Get(value,"automation_id")==id&&Get(value,"name")==name;
    }
    public static bool KnownButton(string app,string type,string id,string name) {
        return type=="Button"&&id=="copyPrompt"&&(name=="Copy prompt"||name=="Copy Black Frame Prompt")&&
            String.Equals(Path.GetFileName(app),"msedge.exe",StringComparison.OrdinalIgnoreCase);
    }
    public static bool HasFrameAnchors(IList scope) {
        return scope!=null&&scope.Count>=3&&
            Is(scope[0] as Dictionary<string,object>,"Group","root","")&&
            Is(scope[1] as Dictionary<string,object>,"Document","RootWebArea","")&&
            (Is(scope[2] as Dictionary<string,object>,"Document","",Component)||
             Is(scope[2] as Dictionary<string,object>,"Document","sc-product-upload-copy",Component));
    }
    public static bool HostBoundary(int index,string type,string id) {
        return index==3&&type=="Group"&&id=="";
    }
    public static bool Supports(Dictionary<string,object> target) {
        if(!KnownButton(Get(target,"app"),Get(target,"control_type"),Get(target,"automation_id"),Get(target,"name")))return false;
        object raw;if(!target.TryGetValue("scope",out raw))return false;
        return HasFrameAnchors(raw as IList);
    }
    public sealed class ScopeAnchor {
        public readonly string Type,Id;
        public readonly Func<string> ReadName;
        public readonly Func<bool> ValidateHost;
        public ScopeAnchor(string type,string id,Func<string> name,Func<bool> validateHost=null) {
            Type=type;Id=id;ReadName=name;ValidateHost=validateHost;
        }
    }
    public static bool ScopeMatches(IList expected,IEnumerable<ScopeAnchor> actual) {
        if(!HasFrameAnchors(expected)||expected.Count>16)return false;
        var anchors=new ArrayList();
        for(int i=0;i<expected.Count;i++) {
            var item=expected[i] as Dictionary<string,object>;
            if(item==null)return false;
            if(HostBoundary(i,Get(item,"control_type"),Get(item,"automation_id")))continue;
            anchors.Add(item);
        }
        int index=0,visited=0;bool hostSeen=false;
        foreach(var item in actual) {
            if(++visited>16)return false;
            // One anonymous host Group immediately outside this exact iframe
            // is layout, not identity. Its potentially content-derived Name is
            // deliberately never read. All remaining anchors compare exactly.
            if(!hostSeen&&HostBoundary(index,item.Type,item.Id)) {
                if(item.ValidateHost!=null&&!item.ValidateHost())return false;
                hostSeen=true;continue;
            }
            string name=item.ReadName();
            if(item.Id==""&&name=="")continue;
            if(index>=anchors.Count||!Is(anchors[index] as Dictionary<string,object>,item.Type,item.Id,name))return false;
            index++;
        }
        return index==anchors.Count;
    }
}
