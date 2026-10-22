using System;
using System.IO;
using System.Windows.Automation;

// Existing Edge tabs only. Page controls must never masquerade as browser chrome.
static class BrowserTabs {
    public static bool Edge(IntPtr window) {
        return String.Equals(Path.GetFileName(Native.ProcessFor(window).MainModule.FileName),"msedge.exe",StringComparison.OrdinalIgnoreCase);
    }
    public static bool ChromeTab(AutomationElement tab,IntPtr window) {
        if(tab.Current.ControlType!=ControlType.TabItem)return false;
        uint pid;Native.GetWindowThreadProcessId(window,out pid);
        bool tabBar=false;
        int depth=0;
        for(var node=tab;node!=null&&depth++<32;node=TreeWalker.ControlViewWalker.GetParent(node)) {
            if(node.Current.ProcessId!=pid||node.Current.ControlType==ControlType.Document)return false;
            if(node.Current.NativeWindowHandle==window.ToInt32())return tabBar;
            if(node.Current.ControlType==ControlType.Tab)tabBar=true;
        }
        return false;
    }
    public static AutomationElement Find(IntPtr window,string name,bool selectedOnly) {
        if(!Edge(window))throw new Exception("Browser tab switching requires Edge.");
        var tabs=AutomationElement.FromHandle(window).FindAll(TreeScope.Descendants,
            new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.TabItem));
        if(tabs.Count>128)throw new Exception("Too many browser tab candidates.");
        AutomationElement found=null;
        foreach(AutomationElement tab in tabs) {
            if(!ChromeTab(tab,window)||name!=null&&!WindowIdentity.EdgeTabNameMatches(name,tab.Current.Name))continue;
            object pattern;
            if(!tab.TryGetCurrentPattern(SelectionItemPattern.Pattern,out pattern))continue;
            if(selectedOnly&&!((SelectionItemPattern)pattern).Current.IsSelected)continue;
            if(found!=null)throw new Exception("Browser tab identity is ambiguous. No tab guessed.");
            found=tab;
        }
        if(found==null||!found.Current.IsEnabled||found.Current.IsOffscreen)
            throw new Exception("The recorded browser tab is not available.");
        Capture.Safe(found.Current.Name);
        return found;
    }
    public static bool Document(IntPtr window,string name) {
        uint pid;Native.GetWindowThreadProcessId(window,out pid);
        var docs=AutomationElement.FromHandle(window).FindAll(TreeScope.Descendants,new AndCondition(
            new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Document),
            new PropertyCondition(AutomationElement.AutomationIdProperty,"RootWebArea"),
            new PropertyCondition(AutomationElement.NameProperty,name)));
        if(docs.Count>16)return false;
        int matches=0;
        foreach(AutomationElement doc in docs) {
            if(doc.Current.IsOffscreen||doc.Current.ProcessId!=pid)continue;
            var parent=TreeWalker.ControlViewWalker.GetParent(doc);
            for(int depth=0;parent!=null&&depth<32;depth++,parent=TreeWalker.ControlViewWalker.GetParent(parent)) {
                if(parent.Current.ProcessId!=pid||parent.Current.ControlType==ControlType.Document)break;
                if(parent.Current.NativeWindowHandle==window.ToInt32()){matches++;break;}
            }
        }
        return matches==1;
    }
}
