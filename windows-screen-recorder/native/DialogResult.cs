using System;
using System.Collections;
using System.Collections.Generic;
using System.Windows.Automation;

// A generic modal result, not a file/sport/page-specific mapping. It proves
// dismissal of the exact containing dialog, not an arbitrary application job.
static class DialogResult {
    public const string Contract="uia.dialog-dismissed.v1";
    public static bool IsModal(AutomationElement element) {
        object pattern;
        return element.Current.ControlType==ControlType.Window&&
            element.TryGetCurrentPattern(WindowPattern.Pattern,out pattern)&&((WindowPattern)pattern).Current.IsModal;
    }
    public static Dictionary<string,object> Target(Dictionary<string,object> button) {
        var scope=button["scope"] as IList;if(scope==null)return null;
        for(int i=0;i<scope.Count;i++) {
            var anchor=scope[i] as Dictionary<string,object>;
            if(anchor==null||!Equals(anchor["control_type"],"Window"))continue;
            var remaining=new List<object>();for(int j=i+1;j<scope.Count;j++)remaining.Add(scope[j]);
            return new Dictionary<string,object>{{"app",button["app"]},{"window_key",button["window_key"]},
                {"control_type",anchor["control_type"]},{"automation_id",anchor["automation_id"]},{"name",anchor["name"]},{"scope",remaining}};
        }
        return null;
    }
    public static bool Supports(Dictionary<string,object> button) {
        object value;return button.TryGetValue("postcondition",out value)&&Equals(value,Contract)&&Target(button)!=null;
    }
    public static bool CaptureModal(AutomationElement button,IntPtr hwnd,uint pid) {
        var parent=TreeWalker.ControlViewWalker.GetParent(button);
        for(int depth=0;parent!=null&&depth<32;depth++,parent=TreeWalker.ControlViewWalker.GetParent(parent)) {
            if(parent.Current.ProcessId!=pid)return false;
            if(parent.Current.NativeWindowHandle==hwnd.ToInt32())return false;
            if(parent.Current.ControlType==ControlType.Window)return IsModal(parent);
        }
        return false;
    }
}
