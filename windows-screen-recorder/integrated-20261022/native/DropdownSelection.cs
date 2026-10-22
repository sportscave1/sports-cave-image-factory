using System;
using System.Collections.Generic;
using System.Windows;
using System.Windows.Automation;

// UIA ownership, never a field/page map. A popup is not an editor and its
// temporary option IDs are not durable recording targets.
static class DropdownSelection {
    public const int AncestryLimit=32;
    public static object Inspect(IntPtr window) {
        var root=AutomationElement.FromHandle(window);
        var combos=root.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.ComboBox));
        var rows=new List<object>();
        for(int i=0;i<Math.Min(4,combos.Count);i++) {
            var combo=combos[i];var parents=new List<object>();
            for(var parent=TreeWalker.RawViewWalker.GetParent(combo);parent!=null&&parents.Count<3;parent=TreeWalker.RawViewWalker.GetParent(parent)) {
                var children=new List<object>();
                for(var child=TreeWalker.RawViewWalker.GetFirstChild(parent);child!=null&&children.Count<6;child=TreeWalker.RawViewWalker.GetNextSibling(child))children.Add(Metadata(child));
                parents.Add(new {element=Metadata(parent),children=children});
            }
            var controlled=combo.GetCurrentPropertyValue(AutomationElementIdentifiers.ControllerForProperty,true) as AutomationElement[];
            var links=new List<object>();if(controlled!=null)for(int j=0;j<Math.Min(8,controlled.Length);j++)links.Add(Metadata(controlled[j]));
            var label=combo.GetCurrentPropertyValue(AutomationElement.LabeledByProperty,true) as AutomationElement;
            var directOptions=combo.FindAll(TreeScope.Children,System.Windows.Automation.Condition.TrueCondition);
            var directRows=new List<object>();
            for(int j=0;j<Math.Min(8,directOptions.Count);j++) {
                var item=directOptions[j];object selection;AutomationElement container=null;
                if(item.TryGetCurrentPattern(SelectionItemPattern.Pattern,out selection))container=((SelectionItemPattern)selection).Current.SelectionContainer;
                directRows.Add(new {element=Metadata(item),container=container==null?null:Metadata(container),container_is_owner=container!=null&&Automation.Compare(container,combo)});
            }
            rows.Add(new {element=Metadata(combo),label=label==null?null:Metadata(label),controller_for=links,parents=parents,direct_children=directRows});
        }
        var lists=root.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.List));
        var listRows=new List<object>();
        for(int i=0;i<Math.Min(4,lists.Count);i++) {
            var list=lists[i];if(list.Current.IsOffscreen)continue;
            var options=list.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.ListItem));
            var optionRows=new List<object>();
            for(int j=0;j<Math.Min(3,options.Count);j++) {
                object pattern;AutomationElement container=null;
                if(options[j].TryGetCurrentPattern(SelectionItemPattern.Pattern,out pattern))container=((SelectionItemPattern)pattern).Current.SelectionContainer;
                optionRows.Add(new {element=Metadata(options[j]),selection_container_matches=container!=null&&Automation.Compare(container,list)});
            }
            listRows.Add(new {element=Metadata(list),option_count=options.Count,options=optionRows});
        }
        return new {candidate_count=combos.Count,truncated=combos.Count>4||lists.Count>4,candidates=rows,lists=listRows};
    }
    static object Metadata(AutomationElement e) {
        var current=e.Current;var bounds=current.BoundingRectangle;
        // Control identities and capabilities only; never Value/Text contents.
        object expansion;string expanded=e.TryGetCurrentPattern(ExpandCollapsePattern.Pattern,out expansion)?((ExpandCollapsePattern)expansion).Current.ExpandCollapseState.ToString():null;
        return new {control_type=current.ControlType.ProgrammaticName,automation_id=Capture.Safe(current.AutomationId),
            name=Capture.Safe(current.Name),offscreen=current.IsOffscreen,
            bounds=bounds.IsEmpty?null:new double[]{bounds.X,bounds.Y,bounds.Width,bounds.Height},
            selection=e.GetCurrentPropertyValue(AutomationElement.IsSelectionPatternAvailableProperty),
            selection_item=e.GetCurrentPropertyValue(AutomationElement.IsSelectionItemPatternAvailableProperty),
            value=e.GetCurrentPropertyValue(AutomationElement.IsValuePatternAvailableProperty),
            expand=e.GetCurrentPropertyValue(AutomationElement.IsExpandCollapsePatternAvailableProperty),expansion_state=expanded};
    }
    public static void Safe(AutomationElement e,uint pid) {
        object password=e.GetCurrentPropertyValue(AutomationElement.IsPasswordProperty,true);
        bool field=e.Current.ControlType==ControlType.ComboBox||e.Current.ControlType==ControlType.Edit||e.Current.ControlType==ControlType.Document;
        if(e.Current.ProcessId!=pid||password is bool&&(bool)password||field&&!(password is bool)||!e.Current.IsEnabled)
            throw new Exception("Protected, disabled or unclassified dropdown control. Draft preserved.");
        Capture.Safe(e.Current.AutomationId);Capture.Safe(e.Current.Name);
    }
    public static bool Descendant(AutomationElement node,AutomationElement parent,uint pid) {
        for(int depth=0;node!=null&&depth<AncestryLimit;depth++,node=TreeWalker.ControlViewWalker.GetParent(node)) {
            if(node.Current.ProcessId!=pid)return false;
            if(Automation.Compare(node,parent))return true;
        }
        return false;
    }
    public static List<AutomationElement> Lists(AutomationElement owner,uint pid) {
        Safe(owner,pid);
        var result=new List<AutomationElement>();
        // Native HTML selects can expose options directly under the combobox,
        // without an intervening List. Their explicit SelectionContainer may
        // be a provider-only List omitted from descendant searches. Follow
        // that link from the owner's direct child, never a nearby popup.
        var direct=owner.FindAll(TreeScope.Children,new PropertyCondition(AutomationElement.IsSelectionItemPatternAvailableProperty,true));
        if(direct.Count>256)throw new Exception("Dropdown option search exceeded its bound.");
        foreach(AutomationElement item in direct) {
            Safe(item,pid);object selection;
            if(!item.TryGetCurrentPattern(SelectionItemPattern.Pattern,out selection))continue;
            var container=((SelectionItemPattern)selection).Current.SelectionContainer;
            if(container!=null&&(Automation.Compare(container,owner)||container.Current.ControlType==ControlType.List))AddList(result,container,pid);
        }
        var nested=owner.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.List));
        if(nested.Count>16)throw new Exception("Dropdown has too many selection containers.");
        foreach(AutomationElement list in nested)AddList(result,list,pid);
        var property=AutomationElementIdentifiers.ControllerForProperty;
        if(property!=null) {
            var controlled=owner.GetCurrentPropertyValue(property,true) as AutomationElement[];
            if(controlled!=null) {
                if(controlled.Length>16)throw new Exception("Dropdown popup ownership is ambiguous.");
                foreach(var list in controlled)if(list.Current.ControlType==ControlType.List)AddList(result,list,pid);
            }
        }
        // Chromium may omit ControllerFor even when aria-controls is valid.
        // The local adapter binds one newly opened menu to one unique owner;
        // require its explicit marker in the same document, never a global list.
        if(result.Count==0){var projected=EdgeDropdownAdapter.OwnedList(owner,pid);if(projected!=null)AddList(result,projected,pid);}
        return result;
    }
    static void AddList(List<AutomationElement> lists,AutomationElement list,uint pid) {
        Safe(list,pid);if(list.Current.IsOffscreen)return;
        foreach(var old in lists)if(Automation.Compare(old,list))return;
        lists.Add(list);
    }
    public static bool Open(AutomationElement owner,uint pid) {
        object pattern;
        if(owner.TryGetCurrentPattern(ExpandCollapsePattern.Pattern,out pattern)&&
            ((ExpandCollapsePattern)pattern).Current.ExpandCollapseState==ExpandCollapseState.Expanded)return true;
        return Lists(owner,pid).Count>0;
    }
    public static string Selected(AutomationElement owner,uint pid) {
        Safe(owner,pid);object pattern;
        string projected;if(EdgeDropdownAdapter.Selected(owner,pid,out projected))return projected;
        if(owner.TryGetCurrentPattern(SelectionPattern.Pattern,out pattern)) {
            var items=((SelectionPattern)pattern).Current.GetSelection();
            if(items.Length>1)throw new Exception("Multiple dropdown selections are not supported.");
            if(items.Length==1){Safe(items[0],pid);return Capture.Safe(items[0].Current.Name);}
        }
        if(owner.TryGetCurrentPattern(ValuePattern.Pattern,out pattern))
            return Capture.Safe(((ValuePattern)pattern).Current.Value);
        throw new Exception("Dropdown does not expose a verifiable selected value.");
    }
    public static AutomationElement AtPoint(IntPtr hwnd,uint pid,Point point) {
        var root=AutomationElement.FromHandle(hwnd);
        var combos=root.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.ComboBox));
        if(combos.Count>64)throw new Exception("Dropdown search exceeded its bounded budget.");
        AutomationElement found=null;
        foreach(AutomationElement combo in combos) {
            if(combo.Current.IsOffscreen)continue;
            bool contains=combo.Current.BoundingRectangle.Contains(point)||EdgeDropdownAdapter.Contains(combo,pid,point);
            if(!contains) {
                // Some accessible comboboxes expose their disclosure button as
                // a sibling in one group. Require that exact structural owner,
                // one combobox and the physical point inside its sole button.
                var group=TreeWalker.ControlViewWalker.GetParent(combo);
                if(group!=null&&group.Current.ControlType==ControlType.Group&&group.Current.ProcessId==pid&&group.Current.BoundingRectangle.Contains(point)) {
                    var peers=group.FindAll(TreeScope.Children,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.ComboBox));
                    var buttons=group.FindAll(TreeScope.Children,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Button));
                    contains=peers.Count==1&&buttons.Count==1&&!buttons[0].Current.IsOffscreen&&buttons[0].Current.BoundingRectangle.Contains(point);
                    if(contains)Safe(buttons[0],pid);
                }
            }
            if(!contains)continue;
            Safe(combo,pid);
            if(!Descendant(combo,root,pid))continue;
            if(found!=null)throw new Exception("More than one dropdown contains the click. No target guessed.");
            found=combo;
        }
        return found;
    }
    public static AutomationElement OptionAt(AutomationElement owner,uint pid,Point point) {
        AutomationElement found=null;
        foreach(var list in Lists(owner,pid)) {
            if(!list.Current.BoundingRectangle.Contains(point))continue;
            var items=list.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.IsSelectionItemPatternAvailableProperty,true));
            if(items.Count>256)throw new Exception("Dropdown option search exceeded its bound.");
            foreach(AutomationElement item in items) {
                if(item.Current.IsOffscreen||!item.Current.BoundingRectangle.Contains(point))continue;
                Safe(item,pid);object pattern;
                if(!item.TryGetCurrentPattern(SelectionItemPattern.Pattern,out pattern))continue;
                var container=((SelectionItemPattern)pattern).Current.SelectionContainer;
                if(container==null||!Automation.Compare(container,list))continue;
                if(found!=null)throw new Exception("Dropdown option click is ambiguous.");
                found=item;
            }
        }
        return found;
    }
    public static bool ContainsPopup(AutomationElement owner,uint pid,Point point) {
        foreach(var list in Lists(owner,pid))if(list.Current.BoundingRectangle.Contains(point))return true;
        return false;
    }
    public static AutomationElement FindOption(AutomationElement owner,uint pid,string value) {
        AutomationElement found=null;
        foreach(var list in Lists(owner,pid)) {
            var items=list.FindAll(TreeScope.Descendants,new AndCondition(
                new PropertyCondition(AutomationElement.NameProperty,value),
                new PropertyCondition(AutomationElement.IsSelectionItemPatternAvailableProperty,true)));
            if(items.Count>16)throw new Exception("Dropdown option identity is ambiguous.");
            foreach(AutomationElement item in items) {
                Safe(item,pid);object pattern;item.TryGetCurrentPattern(SelectionItemPattern.Pattern,out pattern);
                var container=((SelectionItemPattern)pattern).Current.SelectionContainer;
                if(container==null||!Automation.Compare(container,list))continue;
                if(found!=null)throw new Exception("Dropdown option is not unique. No input sent.");
                found=item;
            }
        }
        return found;
    }
    public static string View(AutomationElement owner,uint pid) {
        var marks=new List<string>();
        foreach(var list in Lists(owner,pid)) {
            var items=list.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.IsSelectionItemPatternAvailableProperty,true));
            if(items.Count>256)throw new Exception("Dropdown view exceeded its bounded option budget.");
            foreach(AutomationElement item in items)if(!item.Current.IsOffscreen&&item.Current.BoundingRectangle.IntersectsWith(list.Current.BoundingRectangle)) {
                Safe(item,pid);marks.Add(Capture.Safe(item.Current.Name));
            }
        }
        return String.Join("\n",marks.ToArray());
    }
    public static double? ScrollPosition(AutomationElement owner,uint pid) {
        var lists=Lists(owner,pid);
        if(lists.Count>1)throw new Exception("Dropdown scroll ownership is ambiguous.");
        if(lists.Count==0)return null;
        var access=ScrollAccess.Bind(lists[0],pid,false,true);
        return access==null?(double?)null:access.Vertical;
    }
}
