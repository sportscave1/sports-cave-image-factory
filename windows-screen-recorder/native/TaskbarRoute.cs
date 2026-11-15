using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Automation;

// Shell routes are separate from direct window focus. No stored HWND or pixels,
// no app launch, no SetForegroundWindow fallback, and no repeat after invocation.
static class TaskbarRoute {
    internal static readonly UIntPtr InputTag=new UIntPtr(0x53435442);
    [StructLayout(LayoutKind.Sequential)] struct MouseInput {public int x,y;public uint data,flags,time;public UIntPtr extra;}
    [StructLayout(LayoutKind.Explicit,Size=40)] struct Input {[FieldOffset(0)] public uint type;[FieldOffset(8)] public MouseInput mouse;}
    [DllImport("user32.dll",SetLastError=true)] static extern uint SendInput(uint count,Input[] inputs,int size);
    [DllImport("user32.dll")] static extern IntPtr WindowFromPhysicalPoint(Native.Point point);
    internal static bool RunningButton(Dictionary<string,object> selector) {
        return !Thumbnail(selector)&&(string)selector["control_type"]=="Button"&&
            (string)selector["class_name"]=="Taskbar.TaskListButtonAutomationPeer"&&
            ((string)selector["automation_id"]).StartsWith("Appid:",StringComparison.OrdinalIgnoreCase)&&
            Regex.IsMatch((string)selector["name"],@" - [1-9][0-9]* running window");
    }
    internal static void ValidateLiveSelector(Dictionary<string,object> recorded,Dictionary<string,object> live) {
        if(!Matches(recorded,live)||!Thumbnail(live)&&!RunningButton(live))
            throw new Exception("Taskbar identity or running state changed before activation.");
    }
    internal static void ValidateThumbnailDestination(Dictionary<string,object> route,string title) {
        if(route.ContainsKey("thumbnail")&&!Equals(((Dictionary<string,object>)route["thumbnail"])["name"],title))
            throw new Exception("Thumbnail caption does not identify the expected destination.");
    }
    internal static void ValidateCaptureScope(Dictionary<string,object> prior,Dictionary<string,object> current) {
        if(prior!=null&&!BrowserIdentity.SamePage(prior,current))
            throw new Exception("Taskbar destination browser scope changed or is incomplete. Draft preserved.");
    }
    static void ClickResolved(Item item,Action check,Action invoked) {
        check();Point point;
        if(!item.Element.TryGetClickablePoint(out point)) {var bounds=item.Element.Current.BoundingRectangle;point=new Point(bounds.Left+bounds.Width/2,bounds.Top+bounds.Height/2);}
        if(!item.Element.Current.BoundingRectangle.Contains(point))throw new Exception("Taskbar click point left its verified control.");
        // UIA clickable points and rectangles are physical desktop pixels.
        var hit=Native.GetAncestor(WindowFromPhysicalPoint(new Native.Point{X=(int)point.X,Y=(int)point.Y}),2);
        if(hit!=item.Window)throw new Exception("Taskbar item is covered. Resize or move the covering window, then retry. No input sent. Hit "+
            ObstructionDetails(hit)+"; shell "+ObstructionDetails(item.Window)+"; point "+point.X+","+point.Y+".");
        ClickPoint(point,check,invoked);
    }
    static void ClickPoint(Point point,Action check,Action invoked) {
        int left=Native.GetSystemMetrics(76),top=Native.GetSystemMetrics(77),width=Native.GetSystemMetrics(78),height=Native.GetSystemMetrics(79);
        if(width<2||height<2)throw new Exception("Virtual desktop geometry is unavailable.");
        var move=new MouseInput{x=(int)Math.Round((point.X-left)*65535/(width-1)),y=(int)Math.Round((point.Y-top)*65535/(height-1)),flags=0xC001,extra=InputTag};
        check();
        // One SendInput batch; no asynchronous held button or background click.
        var batch=new[]{new Input{mouse=move},new Input{mouse=new MouseInput{flags=2,extra=InputTag}},new Input{mouse=new MouseInput{flags=4,extra=InputTag}}};
        invoked();uint sent=SendInput(3,batch,Marshal.SizeOf(typeof(Input)));
        if(sent!=3) {
            if(sent==2)SendInput(1,new[]{batch[2]},Marshal.SizeOf(typeof(Input)));
            throw new Exception("Windows did not accept the complete taskbar gesture. Inspect before retrying.");
        }
    }
    internal sealed class Item {
        public IntPtr Window;
        public AutomationElement Element;
        public Dictionary<string,object> Selector;
        public Rect Bounds;
        public long At;
    }
    internal static string Class(IntPtr window) {
        var name=new System.Text.StringBuilder(256);Native.GetClassName(window,name,256);return name.ToString();
    }
    static string ObstructionDetails(IntPtr window) {
        // Windows can disappear between hit-testing and diagnostics. Preserve
        // the actionable refusal even when an optional detail is unavailable.
        if(window==IntPtr.Zero)return "unavailable window";
        string process="unknown process",bounds="unavailable";
        try{using(var owner=Native.ProcessFor(window))process=owner.ProcessName;}catch{}
        try{bounds=AutomationElement.FromHandle(window).Current.BoundingRectangle.ToString();}catch{}
        return process+"/"+Class(window)+" bounds "+bounds;
    }
    internal static bool Surface(IntPtr window) {
        string value=Class(window);
        return value=="Shell_TrayWnd"||value=="Shell_SecondaryTrayWnd"||value=="TaskListThumbnailWnd"||value=="XamlExplorerHostIslandWindow";
    }
    internal static bool Thumbnail(Dictionary<string,object> selector) {return (string)selector["surface"]=="TaskListThumbnailWnd"||(string)selector["surface"]=="XamlExplorerHostIslandWindow";}
    internal static void Shell(IntPtr window) {
        Native.CheckProcess(window);
        if(!Surface(window)||!String.Equals(Native.ProcessFor(window).MainModule.FileName,
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows),"explorer.exe"),StringComparison.OrdinalIgnoreCase))
            throw new Exception("Taskbar surface is not the Windows Explorer shell.");
    }
    internal static bool Matches(Dictionary<string,object> expected,Dictionary<string,object> actual) {
        foreach(string key in new[]{"surface","control_type","class_name","automation_id"})
            if(!Equals(expected[key],actual[key]))return false;
        // An AppID survives running-window count/title changes. Nameless IDs
        // and thumbnails instead require the exact witnessed accessible name.
        return ((string)expected["automation_id"]).StartsWith("Appid:",StringComparison.OrdinalIgnoreCase)&&!Thumbnail(expected)||Equals(expected["name"],actual["name"]);
    }
    internal static Item[] Read(Action check) {
        var windows=new List<IntPtr>();
        Native.EnumWindows((h,l)=>{if(Native.IsWindowVisible(h)&&Surface(h))windows.Add(h);return true;},IntPtr.Zero);
        var foreground=Native.GetForegroundWindow();if(Surface(foreground)&&!windows.Contains(foreground))windows.Add(foreground);
        var result=new List<Item>();
        foreach(var window in windows) {
            check();Shell(window);uint pid;Native.GetWindowThreadProcessId(window,out pid);
            var root=AutomationElement.FromHandle(window);
            var nodes=root.FindAll(TreeScope.Descendants,new OrCondition(
                new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Button),
                new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.ListItem)));
            if(nodes.Count>256)throw new Exception("Taskbar accessibility tree exceeds the supported bound.");
            foreach(AutomationElement node in nodes) {
                check();var current=node.Current;
                if(current.ProcessId!=pid||!current.IsEnabled||current.IsOffscreen||current.IsPassword||current.BoundingRectangle.IsEmpty)continue;
                string id=current.AutomationId,name=current.Name;
                if(String.IsNullOrWhiteSpace(id)&&String.IsNullOrWhiteSpace(name))continue;
                if(id.Length>180||name.Length>180)continue;
                result.Add(new Item{Window=window,Element=node,Bounds=current.BoundingRectangle,At=Stopwatch.GetTimestamp(),
                    Selector=new Dictionary<string,object>{{"surface",Class(window)},{"control_type",current.ControlType.ProgrammaticName.Replace("ControlType.","")},
                        {"class_name",current.ClassName},{"automation_id",id},{"name",name}}});
            }
        }
        return result.ToArray();
    }
    internal static Item Unique(IEnumerable<Item> items,Dictionary<string,object> selector) {
        var matches=items.Where(x=>Matches(selector,x.Selector)).ToArray();
        if(matches.Length!=1)throw new Exception(matches.Length==0?"Recorded taskbar item is unavailable.":"Taskbar item is ambiguous; no window selected.");
        return matches[0];
    }
    internal static Item Hit(Item[] items,IntPtr window,Native.Point point) {
        var matches=items.Where(x=>x.Window==window&&x.Bounds.Contains(new Point(point.X,point.Y))&&
            (Stopwatch.GetTimestamp()-x.At)*1000.0/Stopwatch.Frequency<=1000).ToArray();
        return matches.Length==1?matches[0]:null;
    }
    static void Invoke(Item item,Action check,Action invoked) {
        check();Shell(item.Window);var current=item.Element.Current;
        if(current.IsOffscreen||!current.IsEnabled)
            throw new Exception("Taskbar item is unavailable before activation.");
        ValidateLiveSelector(item.Selector,new Dictionary<string,object>{
            {"surface",Class(item.Window)},{"control_type",current.ControlType.ProgrammaticName.Replace("ControlType.","")},
            {"class_name",current.ClassName},{"automation_id",current.AutomationId},{"name",current.Name}});
        object pattern;check();
        if(item.Element.TryGetCurrentPattern(InvokePattern.Pattern,out pattern)){invoked();((InvokePattern)pattern).Invoke();}
        else if(item.Element.TryGetCurrentPattern(SelectionItemPattern.Pattern,out pattern)){invoked();((SelectionItemPattern)pattern).Select();}
        else {
            if(!Thumbnail(item.Selector)&&!RunningButton(item.Selector))throw new Exception("Only a running application taskbar button may receive a resolved click.");
            ClickResolved(item,check,invoked);
        }
    }
    internal static void Play(Dictionary<string,object> route,IntPtr destination,Action check,Action verifyIdentity,Action invoked,Action<object> trace=null) {
        check();verifyIdentity();
        // Clicking the active app can minimize it. Require a switch from another
        // window; do not silently replace the recorded shell action with a no-op.
        if(Native.Root(Native.GetForegroundWindow())==destination)
            throw new Exception("Taskbar replay requires a different foreground window; no toggle sent.");
        var button=(Dictionary<string,object>)route["button"];
        ValidateThumbnailDestination(route,Native.Title(destination));
        if(route.ContainsKey("thumbnail")&&Equals(((Dictionary<string,object>)route["thumbnail"])["class_name"],ThumbnailCaption.Marker)) {
            ThumbnailCaption.ValidateSelector((Dictionary<string,object>)route["thumbnail"]);ThumbnailCaption.VerifyRuntime();
        }
        var buttons=Read(check).Where(x=>!Thumbnail(x.Selector)).ToArray();
        if(trace!=null&&!buttons.Any(x=>Matches(button,x.Selector)))
            trace(new {reason="recorded taskbar item unavailable",buttons=buttons.Select(x=>x.Selector).ToArray()});
        var first=Unique(buttons,button);
        if(!RunningButton(first.Selector))throw new Exception("The recorded application is not running on the taskbar. Nothing launched.");
        check();Invoke(first,check,invoked);
        if(route.ContainsKey("thumbnail")) {
            var selector=(Dictionary<string,object>)route["thumbnail"];
            ValidateThumbnailDestination(route,Native.Title(destination));
            if(Equals(selector["class_name"],ThumbnailCaption.Marker)) {
                ThumbnailCaption.ValidateSelector(selector);
                ThumbnailCaption.Activate(Native.Title(destination),check,verifyIdentity,p=>ClickPoint(p,check,invoked),trace);
            } else {
            var wait=Stopwatch.StartNew();Item preview=null;
            while(wait.ElapsedMilliseconds<3000) {
                check();var visible=Read(check).Where(x=>Thumbnail(x.Selector)).ToArray();
                if(trace!=null&&visible.Length>0){trace(visible.Select(x=>x.Selector).ToArray());trace=null;}
                var candidates=visible.Where(x=>Matches(selector,x.Selector)).ToArray();
                if(candidates.Length>1)throw new Exception("Grouped taskbar thumbnail is ambiguous.");
                if(candidates.Length==1){preview=candidates[0];break;}
                if(Native.Root(Native.GetForegroundWindow())==destination)throw new Exception("Recorded thumbnail route changed; direct activation is not a thumbnail replay.");
                Thread.Sleep(75);
            }
            if(preview==null)throw new Exception("The shell did not expose the recorded thumbnail identity. Activation was not repeated.");
            check();verifyIdentity();Invoke(preview,check,invoked);
            }
        }
        var settle=Stopwatch.StartNew();
        while(settle.ElapsedMilliseconds<2500) {
            check();
            if(Native.Root(Native.GetForegroundWindow())==destination&&DesktopWindowState.Read(destination)!="minimized") {
                verifyIdentity();check();return;
            }
            Thread.Sleep(50);
        }
        throw new Exception("Taskbar did not activate the verified destination. Activation was not repeated.");
    }
}

