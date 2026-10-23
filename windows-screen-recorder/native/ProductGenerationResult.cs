using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Text.RegularExpressions;
using System.Windows.Automation;

// The application acknowledges one Generate request only after its current
// source/context result has been applied. Receipt IDs never enter recordings.
static class ProductGenerationResult {
    public const string Contract="sports-cave.product-generation.v1";
    public const string Container="sc-product-mockup-generation";
    public sealed class Witness {
        public readonly string State,Receipt;
        public Witness(string state,string receipt){State=state;Receipt=receipt;}
    }
    static readonly Regex Identity=new Regex("^"+Container+"-(idle|working|ready|failed|changed)-([a-f0-9]{32})$");
    static readonly Dictionary<string,string> Labels=new Dictionary<string,string>{
        {"idle","Artwork ready"},{"working","Generating mockups"},{"ready","Mockups ready"},
        {"failed","Mockup generation failed"},{"changed","Product details changed"}};
    public static Witness Parse(string id,string name) {
        var match=Identity.Match(id??"");
        if(!match.Success||Labels[match.Groups[1].Value]!=name)return null;
        return new Witness(match.Groups[1].Value,match.Groups[2].Value);
    }
    public static bool KnownButton(string app,string type,string name) {
        return type=="Button"&&name=="Generate mockups"&&
            String.Equals(Path.GetFileName(app),"msedge.exe",StringComparison.OrdinalIgnoreCase);
    }
    public static bool Supports(Dictionary<string,object> target) {
        object contract;
        return target.TryGetValue("postcondition",out contract)&&Equals(contract,Contract)&&
            KnownButton((string)target["app"],(string)target["control_type"],(string)target["name"]);
    }
    static bool Anchor(object raw,string type,string id,string name=null) {
        var value=raw as Dictionary<string,object>;object t,i,n;
        return value!=null&&value.TryGetValue("control_type",out t)&&Equals(t,type)&&
            value.TryGetValue("automation_id",out i)&&Equals(i,id)&&value.TryGetValue("name",out n)&&
            n is string&&(name==null?((string)n).Length>0:Equals(n,name));
    }
    public static bool StableScope(IList scope) {
        return scope!=null&&scope.Count==3&&Anchor(scope[0],"Group","root","")&&
            Anchor(scope[1],"Document","RootWebArea")&&Anchor(scope[2],"Pane","");
    }
    public static bool LayoutBoundary(int index,string type,string id) {
        // Current Streamlit exposes its main layout with the stable stMain ID.
        // Accept only this one immediate layout boundary; root/document/window
        // anchors and the independent generation witness remain mandatory.
        return index==0&&type=="Group"&&(id==""||id=="stMain");
    }
    public static bool ScopeMatches(IList expected,IEnumerable<ProductCopyResult.ScopeAnchor> actual) {
        if(!StableScope(expected))return false;
        int index=0,visited=0;bool layoutSeen=false;
        foreach(var item in actual) {
            if(++visited>16)return false;
            // Streamlit may expose one content-named layout Group inside root.
            // Never read its content-derived name. The saved root/document/pane
            // remain exact; Read independently binds the result to that document.
            if(!layoutSeen&&LayoutBoundary(index,item.Type,item.Id)) {
                if(item.ValidateHost==null||!item.ValidateHost())return false;
                layoutSeen=true;continue;
            }
            string name=item.ReadName();
            if(item.Id==""&&name=="")continue;
            if(index>=expected.Count||!Anchor(expected[index],item.Type,item.Id,name))return false;
            index++;
        }
        return index==expected.Count;
    }
    public static bool Completed(Witness before,Witness after) {
        return before!=null&&after!=null&&after.Receipt!=before.Receipt&&after.State=="ready";
    }
    public static bool Acknowledged(Witness before,Witness after) {
        return before!=null&&after!=null&&after.Receipt!=before.Receipt&&
            (after.State=="working"||after.State=="ready");
    }
    static void Safe(AutomationElement e,uint pid) {
        object password=e.GetCurrentPropertyValue(AutomationElement.IsPasswordProperty,true);
        if(e.Current.ProcessId!=pid)
            throw new Exception("Generation acknowledgement process check failed for "+e.Current.ControlType.ProgrammaticName+".");
        if(password is bool&&(bool)password)
            throw new Exception("Protected generation acknowledgement excluded.");
        // Layout containers expose identity metadata only. As in capture's
        // existing Privacy rule, unknown text-field classification still blocks.
        if(!(password is bool)&&(e.Current.ControlType==ControlType.Edit||e.Current.ControlType==ControlType.Document))
            throw new Exception("Generation document protection classification is unavailable.");
    }
    public static AutomationElement Document(AutomationElement e,IntPtr hwnd,uint pid) {
        AutomationElement document=null;
        for(int depth=0;e!=null&&depth<16;depth++,e=TreeWalker.ControlViewWalker.GetParent(e)) {
            Safe(e,pid);
            if(e.Current.NativeWindowHandle==hwnd.ToInt32())return document;
            if(e.Current.ControlType==ControlType.Document) {
                if(document!=null||e.Current.AutomationId!="RootWebArea")
                    throw new Exception("Generation acknowledgement must belong to the top-level product page.");
                document=e;
            }
        }
        throw new Exception("Generation acknowledgement ancestry is not supported.");
    }
    static IEnumerable<AutomationElement> Children(AutomationElement e) {
        for(var child=TreeWalker.ControlViewWalker.GetFirstChild(e);child!=null;child=TreeWalker.ControlViewWalker.GetNextSibling(child))yield return child;
    }
    public static Witness Read(AutomationElement button,IntPtr hwnd,uint pid) {
        return ReadForDocument(Document(button,hwnd,pid),hwnd,pid);
    }
    public static Witness ReadForDocument(AutomationElement document,IntPtr hwnd,uint pid) {
        var root=AutomationElement.FromHandle(hwnd);
        var containers=root.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.AutomationIdProperty,Container));
        if(containers.Count==0)return null;
        if(containers.Count!=1)throw new Exception("Generation acknowledgement is ambiguous. No target guessed.");
        var container=containers[0];Safe(container,pid);
        if(container.Current.Name!="Product mockup generation")throw new Exception("Generation acknowledgement identity changed.");
        var statusDocument=Document(container,hwnd,pid);
        if(document==null||statusDocument==null||!Automation.Compare(document,statusDocument))
            throw new Exception("Generate and its acknowledgement belong to different documents.");
        var search=new ScrollTargetSearch<AutomationElement>(node=>{Safe(node,pid);return true;},
            node=>Parse(node.Current.AutomationId,node.Current.AutomationId.StartsWith(Container+"-")?node.Current.Name:"")!=null,
            Children,64,4,"Generation acknowledgement",200);
        var found=search.Find(container);
        return found==null?null:Parse(found.Current.AutomationId,found.Current.Name);
    }
}
