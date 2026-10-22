using System;
using System.IO;
using System.Windows;
using System.Windows.Automation;

// Read the local Edge extension's bounded accessibility projection. Native
// physical-input hooks remain the only source of capture intent.
static class EdgeDropdownAdapter {
    const string Prefix="Sports Cave Edge select v1: ";
    const string OwnerMarker="Sports Cave Edge select owner v1";
    public static AutomationElement OwnedList(AutomationElement combo,uint pid) {
        string selected;if(!Selected(combo,pid,out selected))return null;
        object expansion;
        if(!combo.TryGetCurrentPattern(ExpandCollapsePattern.Pattern,out expansion)||
            ((ExpandCollapsePattern)expansion).Current.ExpandCollapseState!=ExpandCollapseState.Expanded)return null;
        AutomationElement document=null;
        int depth=0;
        for(var node=TreeWalker.ControlViewWalker.GetParent(combo);node!=null&&depth++<32;node=TreeWalker.ControlViewWalker.GetParent(node)) {
            if(node.Current.ProcessId!=pid)return null;
            if(node.Current.ControlType==ControlType.Document){document=node;break;}
        }
        if(document==null)return null;
        var owners=document.FindAll(TreeScope.Descendants,new AndCondition(
            new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.ComboBox),
            new PropertyCondition(AutomationElement.NameProperty,combo.Current.Name)));
        if(owners.Count!=1||!Automation.Compare(owners[0],combo))throw new Exception("Projected dropdown owner is ambiguous.");
        var lists=document.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.List));
        if(lists.Count>16)throw new Exception("Projected dropdown list search exceeded its bound.");
        AutomationElement found=null;
        foreach(AutomationElement list in lists) {
            const string marker="Sports Cave Edge select menu v1: ";
            string help=list.Current.HelpText;
            if(list.Current.IsOffscreen||list.Current.Name!=combo.Current.Name+" choices"||
                help.Length>2000||!help.StartsWith(marker,StringComparison.Ordinal)||
                Capture.Safe(Uri.UnescapeDataString(help.Substring(marker.Length)))!=combo.Current.Name)continue;
            DropdownSelection.Safe(list,pid);
            if(found!=null)throw new Exception("Projected dropdown menu is ambiguous.");
            found=list;
        }
        return found;
    }
    public static bool Selected(AutomationElement combo,uint pid,out string selected) {
        selected=null;
        var description=combo.Current.HelpText;
        int start=description.LastIndexOf(Prefix,StringComparison.Ordinal);
        if(start<0)return false;
        if(!String.Equals(Path.GetFileName(System.Diagnostics.Process.GetProcessById((int)pid).MainModule.FileName),"msedge.exe",StringComparison.OrdinalIgnoreCase))
            throw new Exception("Edge adapter identity appeared outside Edge.");
        if(description.Length>2000)throw new Exception("Edge selected-value projection exceeded its bound.");
        selected=Capture.Safe(Uri.UnescapeDataString(description.Substring(start+Prefix.Length)));
        if(selected.Length>180)throw new Exception("Edge selected value exceeded its bound.");
        return true;
    }
    public static bool Contains(AutomationElement combo,uint pid,Point point) {
        string ignored;if(!Selected(combo,pid,out ignored))return false;
        var parent=TreeWalker.ControlViewWalker.GetParent(combo);
        for(int depth=0;parent!=null&&depth<5;depth++,parent=TreeWalker.ControlViewWalker.GetParent(parent)) {
            if(parent.Current.ProcessId!=pid)return false;
            if(parent.Current.HelpText!=OwnerMarker)continue;
            DropdownSelection.Safe(parent,pid);
            if(parent.Current.ControlType!=ControlType.Group||parent.Current.Name!=combo.Current.Name+" selection"||
                !parent.Current.BoundingRectangle.Contains(point))return false;
            var owners=parent.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.ComboBox));
            return owners.Count==1&&Automation.Compare(owners[0],combo);
        }
        return false;
    }
}