partial class Capture {
    volatile TaskbarRoute.Item[] shellItems=new TaskbarRoute.Item[0];
    System.Threading.Timer shellTimer;
    int shellRefreshing;
    volatile bool shellGesture;
    TaskbarRoute.Item shellDown,pendingShellButton;
    IntPtr shellOrigin,pendingShellPopup;
    bool shellPressed;
    long pendingShellAt;
    readonly Dictionary<IntPtr,Dictionary<string,object>> shellBrowserScopes=new Dictionary<IntPtr,Dictionary<string,object>>();
    ThumbnailCaption.Observation captionObservation;
    string preparedCaptionTitle;
    IntPtr captionDestination;
    string captionStatus;
    void RefreshPendingCaption(TaskbarRoute.Item item) {
        // Called only after the caption's current pixels, shell ownership and
        // foreground surface have been verified. Waiting for OCR or the user's
        // title click must not expire an otherwise continuously verified group.
        if(pendingShellButton!=null&&pendingShellPopup!=IntPtr.Zero&&item.Window==pendingShellPopup&&
           Equals(item.Selector["class_name"],ThumbnailCaption.Marker)&&
           Equals(item.Selector["name"],preparedCaptionTitle))
            Interlocked.Exchange(ref pendingShellAt,MonotonicMs());
    }
    void PublishCaption(int epoch) {
        var pointer=physicalPointer;var item=captionObservation.Item();
        RefreshPendingCaption(item);
        bool hovered=pointer!=null&&pointer.Epoch==epoch&&pointer.Window==item.Window&&
            item.Bounds.Contains(new Point(pointer.Point.X,pointer.Point.Y));
        shellItems=hovered?new[]{item}:new TaskbarRoute.Item[0];
        string status=hovered?"thumbnail_capture_ready":"thumbnail_capture_hover";
        if(captionStatus!=status){captionStatus=status;send("diagnostic",new {kind=status,title=preparedCaptionTitle});}
    }
    void RefreshShell() {
        if(!Armed||Broken||Interlocked.CompareExchange(ref shellRefreshing,1,0)!=0)return;
        int epoch=generation;
        bool recognizingCaption=false;
        try{
            Action check=()=>{if(!Armed||Broken||epoch!=generation)throw new OperationCanceledException();};
            // Keep a verified caption fresh without a potentially slow whole-shell
            // accessibility traversal between every pixel check and publication.
            if(captionObservation!=null&&captionObservation.Current()) {
                check();PublishCaption(epoch);return;
            }
            if(captionObservation!=null){
                send("diagnostic",new {kind="thumbnail_capture_invalidated",reason=captionObservation.Failure});
                captionObservation=null;captionStatus=null;shellItems=new TaskbarRoute.Item[0];
                send("diagnostic",new {kind="thumbnail_capture_waiting"});
            }
            var items=TaskbarRoute.Read(check);
            if(ThumbnailCaption.Configured&&captionDestination!=IntPtr.Zero&&TaskbarRoute.Class(Native.GetForegroundWindow())=="XamlExplorerHostIslandWindow"&&
               !items.Any(x=>TaskbarRoute.Thumbnail(x.Selector))) {
                Action identity=()=>{uint pid;Native.GetWindowThreadProcessId(captionDestination,out pid);Native.CheckProcess(captionDestination);
                    if(!preparedWindows.ContainsKey(captionDestination)||preparedWindows[captionDestination]!=pid||Native.Title(captionDestination)!=preparedCaptionTitle)
                        throw new Exception("Prepared grouped destination changed.");};
                identity();
                if(captionObservation==null||!captionObservation.Current()) {
                    captionObservation=null;
                    recognizingCaption=true;
                    send("diagnostic",new {kind="thumbnail_capture_waiting"});
                    ThumbnailCaption.Activate(preparedCaptionTitle,check,identity,null,null,2,observation=>{check();captionObservation=observation;});
                    check();PublishCaption(epoch);
                    return;
                }
                check();items=items.Concat(new[]{captionObservation.Item()}).ToArray();
            }else captionObservation=null;
            shellItems=items;
        }
        catch(OperationCanceledException){if(epoch==generation)shellItems=new TaskbarRoute.Item[0];}
        catch(Exception error){
            if(epoch==generation){
                shellItems=new TaskbarRoute.Item[0];
                if(recognizingCaption&&Armed&&!Broken){
                    // Activate already has a bounded read-only retry. Do not silently
                    // restart OCR on every timer tick after its final refusal.
                    send("diagnostic",new {kind="thumbnail_capture_failed",reason=error.Message});
                    Interrupt("Grouped thumbnail could not be verified: "+error.Message+" Draft preserved. Stop and report this message.");
                }
            }
        }
        finally{Interlocked.Exchange(ref shellRefreshing,0);}
    }
    void StartShell(bool resume=false) {
        shellGesture=false;shellPressed=false;shellDown=pendingShellButton=null;pendingShellPopup=IntPtr.Zero;
        captionObservation=null;captionStatus=null;if(!resume){captionDestination=preparedWindow;preparedCaptionTitle=captionDestination==IntPtr.Zero?null:Native.Title(captionDestination);}
        if(!resume)shellBrowserScopes.Clear();
        shellTimer=new System.Threading.Timer(_=>RefreshShell(),null,0,250);
    }
    void StopShell() {var timer=Interlocked.Exchange(ref shellTimer,null);if(timer!=null)timer.Dispose();shellItems=new TaskbarRoute.Item[0];}
    void CaptureShell(TaskbarRoute.Item item,IntPtr origin,int epoch) {
        if(item==null)throw new Exception("Taskbar identity was not ready before the click. Draft preserved.");
        TaskbarRoute.Shell(item.Window);
        if(!TaskbarRoute.Thumbnail(item.Selector)&&!TaskbarRoute.RunningButton(item.Selector))throw new Exception("Only running application taskbar buttons can be recorded.");
        var button=TaskbarRoute.Thumbnail(item.Selector)?pendingShellButton:item;
        if(button==null||TaskbarRoute.Thumbnail(item.Selector)&&(MonotonicMs()-Interlocked.Read(ref pendingShellAt)>15000))
            throw new Exception("Thumbnail has no recent captured taskbar button. Draft preserved.");
        var wait=Stopwatch.StartNew();
        while(!Broken&&epoch==generation&&wait.ElapsedMilliseconds<1500) {
            var destination=Native.Root(Native.GetForegroundWindow());
            if(destination!=IntPtr.Zero&&!TaskbarRoute.Surface(destination)&&!Mine(destination)&&destination!=origin) {
                Native.CheckProcess(destination);
                if(!DesktopSession&&!preparedWindows.ContainsKey(destination))throw new Exception("Taskbar destination was not prepared before recording.");
                var target=Target(AutomationElement.FromHandle(destination),destination);
                var currentBrowser=target.ContainsKey("browser")?(Dictionary<string,object>)target["browser"]:null;
                Dictionary<string,object> priorBrowser;
                if(shellBrowserScopes.TryGetValue(destination,out priorBrowser))TaskbarRoute.ValidateCaptureScope(priorBrowser,currentBrowser);
                if(currentBrowser!=null)shellBrowserScopes[destination]=new Dictionary<string,object>(currentBrowser);
                target["automation_id"]="window";target["scope"]=new object[0];
                if(TaskbarRoute.Thumbnail(item.Selector)&&!Equals(item.Selector["name"],Native.Title(destination)))throw new Exception("Thumbnail caption does not identify its resulting window. Draft preserved.");
                var route=new Dictionary<string,object>{{"button",button.Selector}};
                if(TaskbarRoute.Thumbnail(item.Selector))route["thumbnail"]=item.Selector;
                if(Native.Root(Native.GetForegroundWindow())!=destination)throw new Exception("Taskbar destination changed during capture.");
                Emit("taskbar_activate",target,route,epoch);
                lastWindow=destination;lastTitle=(string)target["window_key"];
                lastBrowser=target.ContainsKey("browser")?(Dictionary<string,object>)target["browser"]:null;
                editorAnchor=null;editorAnchorTarget=null;AnchorFocusedEditor(destination);
                send("diagnostic",new {kind="taskbar_route_captured",thumbnail=route.ContainsKey("thumbnail"),destination=lastTitle});
                pendingShellButton=null;pendingShellPopup=IntPtr.Zero;shellGesture=false;return;
            }
            if(!TaskbarRoute.Thumbnail(item.Selector)&&(TaskbarRoute.Read(()=>{}).Any(x=>TaskbarRoute.Thumbnail(x.Selector))||
                ThumbnailCaption.Configured&&TaskbarRoute.Class(destination)=="XamlExplorerHostIslandWindow")) {
                if(TaskbarRoute.Class(destination)=="XamlExplorerHostIslandWindow")TaskbarRoute.Shell(destination);
                pendingShellButton=item;pendingShellPopup=destination;Interlocked.Exchange(ref pendingShellAt,MonotonicMs());
                send("diagnostic",new {kind="taskbar_group_opened",button=item.Selector});return;
            }
            Thread.Sleep(50);
        }
        throw new Exception("Taskbar did not activate a different verified window or expose thumbnails. Draft preserved.");
    }
    void FinishShellCapture() {
        if(shellGesture||shellPressed||pendingShellButton!=null) {
            send("diagnostic",new {kind="taskbar_capture_incomplete",pressed=shellPressed,group_opened=pendingShellButton!=null});
            Interrupt("Taskbar selection was not completed. No thumbnail route was saved. Review the preserved draft.");
        }
    }
}



