using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Windows.Automation;

// Choose PSD becomes inert when its HTML modal opens. Observe the exact modal,
// never infer success from focus or inspect Dropbox file names/field values.
static class ProductPickerResult {
    public const string Contract="sports-cave.product-psd-picker.v1";
    // The installed OS and normal Edge host the component below browser chrome
    // and nested Streamlit documents. Keep a finite bound without mistaking the
    // old 16-level traversal limit for a different window.
    public const int AncestryLimit=32;
    public static bool KnownScrollTarget(string app,string id,string name) {
        return String.Equals(Path.GetFileName(app),"msedge.exe",StringComparison.OrdinalIgnoreCase)&&
            id=="picker"&&name=="Choose PSD from Dropbox";
    }
    public static bool SupportsScroll(Dictionary<string,object> target) {
        object scope;
        if(!KnownScrollTarget((string)target["app"],(string)target["automation_id"],(string)target["name"])||
            !target.TryGetValue("scope",out scope)||!(scope is IList))return false;
        foreach(var raw in (IList)scope){var item=raw as Dictionary<string,object>;
            if(item!=null&&Equals(item["control_type"],"Document")&&Equals(item["automation_id"],"RootWebArea")&&Equals(item["name"],"Product Uploads"))return true;}
        return false;
    }
    public static AutomationElement ScrollContainer(IntPtr hwnd,uint pid,System.Windows.Point point) {
        if(!String.Equals(Path.GetFileName(Native.ProcessFor(hwnd).MainModule.FileName),"msedge.exe",StringComparison.OrdinalIgnoreCase))return null;
        var root=AutomationElement.FromHandle(hwnd);
        var matches=root.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.AutomationIdProperty,"picker"));
        if(matches.Count>16)throw new Exception("PSD picker scroll scope is ambiguous.");
        AutomationElement found=null;
        foreach(AutomationElement dialog in matches) {
            Safe(dialog,pid);
            if(dialog.Current.IsOffscreen||!dialog.Current.IsEnabled||dialog.Current.Name!="Choose PSD from Dropbox"||
                !dialog.Current.BoundingRectangle.Contains(point))continue;
            var document=Document(dialog,hwnd,pid);
            if(document==null||!Open(document,hwnd,pid))continue;
            if(found!=null)throw new Exception("More than one PSD picker contains the scroll. Draft preserved.");
            found=dialog;
        }
        if(found==null)return null;
        object pattern;
        if(!found.TryGetCurrentPattern(ScrollPattern.Pattern,out pattern))return null;
        var position=((ScrollPattern)pattern).Current;
        return position.HorizontallyScrollable||position.VerticallyScrollable?found:null;
    }
    public static bool KnownButton(string app,string type,string id,string name) {
        return String.Equals(Path.GetFileName(app),"msedge.exe",StringComparison.OrdinalIgnoreCase)&&
            type=="Button"&&id=="choose"&&name=="Choose PSD";
    }
    public static bool Supports(Dictionary<string,object> target) {
        object contract,scope;
        if(!target.TryGetValue("postcondition",out contract)||!Equals(contract,Contract)||
            !KnownButton((string)target["app"],(string)target["control_type"],(string)target["automation_id"],(string)target["name"])||
            !target.TryGetValue("scope",out scope)||!(scope is IList))return false;
        foreach(var raw in (IList)scope){var item=raw as Dictionary<string,object>;
            if(item!=null&&Equals(item["control_type"],"Document")&&Equals(item["automation_id"],"RootWebArea")&&Equals(item["name"],"Product Uploads"))return true;}
        return false;
    }
    static void Safe(AutomationElement element,uint pid) {
        object password=element.GetCurrentPropertyValue(AutomationElement.IsPasswordProperty,true);
        if(element.Current.ProcessId!=pid||password is bool&&(bool)password||
            (!(password is bool)&&(element.Current.ControlType==ControlType.Edit||element.Current.ControlType==ControlType.Document)))
            throw new Exception("PSD picker protection or process identity changed. No target guessed.");
    }
    public static AutomationElement Document(AutomationElement element,IntPtr hwnd,uint pid) {
        AutomationElement document=null;
        for(int depth=0;element!=null&&depth<AncestryLimit;depth++,element=TreeWalker.ControlViewWalker.GetParent(element)) {
            Safe(element,pid);
            if(element.Current.NativeWindowHandle==hwnd.ToInt32())return document;
            if(document==null&&element.Current.ControlType==ControlType.Document&&
                element.Current.AutomationId=="RootWebArea"&&element.Current.Name=="Product Uploads")document=element;
        }
        throw new Exception("PSD picker document does not reach the recorded window.");
    }
    public static bool Open(AutomationElement document,IntPtr hwnd,uint pid) {
        if(document==null||!Automation.Compare(Document(document,hwnd,pid),document))
            throw new Exception("PSD picker document identity changed.");
        var matches=document.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.AutomationIdProperty,"picker"));
        int visible=0;
        foreach(AutomationElement dialog in matches) {
            Safe(dialog,pid);if(dialog.Current.IsOffscreen)continue;
            if(dialog.Current.Name!="Choose PSD from Dropbox")throw new Exception("PSD picker dialog identity changed.");
            var close=dialog.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.AutomationIdProperty,"picker-close"));
            if(close.Count!=1)throw new Exception("PSD picker close control is missing or ambiguous.");
            var button=close[0];Safe(button,pid);
            // Scrolling the modal may move its header outside the viewport.
            // The unique enabled close control still identifies this dialog;
            // it is never invoked or used as a scroll/input destination here.
            if(!button.Current.IsEnabled||button.Current.ControlType!=ControlType.Button||button.Current.Name!="Close Dropbox picker")
                throw new Exception("PSD picker close control identity changed.");
            visible++;
        }
        if(visible>1)throw new Exception("PSD picker dialog is ambiguous.");
        return visible==1;
    }
}
