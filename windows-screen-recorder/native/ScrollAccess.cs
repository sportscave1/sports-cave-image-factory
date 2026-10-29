using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Windows;
using System.Windows.Automation;

// Bind to the resolved container. Never search an unrelated ancestor/window or
// turn a missing provider pattern into guessed wheel/key input.
sealed class ScrollAccess {
    public const string ScopedSelector="uia.unique-scoped-scroll.v1";
    public static bool IsLayout(AutomationElement e) {
        var type=e.Current.ControlType;
        return type==ControlType.Group||type==ControlType.Pane||type==ControlType.Custom;
    }
    public static AutomationElement ResolveScoped(IntPtr window,Dictionary<string,object> target) {
        // No positional selector or index: the named ancestor scope must have
        // exactly one anonymous scroll provider of this type on every resolve.
        uint pid;Native.GetWindowThreadProcessId(window,out pid);
        var root=AutomationElement.FromHandle(window);
        var candidates=root.FindAll(TreeScope.Descendants,new AndCondition(
            new PropertyCondition(AutomationElement.IsScrollPatternAvailableProperty,true),
            new PropertyCondition(AutomationElement.AutomationIdProperty,""),
            new PropertyCondition(AutomationElement.NameProperty,"")));
        if(candidates.Count>64)throw new Exception("Scoped scroll search exceeded its bound.");
        var wait=Stopwatch.StartNew();AutomationElement found=null;
        foreach(AutomationElement candidate in candidates) {
            if(wait.ElapsedMilliseconds>200)throw new Exception("Scoped scroll inspection timed out.");
            if(!IsLayout(candidate)||candidate.Current.ControlType.ProgrammaticName!="ControlType."+(string)target["control_type"]||
                !DesktopPlayback.ScopeMatches(candidate,window,target))continue;
            Safe(candidate,pid);
            if(found!=null)throw new Exception("Recorded scroll container is ambiguous. No input sent.");
            found=candidate;
        }
        if(found==null)throw new DesktopPlayback.ControlNotReadyException("Recorded scroll container is not ready.");
        return found;
    }
    readonly ScrollPattern primary;
    readonly RangeValuePattern horizontal,vertical;
    public readonly string Method;
    ScrollAccess(ScrollPattern scroll,string method){primary=scroll;Method=method;}
    ScrollAccess(RangeValuePattern h,RangeValuePattern v){horizontal=h;vertical=v;Method="owned scrollbars";}
    static void Safe(AutomationElement e,uint pid) {
        object password=e.GetCurrentPropertyValue(AutomationElement.IsPasswordProperty,true);
        if(e.Current.ProcessId!=pid||password is bool&&(bool)password||!e.Current.IsEnabled)
            throw new Exception("Scroll container protection or process identity changed.");
        if((e.Current.ControlType==ControlType.Edit||e.Current.ControlType==ControlType.Document)&&!(password is bool))
            throw new Exception("Scroll container protection classification is unavailable.");
    }
    public static bool Close(double actual,double desired) {return desired==-1||actual>=0&&Math.Abs(actual-desired)<=0.5;}
    public static double Percent(double value,double minimum,double maximum) {
        if(Double.IsNaN(value)||Double.IsInfinity(value)||Double.IsNaN(minimum)||Double.IsInfinity(minimum)||
            Double.IsNaN(maximum)||Double.IsInfinity(maximum)||maximum<=minimum||value<minimum||value>maximum)
            throw new Exception("Scroll range cannot establish a bounded position.");
        return (value-minimum)*100/(maximum-minimum);
    }
    static bool Supports(ScrollPattern scroll,bool h,bool v) {
        var current=scroll.Current;return (!h||current.HorizontallyScrollable)&&(!v||current.VerticallyScrollable);
    }
    public static ScrollAccess Bind(AutomationElement target,uint pid,bool h,bool v) {
        Safe(target,pid);object pattern;
        if(target.TryGetCurrentPattern(ScrollPattern.Pattern,out pattern)&&Supports((ScrollPattern)pattern,h,v))
            return new ScrollAccess((ScrollPattern)pattern,"container ScrollPattern");
        var bounds=target.Current.BoundingRectangle;
        var descendants=target.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.IsScrollPatternAvailableProperty,true));
        if(descendants.Count>64)throw new Exception("Scroll fallback search exceeded its bound.");
        ScrollPattern found=null;var wait=Stopwatch.StartNew();
        foreach(AutomationElement child in descendants) {
            if(wait.ElapsedMilliseconds>200)throw new Exception("Scroll fallback inspection timed out.");
            Safe(child,pid);if(child.Current.IsOffscreen)continue;
            var box=child.Current.BoundingRectangle;
            // A provider may move its pattern to an anonymous wrapper with the
            // same viewport. A smaller, nested list is a different container.
            if(!SameViewport(bounds,box)||!LayoutPath(child,target,pid))continue;
            if(!child.TryGetCurrentPattern(ScrollPattern.Pattern,out pattern)||!Supports((ScrollPattern)pattern,h,v))continue;
            if(found!=null)throw new Exception("Scroll fallback is ambiguous. No input sent.");
            found=(ScrollPattern)pattern;
        }
        if(found!=null)return new ScrollAccess(found,"same viewport ScrollPattern");
        var bars=target.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.ScrollBar));
        if(bars.Count>16)throw new Exception("Scrollbars are ambiguous. No input sent.");
        RangeValuePattern hp=null,vp=null;
        foreach(AutomationElement bar in bars) {
            Safe(bar,pid);if(bar.Current.IsOffscreen||!LayoutPath(bar,target,pid)||!bar.TryGetCurrentPattern(RangeValuePattern.Pattern,out pattern))continue;
            var range=(RangeValuePattern)pattern;
            if(range.Current.IsReadOnly||range.Current.Maximum<=range.Current.Minimum)continue;
            if(bar.Current.Orientation==OrientationType.Horizontal){if(hp!=null)throw new Exception("Horizontal scrollbar is ambiguous.");hp=range;}
            if(bar.Current.Orientation==OrientationType.Vertical){if(vp!=null)throw new Exception("Vertical scrollbar is ambiguous.");vp=range;}
        }
        return (!h||hp!=null)&&(!v||vp!=null)&&(hp!=null||vp!=null)?new ScrollAccess(hp,vp):null;
    }
    static bool SameViewport(Rect a,Rect b) {
        return !a.IsEmpty&&!b.IsEmpty&&Math.Abs(a.X-b.X)<=2&&Math.Abs(a.Y-b.Y)<=2&&
            Math.Abs(a.Width-b.Width)<=2&&Math.Abs(a.Height-b.Height)<=2;
    }
    static bool LayoutPath(AutomationElement child,AutomationElement target,uint pid) {
        var parent=TreeWalker.RawViewWalker.GetParent(child);
        for(int depth=0;parent!=null&&depth<32;depth++,parent=TreeWalker.RawViewWalker.GetParent(parent)) {
            Safe(parent,pid);if(Automation.Compare(parent,target))return true;
            if(parent.Current.ControlType!=ControlType.Pane&&parent.Current.ControlType!=ControlType.Group&&parent.Current.ControlType!=ControlType.Custom)return false;
            if(parent.Current.AutomationId.Length!=0||parent.Current.Name.Length!=0)return false;
        }
        return false;
    }
    static double ReadRange(RangeValuePattern range) {
        if(range==null)return -1;var state=range.Current;
        return Percent(state.Value,state.Minimum,state.Maximum);
    }
    public double Horizontal {get {return primary!=null?primary.Current.HorizontalScrollPercent:ReadRange(horizontal);}}
    public double Vertical {get {return primary!=null?primary.Current.VerticalScrollPercent:ReadRange(vertical);}}
    public double? HorizontalView {get {return primary!=null?(double?)primary.Current.HorizontalViewSize:null;}}
    public double? VerticalView {get {return primary!=null?(double?)primary.Current.VerticalViewSize:null;}}
    public static bool ViewMatches(double? actual,double desired) {
        return actual.HasValue&&Math.Abs(actual.Value-desired)<=0.5;
    }
    public bool MatchesViewport(Dictionary<string,object> position) {
        return (!position.ContainsKey("horizontal_view_size")||Convert.ToDouble(position["horizontal"])==-1||
            ViewMatches(HorizontalView,Convert.ToDouble(position["horizontal_view_size"])))&&
            (!position.ContainsKey("vertical_view_size")||Convert.ToDouble(position["vertical"])==-1||
            ViewMatches(VerticalView,Convert.ToDouble(position["vertical_view_size"])));
    }
    public bool At(double h,double v){return Close(Horizontal,h)&&Close(Vertical,v);}
    public void Set(double h,double v) {
        if(primary!=null){primary.SetScrollPercent(h,v);return;}
        if(h!=-1){var state=horizontal.Current;horizontal.SetValue(state.Minimum+(state.Maximum-state.Minimum)*h/100);}
        if(v!=-1){var state=vertical.Current;vertical.SetValue(state.Minimum+(state.Maximum-state.Minimum)*v/100);}
    }
}
