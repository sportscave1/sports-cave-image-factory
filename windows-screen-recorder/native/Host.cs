// Local development host. Explicitly armed capture and UIA candidate execution.
using System;
using System.Collections.Generic;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Threading;

static class Native {
    public delegate IntPtr Hook(int code, IntPtr w, IntPtr l);
    public delegate bool EnumProc(IntPtr hwnd, IntPtr param);
    [StructLayout(LayoutKind.Sequential)] public struct Point { public int X,Y; }
    [StructLayout(LayoutKind.Sequential)] public struct Mouse { public Point point; public uint data, flags, time; public UIntPtr extra; }
    [StructLayout(LayoutKind.Sequential)] public struct Key { public uint vk,scan,flags,time; public UIntPtr extra; }
    [DllImport("user32.dll")] public static extern IntPtr SetWindowsHookEx(int id,Hook cb,IntPtr module,uint thread);
    [DllImport("user32.dll")] public static extern bool UnhookWindowsHookEx(IntPtr hook);
    [DllImport("user32.dll")] public static extern IntPtr CallNextHookEx(IntPtr h,int c,IntPtr w,IntPtr l);
    [DllImport("kernel32.dll")] public static extern IntPtr GetModuleHandle(string name);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h,out uint pid);
    [DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr h,uint flags);
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(Point point);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc p,IntPtr l);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr h);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h,System.Text.StringBuilder name,int length);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h,System.Text.StringBuilder s,int n);
    [DllImport("user32.dll")] public static extern short GetAsyncKeyState(int vk);
    [DllImport("user32.dll")] public static extern uint GetDpiForWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern int GetSystemMetrics(int n);
    [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr value);
    [DllImport("advapi32.dll")] public static extern bool OpenProcessToken(IntPtr process,uint access,out IntPtr token);
    [DllImport("advapi32.dll")] public static extern bool GetTokenInformation(IntPtr token,int kind,out int value,int size,out int returned);
    [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr handle);
    public static string Title(IntPtr h) { var s=new System.Text.StringBuilder(256); GetWindowText(h,s,256); return s.ToString(); }
    public static Process ProcessFor(IntPtr h) { uint id; GetWindowThreadProcessId(h,out id); return Process.GetProcessById((int)id); }
    public static bool IsTaskbar(IntPtr h) {
        var name=new System.Text.StringBuilder(256);GetClassName(h,name,256);
        return name.ToString()=="Shell_TrayWnd"||name.ToString()=="Shell_SecondaryTrayWnd";
    }
    public static object WindowMetadata(IntPtr h) {
        var name=new System.Text.StringBuilder(256);GetClassName(h,name,256);
        string process="unavailable";try{process=ProcessFor(h).ProcessName;}catch{}
        return new {exists=IsWindow(h),visible=IsWindowVisible(h),window_class=name.ToString(),process=process,title=Title(h)};
    }
    public static IntPtr Root(IntPtr h) {
        var root=GetAncestor(h,2);if(root==IntPtr.Zero)root=h;
        var owner=GetAncestor(root,3);uint rootPid,ownerPid;
        GetWindowThreadProcessId(root,out rootPid);GetWindowThreadProcessId(owner,out ownerPid);
        return WindowIdentity.Root(root,owner,rootPid,ownerPid);
    }
    public static void CheckProcess(IntPtr h) {
        var p=ProcessFor(h); IntPtr token; int elevated,length;
        if(p.SessionId!=Process.GetCurrentProcess().SessionId || !OpenProcessToken(p.Handle,8,out token))
            throw new Exception("Cannot classify this application. Capture paused.");
        try { if(!GetTokenInformation(token,20,out elevated,4,out length)||elevated!=0) throw new Exception("Elevated applications are not supported."); }
        finally { CloseHandle(token); }
        string n=p.ProcessName.ToLowerInvariant();
        if(Title(h).IndexOf("ChatGPT",StringComparison.OrdinalIgnoreCase)>=0)
            throw new Exception("ChatGPT windows are outside the supported capture scope.");
        if(n.Contains("codex")||n.Contains("computer-use")||new[]{"chatgpt","powershell","pwsh","cmd","windowsterminal","lockapp","credentialuibroker"}.Contains(n))
            throw new Exception("This application is outside the supported capture scope.");
    }
}

class Capture {
    readonly Action<string,object> send;
    readonly Action<string> fail;
    readonly BlockingCollection<Action> queue=new BlockingCollection<Action>(128);
    readonly Stopwatch clock=Stopwatch.StartNew();
    readonly Native.Hook mouse,key;
    IntPtr mh,kh;
    public volatile bool Armed;
    public volatile bool Broken;
    public long BusySince;
    NativeMetrics metrics;
    int generation;
    IntPtr own,lastWindow;
    IntPtr preparedWindow;
    readonly Dictionary<IntPtr,uint> preparedWindows=new Dictionary<IntPtr,uint>();
    string lastTitle;
    AutomationElement field;
    AutomationElement editorAnchor;
    Dictionary<string,object> editorAnchorTarget;
    readonly PendingEditorClick pendingEditorClick=new PendingEditorClick();
    System.Windows.Rect pendingWindowBounds;
    uint pendingWindowDpi,pendingWindowPid;
    Dictionary<string,object> fieldTarget;
    long fieldAt;
    bool dirty;
    string fieldValue;
    readonly bool injected;
    int traceCount,ownExclusions;
    class WheelBurst {
        public Native.Point Point;public IntPtr Window;public int Epoch;
        public long LastAt;public bool Closed;
    }
    readonly object wheelGate=new object();
    WheelBurst wheelBurst;
    sealed class GenerationAnchor {
        public IntPtr Window;public uint Pid,Dpi;public int Epoch;public long DownAt;
        public System.Windows.Rect Bounds,WindowBounds;
        public AutomationElement Control,Document;
        public Dictionary<string,object> Target;
        public ProductGenerationResult.Witness Before;
    }
    volatile GenerationAnchor preparedGeneration;
    volatile GenerationAnchor preparedPicker;
    GenerationAnchor pendingPicker;
    bool expectedPickerDown;
    sealed class GenerationGesture { public long ReleasedAt; }
    GenerationGesture generationGesture;
    GenerationAnchor pendingGeneration;
    bool expectedGenerationDown;
    public Capture(IntPtr own,Action<string,object> send,Action<string> fail,bool injected) {
        this.own=own;this.send=send;this.fail=fail;this.injected=injected;
        mouse=OnMouse;key=OnKey;
        var worker=new Thread(()=>{foreach(var work in queue.GetConsumingEnumerable()){
            if(Broken)continue; // Never inspect queued targets after an interruption.
            Interlocked.Exchange(ref BusySince,Stopwatch.GetTimestamp());
            try { work(); } catch(Exception e){Interrupt(e is ElementNotAvailableException?"The target window disappeared.":e.Message);}
            finally{Interlocked.Exchange(ref BusySince,0);}
        }}){IsBackground=true};worker.SetApartmentState(ApartmentState.MTA);worker.Start();
    }
    void Put(Action a) { if(!Broken&&!queue.TryAdd(a)) Interrupt("Capture queue is full. Stop and save the preserved draft."); }
    public void Interrupt(string reason) { if(Broken)return; Broken=true; Armed=false; fail(reason); }
    public void Watchdog() {
        long since=Interlocked.Read(ref BusySince);
        if(since!=0 && (Stopwatch.GetTimestamp()-since)/(double)Stopwatch.Frequency>3) Interrupt("Accessibility provider did not respond. Stop to preserve the draft, then restart the candidate.");
    }
    public void Start(int epoch) {
        if(Broken&&(Interlocked.Read(ref BusySince)!=0||queue.Count!=0))throw new Exception("Restart the candidate after an accessibility interruption.");
        Broken=false;field=null;fieldTarget=null;dirty=false;editorAnchor=null;editorAnchorTarget=null;
        pendingEditorClick.Clear();
        pendingGeneration=null;expectedGenerationDown=false;
        pendingPicker=null;expectedPickerDown=false;
        generation=epoch;lastWindow=IntPtr.Zero;lastTitle=null;
        mh=Native.SetWindowsHookEx(14,mouse,Native.GetModuleHandle(null),0);
        kh=Native.SetWindowsHookEx(13,key,Native.GetModuleHandle(null),0);
        if(mh==IntPtr.Zero||kh==IntPtr.Zero) {Detach();throw new Exception("Windows capture hooks could not be armed.");}
        Armed=true;
        metrics=NativeMetrics.Begin("recording");
        clock.Start();
    }
    public void PrepareRecord(IntPtr selected) {
        if(Interlocked.Read(ref BusySince)!=0||queue.Count!=0)throw new Exception("Wait for the accessibility check to finish.");
        Broken=false;
        Put(()=>{selected=Native.Root(selected);var target=Target(AutomationElement.FromHandle(selected),selected);
            preparedWindows.Clear();
            Native.EnumWindows((h,l)=>{
                if(preparedWindows.Count>=512)return false;
                if(Native.IsWindowVisible(h)){uint pid;Native.GetWindowThreadProcessId(h,out pid);preparedWindows[Native.Root(h)]=pid;}
                return true;
            },IntPtr.Zero);
            preparedWindow=selected;PrepareGeneration(selected);clock.Reset();traceCount=0;ownExclusions=0;send("record",new {window=target});});
    }
    public void Detach(bool finishMetrics=true) {
        Armed=false;
        clock.Stop();
        if(mh!=IntPtr.Zero)Native.UnhookWindowsHookEx(mh);
        if(kh!=IntPtr.Zero)Native.UnhookWindowsHookEx(kh);
        mh=kh=IntPtr.Zero;
        if(finishMetrics)FinishMetrics();
    }
    void FinishMetrics() {
        var completed=Interlocked.Exchange(ref metrics,null);
        if(completed!=null)completed.Finish(send);
    }
    public void Barrier(string command,string requestId=null) {
        CloseWheelBurst();
        Detach(false);
        if(Broken){FinishMetrics();send(command,new {request_id=requestId});return;}
        Put(()=>{Flush();FinishMetrics();send("diagnostic",new {kind="capture_barrier",toolbar_inputs_excluded=ownExclusions});send(command,new {request_id=requestId});});
    }
    bool Mine(IntPtr h) { uint id;Native.GetWindowThreadProcessId(h,out id);return WindowIdentity.IsToolbar(id,(uint)Process.GetCurrentProcess().Id); }
    IntPtr OnMouse(int c,IntPtr w,IntPtr l) {
        if(c>=0&&Armed&&(w.ToInt32()==0x201||w.ToInt32()==0x202||w.ToInt32()==0x20A||w.ToInt32()==0x205)){
            var m=(Native.Mouse)Marshal.PtrToStructure(l,typeof(Native.Mouse));
            if(injected||(m.flags&1)==0){
                var hit=Native.WindowFromPoint(m.point);var window=Native.Root(hit);
                if(Mine(window)){if(w.ToInt32()==0x202)ownExclusions++;return Native.CallNextHookEx(IntPtr.Zero,c,w,l);}
                if(w.ToInt32()==0x201){var point=m.point;int epoch=generation;long at=MonotonicMs();
                    var gesture=new GenerationGesture();generationGesture=gesture;
                    Put(()=>{SnapshotGeneration(point,window,epoch,at,gesture);SnapshotGeneration(point,window,epoch,at,gesture,true);});}
                else if(w.ToInt32()==0x20A){QueueWheel(m.point,window,generation);}
                else if(w.ToInt32()==0x202){CloseWheelBurst();var point=m.point;int epoch=generation;
                    var gesture=generationGesture;generationGesture=null;
                    if(gesture!=null)Interlocked.Exchange(ref gesture.ReleasedAt,MonotonicMs());
                    var foreground=Native.Root(Native.GetForegroundWindow());
                    Put(()=>{TraceWindow("mouse",window,foreground,hit);Flush();if(!CompleteGeneration(point,window,epoch,true)&&!CompleteGeneration(point,window,epoch))Click(point,window,epoch);});}
                else {CloseWheelBurst();Put(()=>{Flush();Interrupt("Secondary clicks are not yet supported. Draft preserved.");});}
            }
        }
        return Native.CallNextHookEx(IntPtr.Zero,c,w,l);
    }
    void CloseWheelBurst(){lock(wheelGate){if(wheelBurst!=null)wheelBurst.Closed=true;}}
    void PrepareGeneration(IntPtr window) {
        PreparePicker(window);
        preparedGeneration=null;
        var process=Native.ProcessFor(window);
        if(!String.Equals(Path.GetFileName(process.MainModule.FileName),"msedge.exe",StringComparison.OrdinalIgnoreCase))return;
        var root=AutomationElement.FromHandle(window);
        if(root.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.AutomationIdProperty,ProductGenerationResult.Container)).Count==0)return;
        var buttons=root.FindAll(TreeScope.Descendants,new AndCondition(
            new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Button),
            new PropertyCondition(AutomationElement.NameProperty,"Generate mockups")));
        if(buttons.Count>16)throw new Exception("Generate is ambiguous. Prepare one product page before Record.");
        foreach(AutomationElement button in buttons) {
            if(!button.Current.IsEnabled||button.Current.IsOffscreen)continue;
            var target=Target(button,window);
            if(!ProductGenerationResult.Supports(target))continue;
            if(preparedGeneration!=null)throw new Exception("Generate is ambiguous. Prepare one product page before Record.");
            preparedGeneration=new GenerationAnchor{Window=window,Pid=(uint)process.Id,Control=button,Target=target,
                Document=ProductGenerationResult.Document(button,window,(uint)process.Id),
                Before=ProductGenerationResult.Read(button,window,(uint)process.Id),
                Bounds=button.Current.BoundingRectangle,WindowBounds=root.Current.BoundingRectangle,Dpi=Native.GetDpiForWindow(window)};
        }
        send("diagnostic",new {kind="generation_capture_prepared",visible_generate_anchor=preparedGeneration!=null});
    }
    void PreparePicker(IntPtr window) {
        preparedPicker=null;
        var process=Native.ProcessFor(window);
        if(!String.Equals(Path.GetFileName(process.MainModule.FileName),"msedge.exe",StringComparison.OrdinalIgnoreCase))return;
        var root=AutomationElement.FromHandle(window);
        var buttons=root.FindAll(TreeScope.Descendants,new AndCondition(
            new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Button),
            new PropertyCondition(AutomationElement.AutomationIdProperty,"choose"),
            new PropertyCondition(AutomationElement.NameProperty,"Choose PSD")));
        foreach(AutomationElement button in buttons) {
            if(button.Current.IsOffscreen||!button.Current.IsEnabled)continue;
            var document=ProductPickerResult.Document(button,window,(uint)process.Id);
            if(document==null)continue;
            var target=Target(button,window);
            if(!ProductPickerResult.Supports(target)||ProductPickerResult.Open(document,window,(uint)process.Id))continue;
            if(preparedPicker!=null)throw new Exception("Prepare one Product Uploads PSD picker before Record.");
            preparedPicker=new GenerationAnchor{Window=window,Pid=(uint)process.Id,Control=button,Target=target,Document=document,
                Bounds=button.Current.BoundingRectangle,WindowBounds=root.Current.BoundingRectangle,Dpi=Native.GetDpiForWindow(window)};
        }
    }
    void SnapshotGeneration(Native.Point point,IntPtr window,int epoch,long at,GenerationGesture gesture,bool picker=false) {
        if(picker){pendingPicker=null;expectedPickerDown=false;}else{pendingGeneration=null;expectedGenerationDown=false;}
        var prepared=picker?preparedPicker:preparedGeneration;
        if(prepared==null||window!=prepared.Window||!prepared.Bounds.Contains(new System.Windows.Point(point.X,point.Y)))return;
        if(picker)expectedPickerDown=true;else expectedGenerationDown=true;
        if(Interlocked.Read(ref gesture.ReleasedAt)!=0)
            throw new Exception("Generate click completed before its target could be confirmed. Draft preserved.");
        InputWindow(window);uint pid;Native.GetWindowThreadProcessId(window,out pid);
        if(epoch!=generation||pid!=prepared.Pid||Native.GetDpiForWindow(window)!=prepared.Dpi||
            !AutomationElement.FromHandle(window).Current.BoundingRectangle.Equals(prepared.WindowBounds)||
            MonotonicMs()-at>250)throw new Exception("Generate changed before its click target could be confirmed. Draft preserved.");
        Privacy(prepared.Control);
        var bounds=prepared.Control.Current.BoundingRectangle;
        if(!bounds.Contains(new System.Windows.Point(point.X,point.Y)))
            throw new Exception("Generate moved before the physical click. Prepare the page and Record again.");
        var target=prepared.Target;
        if(prepared.Control.Current.ProcessId!=pid||prepared.Control.Current.Name!=(string)target["name"]||
            prepared.Control.Current.AutomationId!=(string)target["automation_id"])
            throw new Exception("Generate control identity changed before the physical click. Draft preserved.");
        var before=prepared.Before;
        if((!picker&&before==null)||prepared.Control.Current.ControlType!=ControlType.Button||
            MonotonicMs()-at>250||Interlocked.Read(ref gesture.ReleasedAt)!=0)
            throw new Exception("Generate changed before its click target could be confirmed. Draft preserved.");
        var pending=new GenerationAnchor{Window=window,Pid=pid,Dpi=prepared.Dpi,Bounds=bounds,
            WindowBounds=prepared.WindowBounds,Epoch=epoch,DownAt=at,Target=target,Before=before,
            Document=prepared.Document};
        if(picker)pendingPicker=pending;else pendingGeneration=pending;
    }
    bool CompleteGeneration(Native.Point point,IntPtr window,int epoch,bool picker=false) {
        if(!(picker?expectedPickerDown:expectedGenerationDown))return false;
        var anchor=picker?pendingPicker:pendingGeneration;
        if(picker){expectedPickerDown=false;pendingPicker=null;}else{expectedGenerationDown=false;pendingGeneration=null;}
        if(anchor==null)throw new Exception("Generate was not identified before its click. Draft preserved.");
        InputWindow(window);uint pid;Native.GetWindowThreadProcessId(window,out pid);
        if(anchor.Window!=window||anchor.Epoch!=epoch||generation!=epoch||pid!=anchor.Pid||Native.Root(Native.GetForegroundWindow())!=window||
            Native.GetDpiForWindow(window)!=anchor.Dpi||Native.Title(window)!=(string)anchor.Target["window_key"]||
            !AutomationElement.FromHandle(window).Current.BoundingRectangle.Equals(anchor.WindowBounds)||
            !anchor.Bounds.Contains(new System.Windows.Point(point.X,point.Y))||MonotonicMs()-anchor.DownAt>2000)
            throw new Exception("Generate click identity or timing changed. Draft preserved.");
        var wait=Stopwatch.StartNew();
        while(!Broken&&wait.ElapsedMilliseconds<1500) {
            InputWindow(window);
            if(picker) {
                if(ProductPickerResult.Open(anchor.Document,window,pid)) {
                    WindowAction(window,epoch,(string)anchor.Target["window_key"]);Emit("invoke",anchor.Target,null,epoch);
                    send("diagnostic",new {kind="psd_picker_click_acknowledged",pre_click_identity_verified=true,modal_verified=true});
                    preparedPicker=null;return true;
                }
                Thread.Sleep(25);continue;
            }
            var after=ProductGenerationResult.ReadForDocument(anchor.Document,window,pid);
            if(ProductGenerationResult.Acknowledged(anchor.Before,after)) {
                WindowAction(window,epoch,(string)anchor.Target["window_key"]);Emit("invoke",anchor.Target,null,epoch);
                send("diagnostic",new {kind="generation_click_acknowledged",pre_click_identity_verified=true,fresh_application_acknowledgement=true});
                preparedGeneration=null;return true;
            }
            if(after!=null&&after.Receipt!=anchor.Before.Receipt&&(after.State=="failed"||after.State=="changed"))
                throw new Exception("Generate failed or its product details changed. Draft preserved.");
            Thread.Sleep(25);
        }
        throw new Exception("Generate click was not acknowledged by the prepared product page. Draft preserved.");
    }
    void QueueWheel(Native.Point point,IntPtr window,int epoch) {
        WheelBurst burst;
        lock(wheelGate){
            if(wheelBurst!=null&&!wheelBurst.Closed&&wheelBurst.Window==window&&wheelBurst.Epoch==epoch&&
               wheelBurst.Point.X==point.X&&wheelBurst.Point.Y==point.Y){wheelBurst.LastAt=MonotonicMs();return;}
            if(wheelBurst!=null)wheelBurst.Closed=true;
            burst=new WheelBurst(){Point=point,Window=window,Epoch=epoch,LastAt=MonotonicMs()};wheelBurst=burst;
        }
        Put(()=>{Flush();CaptureScroll(burst);});
    }
    void CaptureScroll(WheelBurst burst) {
        var wait=Stopwatch.StartNew();
        while(!Broken){
            lock(wheelGate){if(burst.Closed||MonotonicMs()-burst.LastAt>=80||wait.ElapsedMilliseconds>=300){burst.Closed=true;break;}}
            Thread.Sleep(10);
        }
        if(Broken)return;
        InputWindow(burst.Window);
        var e=AutomationElement.FromPoint(new System.Windows.Point(burst.Point.X,burst.Point.Y));
        var page=e.Current.ControlType==ControlType.Document&&e.Current.AutomationId=="RootWebArea"?e:null;
        uint pid;Native.GetWindowThreadProcessId(burst.Window,out pid);
        var inspected=new List<object>();
        // Scroll containers can be layout elements omitted from Control View.
        // Follow the provider's raw ancestry, still bounded to the selected app.
        for(int depth=0;e!=null&&depth<16;depth++,e=TreeWalker.RawViewWalker.GetParent(e)){
            if(e.Current.ProcessId!=pid)throw new Exception("Scroll target left the intended application. Draft preserved.");
            Privacy(e);object pattern;
            bool supported=e.TryGetCurrentPattern(ScrollPattern.Pattern,out pattern);
            var bounds=e.Current.BoundingRectangle;
            inspected.Add(new {control_type=e.Current.ControlType.ProgrammaticName,
                automation_id=Safe(e.Current.AutomationId),is_control=e.Current.IsControlElement,
                contains_pointer=bounds.Contains(new System.Windows.Point(burst.Point.X,burst.Point.Y)),
                scroll_pattern=supported});
            if(supported){
                var scroll=((ScrollPattern)pattern).Current;
                if(!scroll.HorizontallyScrollable&&!scroll.VerticallyScrollable)continue;
                var target=Target(e,burst.Window);WindowAction(burst.Window,burst.Epoch);
                Emit("scroll",target,new Dictionary<string,object>{
                    {"horizontal",scroll.HorizontallyScrollable?scroll.HorizontalScrollPercent:ScrollPattern.NoScroll},
                    {"vertical",scroll.VerticallyScrollable?scroll.VerticalScrollPercent:ScrollPattern.NoScroll}},burst.Epoch);
                return;
            }
            if(e.Current.NativeWindowHandle==burst.Window.ToInt32())break;
        }
        // Chromium sometimes reports only the document for a wheel hit, while
        // the actual overflow container is a raw descendant. Search only that
        // page, only branches under the pointer, and require one eligible target.
        if(page!=null) {
            var point=new System.Windows.Point(burst.Point.X,burst.Point.Y);
            var search=new ScrollTargetSearch<AutomationElement>(
                node=>node.Current.ProcessId==pid&&!node.Current.IsOffscreen&&node.Current.BoundingRectangle.Contains(point),
                node=>{object candidate;if(!node.TryGetCurrentPattern(ScrollPattern.Pattern,out candidate))return false;
                    var position=((ScrollPattern)candidate).Current;return position.HorizontallyScrollable||position.VerticallyScrollable;},
                RawChildren);
            var container=search.Find(page);
            if(container!=null) {
                if(Broken)return;
                if(Native.Root(Native.GetForegroundWindow())!=burst.Window)
                    throw new Exception("Focus changed while identifying the scroll container. Draft preserved.");
                var target=Target(container,burst.Window);object pattern;
                if(!container.TryGetCurrentPattern(ScrollPattern.Pattern,out pattern))
                    throw new Exception("The scroll container changed before its position was read. Draft preserved.");
                var position=((ScrollPattern)pattern).Current;
                if(!position.HorizontallyScrollable&&!position.VerticallyScrollable)
                    throw new Exception("The scroll container is no longer scrollable. Draft preserved.");
                WindowAction(burst.Window,burst.Epoch);
                Emit("scroll",target,new Dictionary<string,object>{
                    {"horizontal",position.HorizontallyScrollable?position.HorizontalScrollPercent:ScrollPattern.NoScroll},
                    {"vertical",position.VerticallyScrollable?position.VerticalScrollPercent:ScrollPattern.NoScroll}},burst.Epoch);
                send("diagnostic",new {kind="scroll_descendant_resolved",control_type=target["control_type"],automation_id=target["automation_id"]});
                return;
            }
        }
        send("diagnostic",new {kind="scroll_position_unavailable",ancestors=inspected,
            window_title=Safe(Native.Title(burst.Window))});
        throw new Exception("The scrolled control has no supported scroll position. Draft preserved.");
    }
    static IEnumerable<AutomationElement> RawChildren(AutomationElement parent) {
        for(var child=TreeWalker.RawViewWalker.GetFirstChild(parent);child!=null;child=TreeWalker.RawViewWalker.GetNextSibling(child))
            yield return child;
    }
    IntPtr OnKey(int c,IntPtr w,IntPtr l) {
        if(c>=0&&Armed&&!Mine(Native.Root(Native.GetForegroundWindow()))&&(w.ToInt32()==0x101||w.ToInt32()==0x105)){
            var k=(Native.Key)Marshal.PtrToStructure(l,typeof(Native.Key));
            if(injected||(k.flags&16)==0){
                if(k.vk==16||k.vk==17||k.vk==18||k.vk==91||k.vk==92||(k.vk>=160&&k.vk<=165))return Native.CallNextHookEx(IntPtr.Zero,c,w,l);
                CloseWheelBurst();
                var window=Native.Root(Native.GetForegroundWindow());int epoch=generation;
                long observed=Stopwatch.GetTimestamp();
                bool ctrl=(Native.GetAsyncKeyState(17)&0x8000)!=0;
                bool alt=(Native.GetAsyncKeyState(18)&0x8000)!=0;
                bool shortcut=ctrl||alt;
                bool editShortcut=ctrl&&!alt&&(k.vk==86||k.vk==88);
                bool selectAll=ctrl&&!alt&&k.vk==65;
                bool tab=k.vk==9;
                Put(()=>{if(tab){Flush();AnchorFocusedEditor(window);return;}if(selectAll)return;if(shortcut&&!editShortcut){Flush();Interrupt("This keyboard shortcut is not yet supported. Draft preserved.");return;}
                    if((Stopwatch.GetTimestamp()-observed)/(double)Stopwatch.Frequency>0.25)throw new Exception("Text observation was delayed. Capture stopped rather than reading a later value.");
                    TraceWindow("text",window,window);TextIntent(window,epoch);});
            }
        }
        return Native.CallNextHookEx(IntPtr.Zero,c,w,l);
    }
    internal static string Safe(string s) {
        if(s==null||s.Length>2000||System.Text.RegularExpressions.Regex.IsMatch(s,@"password|passwd|credential|secret|token|authorization|one.?time|api.?key",System.Text.RegularExpressions.RegexOptions.IgnoreCase))
            throw new Exception("Protected or unclassified control. Capture suspended before reading its value.");
        return s;
    }
    void Privacy(AutomationElement e, bool reading=false) {
        object p=e.GetCurrentPropertyValue(AutomationElement.IsPasswordProperty,true);
        bool fieldType=e.Current.ControlType==ControlType.Edit||e.Current.ControlType==ControlType.Document;
        if((p is bool&&(bool)p)||((reading||fieldType)&&!(p is bool)))throw new Exception("Protected or unknown text field excluded before value collection.");
        Safe(e.Current.AutomationId);Safe(e.Current.Name);
        if(!e.Current.IsEnabled)throw new Exception("The target is disabled.");
    }
    internal static bool SafeAnonymousHost(AutomationElement e) {
        object password=e.GetCurrentPropertyValue(AutomationElement.IsPasswordProperty,true);
        return !(password is bool&&(bool)password)&&e.Current.IsEnabled;
    }
    Dictionary<string,object> Target(AutomationElement e,IntPtr h) {
        Native.CheckProcess(h);Privacy(e);
        var proc=Native.ProcessFor(h);
        string title=Safe(Native.Title(h));
        string id=Safe(e.Current.AutomationId),name=Safe(e.Current.Name);
        if(id.Length==0&&name.Length==0)throw new Exception("This control has no reliable identity. Draft preserved.");
        if(title.Length==0)throw new Exception("This window has no document identity.");
        var scope=new List<object>();
        bool productPicker=ProductPickerResult.KnownButton(proc.MainModule.FileName,e.Current.ControlType.ProgrammaticName.Replace("ControlType.",""),id,name);
        int ancestryLimit=productPicker?ProductPickerResult.AncestryLimit:16;
        bool productCopy=ProductCopyResult.KnownButton(proc.MainModule.FileName,e.Current.ControlType.ProgrammaticName.Replace("ControlType.",""),id,name),hostSkipped=false;
        bool generation=ProductGenerationResult.KnownButton(proc.MainModule.FileName,e.Current.ControlType.ProgrammaticName.Replace("ControlType.",""),name)&&
            ProductGenerationResult.Read(e,h,(uint)proc.Id)!=null;
        bool generationLayoutSkipped=false;
        bool reachedRoot=e.Current.NativeWindowHandle==h.ToInt32();
        var parent=reachedRoot?null:TreeWalker.ControlViewWalker.GetParent(e);
        for(int depth=0;parent!=null&&depth<ancestryLimit;depth++){
            if(parent.Current.NativeWindowHandle==h.ToInt32()){reachedRoot=true;break;}
            if(parent.Current.ProcessId!=proc.Id)throw new Exception("Control ancestry left the intended application.");
            if(generation&&!generationLayoutSkipped&&ProductGenerationResult.LayoutBoundary(scope.Count,
                parent.Current.ControlType.ProgrammaticName.Replace("ControlType.",""),parent.Current.AutomationId)) {
                if(!SafeAnonymousHost(parent))throw new Exception("Protected or unavailable generation layout. Draft preserved.");
                generationLayoutSkipped=true;parent=TreeWalker.ControlViewWalker.GetParent(parent);continue;
            }
            if(productCopy&&!hostSkipped&&ProductCopyResult.HasFrameAnchors(scope)&&
               ProductCopyResult.HostBoundary(scope.Count,parent.Current.ControlType.ProgrammaticName.Replace("ControlType.",""),parent.Current.AutomationId)) {
                if(!SafeAnonymousHost(parent))throw new Exception("Protected or unavailable component host. Draft preserved.");
                hostSkipped=true;parent=TreeWalker.ControlViewWalker.GetParent(parent);continue;
            }
            Privacy(parent);
            string parentId=Safe(parent.Current.AutomationId),parentName=Safe(parent.Current.Name);
            if(parentId.Length>0||parentName.Length>0)scope.Add(new Dictionary<string,object>{
                {"control_type",parent.Current.ControlType.ProgrammaticName.Replace("ControlType.","")},
                {"automation_id",parentId},{"name",parentName}});
            parent=TreeWalker.ControlViewWalker.GetParent(parent);
            if(depth==ancestryLimit-1)throw new Exception("Control ancestry exceeds the supported bound.");
        }
        if(!reachedRoot)throw new Exception("Control ancestry does not reach the intended window. Draft preserved.");
        var target=new Dictionary<string,object>{{"app",proc.MainModule.FileName},{"window_key",title},{"scope",scope},
            {"control_type",e.Current.ControlType.ProgrammaticName.Replace("ControlType.","")},
            {"automation_id",id},{"name",name}};
        if(ProductPickerResult.KnownButton(proc.MainModule.FileName,(string)target["control_type"],id,name)&&
            ProductPickerResult.Document(e,h,(uint)proc.Id)!=null)target["postcondition"]=ProductPickerResult.Contract;
        if(generation) {
            if(!ProductGenerationResult.StableScope(scope))throw new Exception("Generation scope is not supported. Draft preserved.");
            target["postcondition"]=ProductGenerationResult.Contract;
        }
        return target;
    }
    void WindowAction(IntPtr h,int epoch,string anchoredTitle=null) {
        if(lastWindow==IntPtr.Zero&&preparedWindow!=IntPtr.Zero&&h!=preparedWindow)
            throw new Exception("Start in the selected prepared window. Stop and save, then select the intended window.");
        string title=anchoredTitle??Native.Title(h);
        if(lastWindow==h&&lastTitle==title)return;
        Native.CheckProcess(h);
        var root=AutomationElement.FromHandle(h);
        var target=Target(root,h);target["automation_id"]="window";target["window_key"]=title;target["name"]=title;
        Emit("focus_window",target,null,epoch);lastWindow=h;lastTitle=title;preparedWindow=IntPtr.Zero;
    }
    void InputWindow(IntPtr h) {
        if(!WindowIdentity.InitialMatches(preparedWindow,h))
            throw new Exception("Input reached a different window from the selected prepared window. Draft preserved; window details recorded.");
        Native.CheckProcess(h);
    }
    void TraceWindow(string source,IntPtr actual,IntPtr foreground,IntPtr hit=default(IntPtr)) {
        if(source!="mouse"&&traceCount++>=8)return;
        send("diagnostic",new {kind="window_identity",source=source,
            selected_root_matches=preparedWindow==IntPtr.Zero||actual==preparedWindow,
            foreground_matches_input_root=foreground==actual,
            input_window_title=Native.Title(actual),foreground_title=Native.Title(foreground),
            input_window=Native.WindowMetadata(actual),selected_window=Native.WindowMetadata(preparedWindow),
            hit_window=Native.WindowMetadata(hit),hit_parent_root=Native.WindowMetadata(Native.GetAncestor(hit,2)),
            input_parent_root=Native.WindowMetadata(Native.GetAncestor(actual,2)),
            input_owner_root=Native.WindowMetadata(Native.GetAncestor(actual,3))});
    }
    void Emit(string kind,Dictionary<string,object> target,object value,int epoch) {
        if(Broken)return;
        var caps=new Dictionary<string,string>{{"invoke","uia.invoke.v1"},{"set_text","uia.value.v1"},{"select","uia.selection.v1"},{"toggle","uia.toggle.v1"},{"focus_window","windows.focus.v1"},{"expand","uia.expand.v1"},{"scroll","uia.scroll.v1"}};
        var a=new Dictionary<string,object>{{"version",2},{"kind",kind},{"requires",new[]{caps[kind].Replace(".v1",".v2")}},{"target",target},{"timeout_ms",8000},{"observed_ms",clock.ElapsedMilliseconds}};
        if(kind=="invoke"&&ProductGenerationResult.Supports(target))a["timeout_ms"]=30000;
        if(value!=null)a["value"]=value;
        send("event",new {generation=epoch,privacy="safe",action=a});
    }
    void Click(Native.Point p,IntPtr h,int epoch) {
        if(Broken)return;
        if(Native.IsTaskbar(h)){
            CaptureTaskbarSwitch(h,epoch);
            return;
        }
        InputWindow(h);
        var e=AutomationElement.FromPoint(new System.Windows.Point(p.X,p.Y));
        uint expectedPid;Native.GetWindowThreadProcessId(h,out expectedPid);
        if(e.Current.ProcessId!=expectedPid)throw new Exception("The intended window is obscured or changed focus. Capture stopped.");
        if((e.Current.ControlType==ControlType.Pane||e.Current.ControlType==ControlType.Document||e.Current.ControlType==ControlType.Edit||e.Current.ControlType==ControlType.Text)
            &&WaitForClickedEditor(p,h,expectedPid)){
            send("diagnostic",new {kind="editor_focus_click",window_title=Native.Title(h),resolution="focused editor contains click; no value read"});
            return;
        }
        var linked=FocusedSemanticControl(p,h,expectedPid);
        if(linked!=null)e=linked;
        else if(e.Current.ControlType==ControlType.Document&&e.Current.AutomationId=="RootWebArea") {
            var pointed=PointedSemanticControl(e,p,h,expectedPid,epoch);
            if(pointed!=null)e=pointed;
        }
        var seen=new List<string>();
        for(int i=0;i<16&&e!=null;i++,e=TreeWalker.RawViewWalker.GetParent(e)){
            if(e.Current.ProcessId!=expectedPid)throw new Exception("Clicked control ancestry left the intended application. Draft preserved.");
            seen.Add(e.Current.ControlType.ProgrammaticName);
            Privacy(e);object pattern;
            if(e.Current.ControlType==ControlType.Edit||e.Current.ControlType==ControlType.Document){
                if(e.Current.AutomationId=="RootWebArea")
                {
                    var focused=AutomationElement.FocusedElement;
                    if(focused!=null&&focused.Current.ControlType!=ControlType.Edit&&
                       focused.Current.ControlType!=ControlType.Document&&focused.Current.ControlType!=ControlType.Pane&&
                       focused.Current.ControlType!=ControlType.Text) {
                        send("diagnostic",new {kind="unresolved_semantic_click",control_type=focused.Current.ControlType.ProgrammaticName,
                            focused_process_matches=focused.Current.ProcessId==expectedPid,
                            contains_click=EditorClickTarget.Matches(new System.Windows.Point(p.X,p.Y),focused.Current.BoundingRectangle,System.Windows.Rect.Empty,false)});
                        Interrupt("The clicked control could not be identified at the click location. Draft preserved; no page contents were read.");
                        return;
                    }
                    // The editor may be published only once real typing begins.
                    // Retain the unresolved click; never anchor/read RootWebArea.
                    editorAnchor=null;editorAnchorTarget=null;
                    pendingEditorClick.Begin(h,p.X,p.Y,epoch,MonotonicMs());
                    pendingWindowBounds=AutomationElement.FromHandle(h).Current.BoundingRectangle;
                    pendingWindowDpi=Native.GetDpiForWindow(h);pendingWindowPid=expectedPid;
                    send("diagnostic",new {kind="editor_focus_pending",window_title=Native.Title(h),control_types=seen,
                        focused_type=focused==null?null:focused.Current.ControlType.ProgrammaticName,
                        focused_process_matches=focused!=null&&focused.Current.ProcessId==expectedPid,
                        linked_label_available=focused!=null&&focused.GetCurrentPropertyValue(AutomationElement.LabeledByProperty,true) is AutomationElement,
                        resolution="Awaiting matching editor on input; no value read"});
                    return;
                }
                // Focus alone is not a text edit. Never read a field until input intent.
                AnchorEditor(e,h);
                return;
            }
            if(e.TryGetCurrentPattern(TogglePattern.Pattern,out pattern)){
                if(((TogglePattern)pattern).Current.ToggleState==ToggleState.Indeterminate)throw new Exception("Indeterminate toggles are not supported. Draft preserved.");
                var t=Target(e,h);WindowAction(h,epoch);Emit("toggle",t,((TogglePattern)pattern).Current.ToggleState==ToggleState.On,epoch);return;
            }
            if(e.TryGetCurrentPattern(SelectionItemPattern.Pattern,out pattern)){
                if(!((SelectionItemPattern)pattern).Current.IsSelected)throw new Exception("The clicked option was not selected. Draft preserved.");
                var t=Target(e,h);WindowAction(h,epoch);Emit("select",t,Safe(e.Current.Name),epoch);return;
            }
            if(e.TryGetCurrentPattern(ExpandCollapsePattern.Pattern,out pattern)){
                Thread.Sleep(50);
                var expanded=((ExpandCollapsePattern)pattern).Current.ExpandCollapseState;
                if(expanded!=ExpandCollapseState.Expanded&&expanded!=ExpandCollapseState.Collapsed)
                    throw new Exception("This menu has no definite open/closed state. Draft preserved.");
                var t=Target(e,h);WindowAction(h,epoch);Emit("expand",t,expanded==ExpandCollapseState.Expanded,epoch);return;
            }
            if(e.TryGetCurrentPattern(InvokePattern.Pattern,out pattern)){
                var t=Target(e,h);WindowAction(h,epoch);Emit("invoke",t,null,epoch);return;
            }
        }
        send("diagnostic",new {kind="unsupported_click",control_types=seen,window_title=Native.Title(h),
            foreground_title=Native.Title(Native.Root(Native.GetForegroundWindow()))});
        Interrupt("This clicked control is not supported ("+String.Join(", ",seen.ToArray())+"). Draft preserved.");
    }
    AutomationElement PointedSemanticControl(AutomationElement page,Native.Point point,IntPtr h,uint expectedPid,int epoch) {
        var location=new System.Windows.Point(point.X,point.Y);
        var bounds=AutomationElement.FromHandle(h).Current.BoundingRectangle;uint dpi=Native.GetDpiForWindow(h);
        var search=new ScrollTargetSearch<AutomationElement>(
            node=>node.Current.ProcessId==expectedPid&&!node.Current.IsOffscreen&&node.Current.BoundingRectangle.Contains(location),
            node=>{object pattern;return node.TryGetCurrentPattern(TogglePattern.Pattern,out pattern)||
                node.TryGetCurrentPattern(SelectionItemPattern.Pattern,out pattern)||
                node.TryGetCurrentPattern(ExpandCollapsePattern.Pattern,out pattern)||
                (node.Current.ControlType==ControlType.Button&&node.TryGetCurrentPattern(InvokePattern.Pattern,out pattern));},
            RawChildren,256,16,"Clicked control",500);
        var control=search.Find(page);
        if(control==null) {
            send("diagnostic",new {kind="pointer_semantic_absent",resolution="No supported semantic control uniquely exposed under the physical click"});
            return null;
        }
        // Do not turn a click on a disabled control into an action later.
        // Target/Privacy below must accept its current enabled state.
        if(Broken)return null;
        uint pid;Native.GetWindowThreadProcessId(h,out pid);
        if(epoch!=generation||pid!=expectedPid||Native.Root(Native.GetForegroundWindow())!=h||
           Native.GetDpiForWindow(h)!=dpi||AutomationElement.FromHandle(h).Current.BoundingRectangle!=bounds||
           control.Current.IsOffscreen||!control.Current.BoundingRectangle.Contains(location))
            throw new Exception("The clicked control or its window changed before identification. Draft preserved.");
        var target=Target(control,h);
        send("diagnostic",new {kind="pointer_semantic_resolved",control_type=target["control_type"],
            automation_id=target["automation_id"],resolution="Unique supported control under physical click; full ancestry validated"});
        return control;
    }
    AutomationElement FocusedSemanticControl(Native.Point point,IntPtr h,uint expectedPid) {
        if(Native.Root(Native.GetForegroundWindow())!=h)return null;
        var control=AutomationElement.FocusedElement;
        if(control==null||control.Current.ProcessId!=expectedPid||!control.Current.HasKeyboardFocus||control.Current.IsOffscreen)return null;
        // Chromium can hit-test an embedded component as RootWebArea even
        // after publishing a focused semantic control. Focus alone is
        // insufficient: require the physical click inside it and ancestry.
        object pattern;
        bool stateful=control.TryGetCurrentPattern(TogglePattern.Pattern,out pattern)||
            control.TryGetCurrentPattern(SelectionItemPattern.Pattern,out pattern)||
            control.TryGetCurrentPattern(ExpandCollapsePattern.Pattern,out pattern);
        bool button=control.Current.ControlType==ControlType.Button&&control.TryGetCurrentPattern(InvokePattern.Pattern,out pattern);
        if((stateful||button)&&
           EditorClickTarget.Matches(new System.Windows.Point(point.X,point.Y),control.Current.BoundingRectangle,System.Windows.Rect.Empty,false)) {
            Target(control,h);
            send("diagnostic",new {kind="focused_semantic_click",control_type=control.Current.ControlType.ProgrammaticName,
                automation_id=Safe(control.Current.AutomationId),control_name=Safe(control.Current.Name),
                window_title=Safe(Native.Title(h)),resolution="physical click inside focused semantic control; ancestry validated"});
            return control;
        }
        // A label may focus a checkbox/radio without its text being a descendant
        // of that input. Accept only the provider's explicit relationship.
        if(!stateful)return null;
        var label=control.GetCurrentPropertyValue(AutomationElement.LabeledByProperty,true) as AutomationElement;
        if(label==null||label.Current.ProcessId!=expectedPid||label.Current.ControlType!=ControlType.Text||label.Current.IsOffscreen)return null;
        Privacy(control);Privacy(label);
        if(!EditorClickTarget.Matches(new System.Windows.Point(point.X,point.Y),System.Windows.Rect.Empty,label.Current.BoundingRectangle,true))return null;
        Target(control,h);Target(label,h);
        send("diagnostic",new {kind="semantic_label_click",control_type=control.Current.ControlType.ProgrammaticName,
            automation_id=Safe(control.Current.AutomationId),window_title=Safe(Native.Title(h))});
        return control;
    }
    void CaptureTaskbarSwitch(IntPtr taskbar,int epoch) {
        Native.CheckProcess(taskbar);
        string shell=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows),"explorer.exe");
        if(!String.Equals(Native.ProcessFor(taskbar).MainModule.FileName,shell,StringComparison.OrdinalIgnoreCase))
            throw new Exception("The taskbar identity could not be validated. Draft preserved.");
        if(lastWindow==IntPtr.Zero)
            throw new Exception("Start with an action in the selected prepared window before switching applications.");
        var wait=Stopwatch.StartNew();
        while(!Broken&&wait.ElapsedMilliseconds<500){
            var destination=Native.Root(Native.GetForegroundWindow());
            uint pid,originalPid;Native.GetWindowThreadProcessId(destination,out pid);
            if(destination!=IntPtr.Zero&&destination!=lastWindow&&destination!=taskbar&&!Mine(destination)){
                if(!preparedWindows.TryGetValue(destination,out originalPid)||originalPid!=pid)
                    throw new Exception("Taskbar switched to a window that was not open when recording began. Draft preserved.");
                Native.CheckProcess(destination);
                // Capture the resulting validated window identity, never the taskbar
                // coordinates or a shell Invoke. Values remain unread until typing.
                var target=Target(AutomationElement.FromHandle(destination),destination);
                if(Native.Root(Native.GetForegroundWindow())!=destination)
                    throw new Exception("The application changed during taskbar activation. Draft preserved.");
                editorAnchor=null;editorAnchorTarget=null;
                AnchorFocusedEditor(destination);
                WindowAction(destination,epoch);
                send("diagnostic",new {kind="taskbar_window_switch",window_title=target["window_key"],app=target["app"]});
                return;
            }
            Thread.Sleep(20);
        }
        throw new Exception("The taskbar did not activate an existing application. Draft preserved; taskbar menus and previews are not supported.");
    }
    bool WaitForClickedEditor(Native.Point point,IntPtr h,uint expectedPid) {
        // Mouse-up can precede Chromium's accessibility focus publication.
        // Query only the focused element, on the worker, for a bounded interval.
        var wait=Stopwatch.StartNew();
        do {
            if(Broken)return false;
            if(FocusedEditorContains(point,h,expectedPid))return true;
            if(wait.ElapsedMilliseconds>=150)return false;
            Thread.Sleep(15);
        } while(true);
    }
    static long MonotonicMs(){return (long)(Stopwatch.GetTimestamp()*1000.0/Stopwatch.Frequency);}
    void ResolvePendingEditorClick() {
        if(!pendingEditorClick.Active)return;
        var h=pendingEditorClick.Window;
        if(!pendingEditorClick.CanResolve(Native.Root(Native.GetForegroundWindow()),generation,MonotonicMs()))
            throw new Exception("The clicked editor was not identified before focus or timing changed. Draft preserved; no page contents were read.");
        uint pid;Native.GetWindowThreadProcessId(h,out pid);
        if(pid!=pendingWindowPid||Native.GetDpiForWindow(h)!=pendingWindowDpi||
           AutomationElement.FromHandle(h).Current.BoundingRectangle!=pendingWindowBounds)
            throw new Exception("The clicked window moved or changed before its editor was identified. Draft preserved.");
        var point=new Native.Point(){X=pendingEditorClick.X,Y=pendingEditorClick.Y};
        if(!FocusedEditorContains(point,h,pid)) {
            var focused=AutomationElement.FocusedElement;
            // Metadata only; never collect the document or an unclassified value.
            send("diagnostic",new {kind="editor_focus_unresolved",window_title=Native.Title(h),
                focused_type=focused==null?null:focused.Current.ControlType.ProgrammaticName,
                focused_process_matches=focused!=null&&focused.Current.ProcessId==pid,
                has_keyboard_focus=focused!=null&&focused.Current.HasKeyboardFocus,
                is_page_root=focused!=null&&focused.Current.AutomationId=="RootWebArea",
                contains_click=focused!=null&&focused.Current.BoundingRectangle.Contains(new System.Windows.Point(point.X,point.Y)),
                linked_label_available=focused!=null&&focused.GetCurrentPropertyValue(AutomationElement.LabeledByProperty,true) is AutomationElement});
            throw new Exception("The click did not identify the focused editor or its linked label. Draft preserved; no page contents were read.");
        }
        pendingEditorClick.Clear();
        send("diagnostic",new {kind="editor_focus_resolved",window_title=Native.Title(h),resolution="Matching editor validated after click; no value read"});
    }
    bool FocusedEditorContains(Native.Point point,IntPtr h,uint expectedPid) {
        if(Native.Root(Native.GetForegroundWindow())!=h)return false;
        var editor=AutomationElement.FocusedElement;
        if(editor==null||editor.Current.ProcessId!=expectedPid)return false;
        bool text=editor.Current.ControlType==ControlType.Edit||editor.Current.ControlType==ControlType.Document;
        if(!text||!editor.Current.HasKeyboardFocus)return false;
        if(editor.Current.AutomationId=="RootWebArea")return false;
        Privacy(editor,true); // Classification only: never reads text on a click.
        var bounds=editor.Current.BoundingRectangle;
        var location=new System.Windows.Point(point.X,point.Y);
        if(!EditorClickTarget.Matches(location,bounds,System.Windows.Rect.Empty,false)) {
            // Clicking an associated label focuses the editor without falling
            // inside the editor rectangle. Require the provider's explicit
            // relationship and same-window ancestry, not a matching label name.
            var label=editor.GetCurrentPropertyValue(AutomationElement.LabeledByProperty,true) as AutomationElement;
            if(label==null||label.Current.ProcessId!=expectedPid||label.Current.ControlType!=ControlType.Text||label.Current.IsOffscreen)return false;
            Privacy(label);
            if(!EditorClickTarget.Matches(location,bounds,label.Current.BoundingRectangle,true))return false;
            Target(label,h); // Verifies the linked label's ancestry and identity.
            send("diagnostic",new {kind="editor_label_click",window_title=Native.Title(h),resolution="Explicit UIA label relationship validated; no value read"});
        }
        AnchorEditor(editor,h); // Require stable identity and ancestry in this window.
        return true;
    }
    void AnchorEditor(AutomationElement editor,IntPtr h) {
        Privacy(editor,true);
        if(editor.Current.AutomationId=="RootWebArea")
            throw new Exception("The browser page itself is not a supported text field. Draft preserved; no page contents were read.");
        editorAnchorTarget=Target(editor,h);
        editorAnchor=editor;
        send("diagnostic",new {kind="editor_anchor",control_type=editorAnchorTarget["control_type"],
            automation_id=editorAnchorTarget["automation_id"],name=editorAnchorTarget["name"],
            window_title=editorAnchorTarget["window_key"]});
    }
    void AnchorFocusedEditor(IntPtr h) {
        editorAnchor=null;editorAnchorTarget=null;
        var editor=AutomationElement.FocusedElement;
        if(editor==null)return;
        if(editor.Current.ControlType!=ControlType.Edit&&editor.Current.ControlType!=ControlType.Document)return;
        if(!editor.Current.HasKeyboardFocus||editor.Current.AutomationId=="RootWebArea")return;
        uint pid;Native.GetWindowThreadProcessId(h,out pid);
        if(editor.Current.ProcessId!=pid)return;
        AnchorEditor(editor,h);
    }
    void TextIntent(IntPtr h,int epoch) {
        if(Broken)return;
        InputWindow(h);
        ResolvePendingEditorClick();
        var e=AutomationElement.FocusedElement;
        uint expectedPid;Native.GetWindowThreadProcessId(h,out expectedPid);
        if(e.Current.ProcessId!=expectedPid)throw new Exception("Focus moved to a different application. Capture stopped.");
        var t=Target(e,h);
        if(e.Current.ControlType!=ControlType.Edit&&e.Current.ControlType!=ControlType.Document)
            throw new Exception("Keyboard action outside a supported text field.");
        if(editorAnchor==null||!Automation.Compare(editorAnchor,e)){
            send("diagnostic",new {kind="editor_anchor_mismatch",anchor_present=editorAnchor!=null,
                anchored_type=editorAnchorTarget==null?null:editorAnchorTarget["control_type"],
                anchored_id=editorAnchorTarget==null?null:editorAnchorTarget["automation_id"],
                focused_type=t["control_type"],focused_id=t["automation_id"]});
            throw new Exception("Click the intended text field before typing so its starting document can be identified. Draft preserved.");
        }
        var serializer=new JavaScriptSerializer();
        foreach(string key in new[]{"app","control_type","automation_id","name","scope"})
            if(serializer.Serialize(t[key])!=serializer.Serialize(editorAnchorTarget[key]))
                throw new Exception("The focused document changed during text entry. Draft preserved.");
        t=new Dictionary<string,object>(editorAnchorTarget);
        if(field!=null&&!Automation.Compare(field,e))Flush();
        // Snapshot on accepted input, never substitute a later value at Stop.
        // UIA does not prove provenance within this observation interval; changes
        // after this snapshot are detected by Flush and fail closed.
        string snapshot=ReadText(e);
        WindowAction(h,epoch,(string)t["window_key"]);field=e;fieldTarget=t;fieldAt=epoch;fieldValue=snapshot;dirty=true;
    }
    string ReadText(AutomationElement e) {
        Privacy(e,true);
        object p;string value;
        if(e.TryGetCurrentPattern(ValuePattern.Pattern,out p))value=((ValuePattern)p).Current.Value;
        else if(e.TryGetCurrentPattern(TextPattern.Pattern,out p))value=((TextPattern)p).DocumentRange.GetText(2001);
        else throw new Exception("Text field does not expose a supported value pattern.");
        if(value.Length>2000)throw new Exception("This text field exceeds the supported recording size.");
        return Safe(value);
    }
    void Flush() {
        if(!Broken)ResolvePendingEditorClick();
        if(!dirty||Broken)return;
        if(ReadText(field)!=fieldValue)throw new Exception("Text changed after the observed input. Draft preserved; the later value was not recorded.");
        Emit("set_text",fieldTarget,fieldValue,(int)fieldAt);dirty=false;field=null;fieldValue=null;
    }
    public void Diagnostic(IntPtr h) {
        if(Armed||Interlocked.Read(ref BusySince)!=0||queue.Count!=0)
            throw new Exception("Wait until capture and accessibility work have stopped before inspecting Details.");
        Broken=false;
        Put(()=>{
        var normalized=Native.Root(h);
        Native.CheckProcess(h);
        var e=AutomationElement.FromHandle(h);
        var cache=new CacheRequest();cache.Add(AutomationElement.ControlTypeProperty);cache.Add(AutomationElement.IsPasswordProperty);
        cache.TreeScope=TreeScope.Element|TreeScope.Children;
        using(cache.Activate()){var children=e.FindAll(TreeScope.Children,System.Windows.Automation.Condition.TrueCondition);
            var rows=new List<object>();
            for(int i=0;i<Math.Min(30,children.Count);i++){var c=children[i];var childHandle=new IntPtr(c.Current.NativeWindowHandle);rows.Add(new {type=c.Current.ControlType.ProgrammaticName,password_classification_available=c.GetCurrentPropertyValue(AutomationElement.IsPasswordProperty,true) is bool,
                has_native_window=childHandle!=IntPtr.Zero,native_window=Native.WindowMetadata(childHandle),
                native_root=Native.WindowMetadata(Native.Root(childHandle)),root_matches_selected=Native.Root(childHandle)==normalized});}
            send("diagnostic",new {dpi=Native.GetDpiForWindow(h),monitors=Native.GetSystemMetrics(80),controls=rows,
                selected_title=Native.Title(h),selected_is_normalized_root=h==normalized,
                selected_window=Native.WindowMetadata(h),selected_owner=Native.WindowMetadata(Native.GetAncestor(h,3))});
        }
    });}
}

class Host : Window {
    static readonly JavaScriptSerializer json=new JavaScriptSerializer(){MaxJsonLength=65536};
    readonly BlockingCollection<string> outbound=new BlockingCollection<string>(128);
    readonly ComboBox windows=new ComboBox(){Margin=new Thickness(0,4,0,6),MinHeight=30};
    readonly ComboBox tasks=new ComboBox(){Margin=new Thickness(0,4,0,6),MinHeight=30};
    readonly StackPanel windowPanel=new StackPanel();
    readonly TextBlock heading=new TextBlock(){FontSize=18,FontWeight=FontWeights.SemiBold,Margin=new Thickness(0,5,0,2)};
    readonly TextBlock contextName=new TextBlock(){TextWrapping=TextWrapping.Wrap,Margin=new Thickness(0,0,0,6)};
    readonly Expander advanced=new Expander(){Header="Details",Margin=new Thickness(0,8,0,0)};
    readonly TextBlock status=new TextBlock(){Margin=new Thickness(7),TextWrapping=TextWrapping.Wrap};
    readonly TextBlock timer=new TextBlock(){Margin=new Thickness(7),FontSize=17};
    readonly StackPanel controls=new StackPanel(){Orientation=Orientation.Horizontal};
    readonly StackPanel savePanel=new StackPanel();
    readonly TextBox name=new TextBox(){Margin=new Thickness(0,4,0,6),MaxLength=100,MinHeight=30};
    Button saveButton,discardButton;
    Capture capture;IntPtr hwnd;string state="idle";string playbackProgress;int generation;long elapsed;Stopwatch segment=new Stopwatch();
    bool closeAllowed;bool pending;bool testInput;
    volatile string pendingId;
    DesktopPlayback playback;
    int instructionSerial;
    bool playbackPaused;
    bool awaitingPlayback;
    bool connected=true,stopRequested;
    string pendingKind="";
    string lastSavedId;
    public Host(bool testInput) {
        this.testInput=testInput;
        Title="Sports Cave · Task Recorder";Width=390;SizeToContent=SizeToContent.Height;Topmost=true;
        MaxHeight=SystemParameters.WorkArea.Height-30;FontFamily=new FontFamily("Segoe UI");FontSize=12;
        ResizeMode=ResizeMode.CanMinimize;WindowStartupLocation=WindowStartupLocation.Manual;
        Left=Math.Max(SystemParameters.WorkArea.Left,SystemParameters.WorkArea.Right-Width-20);Top=SystemParameters.WorkArea.Top+70;
        Background=new SolidColorBrush(Color.FromRgb(255,253,248));Foreground=new SolidColorBrush(Color.FromRgb(36,39,32));
        var layout=new StackPanel(){Margin=new Thickness(14)};Content=new ScrollViewer(){Content=layout,VerticalScrollBarVisibility=ScrollBarVisibility.Auto};
        var title=new TextBlock(){Text="SPORTS CAVE  /  TASK RECORDER",FontSize=10,Foreground=Brushes.DimGray};
        title.MouseLeftButtonDown+=(s,e)=>DragMove();layout.Children.Add(title);
        layout.Children.Add(heading);layout.Children.Add(contextName);
        windowPanel.Children.Add(new TextBlock(){Text="Window to record",Foreground=Brushes.DimGray});windowPanel.Children.Add(windows);layout.Children.Add(windowPanel);
        layout.Children.Add(controls);layout.Children.Add(timer);layout.Children.Add(status);
        savePanel.Children.Add(new TextBlock(){Text="Recording name"});
        savePanel.Children.Add(name);var row=new StackPanel(){Orientation=Orientation.Horizontal};
        saveButton=Button("Save recording",()=>Command("save",new {name=name.Text.Trim()}));
        discardButton=Button("Discard draft",()=>{if(MessageBox.Show(this,"Discard this unsaved recording?","Discard recording",MessageBoxButton.YesNo,MessageBoxImage.Question)==MessageBoxResult.Yes)Command("discard",new {});});
        row.Children.Add(saveButton);row.Children.Add(discardButton);savePanel.Children.Add(row);layout.Children.Add(savePanel);
        var details=new StackPanel();details.Children.Add(new TextBlock(){Text="Saved recording",Margin=new Thickness(0,6,0,0)});details.Children.Add(tasks);
        var tools=new StackPanel(){Orientation=Orientation.Horizontal};tools.Children.Add(Button("Refresh windows",RefreshWindows));
        tools.Children.Add(Button("Inspect window",()=>{if(windows.SelectedItem!=null)capture.Diagnostic((IntPtr)((ComboBoxItem)windows.SelectedItem).Tag);}));
        details.Children.Add(tools);details.Children.Add(new TextBlock(){Text="Ctrl+Alt+F12 stops playback immediately.",TextWrapping=TextWrapping.Wrap,Margin=new Thickness(0,5,0,0)});
        advanced.Content=details;layout.Children.Add(advanced);
        windows.SelectionChanged+=(s,e)=>Render();tasks.DropDownClosed+=(s,e)=>Render();
        SourceInitialized+=(s,e)=>{
            hwnd=new WindowInteropHelper(this).Handle;
            playback=new DesktopPlayback(hwnd,Send);
            HwndSource.FromHwnd(hwnd).AddHook((IntPtr h,int msg,IntPtr w,IntPtr l,ref bool handled)=>{
                if(msg==0x312&&w.ToInt32()==DesktopPlayback.Hotkey){playback.Stop();Send("diagnostic",new {kind="emergency_stop",source="registered_windows_hotkey"});Send("play_stop",new {reason="Emergency Stop requested."});handled=true;}return IntPtr.Zero;
            });
            capture=new Capture(hwnd,Send,reason=>Dispatcher.BeginInvoke(new Action(()=>{capture.Detach();Send("interrupt",new {reason});status.Text=reason;})),testInput);
            RefreshWindows();Render();Send("diagnostic",new {kind="toolbar_ready"});
        };
        Closing+=(s,e)=>{
            if(state=="playing"){playback.Disarm();Send("play_stop",new {reason="Toolbar closed. Pending effects remain uncertain."});closeAllowed=true;}
            if(!closeAllowed&&state!="idle"){e.Cancel=true;status.Text="Stop, then Save or Discard before closing.";if(state=="recording"||state=="paused")Stop();}
            else {if(capture!=null)capture.Detach();if(playback!=null)playback.Disarm();Send("close",new {});}
        };
        var tick=new DispatcherTimer(){Interval=TimeSpan.FromMilliseconds(250)};
        tick.Tick+=(s,e)=>{string display=playbackProgress??((state=="recording"?"● Recording  ":state=="paused"?"Paused  ":"")+TimeSpan.FromMilliseconds(elapsed+segment.ElapsedMilliseconds).ToString(@"hh\:mm\:ss"));if(timer.Text!=display)timer.Text=display;if(capture!=null)capture.Watchdog();if(playback!=null)playback.Watchdog();};tick.Start();
        Task.Run(()=>{foreach(string line in outbound.GetConsumingEnumerable()){Console.Out.WriteLine(line);Console.Out.Flush();}});
        Task.Run(()=>{try{string line;while((line=ReadFrame())!=null){var d=json.Deserialize<Dictionary<string,object>>(line);Dispatcher.Invoke(new Action(()=>Apply(d)));}}
            catch{} Dispatcher.BeginInvoke(new Action(()=>{if(capture!=null)capture.Detach();if(playback!=null)playback.Disarm();connected=false;pending=false;status.Text="Connection lost. Your draft is retained. Reopen the Windows popup from Sports Cave OS.";closeAllowed=true;Render();}));});
    }
    static string ReadFrame() {
        var buffer=new System.Text.StringBuilder();
        int c;
        while((c=Console.In.Read())!=-1){
            if(c==10)return buffer.ToString();
            if(buffer.Length>=65536)throw new Exception("IPC frame exceeds limit.");
            buffer.Append((char)c);
        }
        if(buffer.Length!=0)throw new Exception("Incomplete IPC frame.");
        return null;
    }
    Button Button(string text,Action action){var b=new Button(){Content=text,Padding=new Thickness(12,6,12,6),Margin=new Thickness(0,0,6,0),MinWidth=64,Background=Brushes.White,BorderBrush=new SolidColorBrush(Color.FromRgb(211,207,195))};b.Click+=(s,e)=>{try{action();}catch(Exception ex){status.Text=ex.Message;pending=false;pendingKind="";Render();}};return b;}
    void Send(string kind,object payload) {
        string id=Guid.NewGuid().ToString();
        if(pending&&kind!="event"&&kind!="diagnostic")pendingId=id;
        string message=json.Serialize(new {v=1,id=id,kind=kind,payload=payload});
        if(!outbound.TryAdd(message)){
            // The interruption itself cannot be delivered on a full connection.
            // End this candidate so the helper observes EOF, preserves its last
            // acknowledged draft/journal and marks the outcome interrupted.
            if(capture!=null){capture.Broken=true;capture.Armed=false;}
            if(playback!=null)playback.Stop();
            Environment.Exit(78);
        }
    }
    void Command(string kind,object payload){if(pending||stopRequested||!connected)return;pending=true;pendingKind=kind;status.Text=kind=="save"?"Saving…":"Updating…";Send(kind,payload);Render();}
    void RefreshWindows() {
        var old=windows.SelectedItem as ComboBoxItem;
        windows.Items.Clear();
        Native.EnumWindows((h,l)=>{if(h!=hwnd&&Native.IsWindowVisible(h)){string title=Native.Title(h);if(title.Length>0){try{Native.CheckProcess(h);windows.Items.Add(new ComboBoxItem(){Content=title,Tag=h});}catch{}}}return true;},IntPtr.Zero);
        if(old!=null)foreach(ComboBoxItem item in windows.Items)if(Equals(item.Tag,old.Tag)&&Equals(item.Content,old.Content))windows.SelectedItem=item;
        status.Text="Choose a window, then Record.";
    }
    void Stop(){if(stopRequested||!connected)return;stopRequested=true;pending=true;pendingKind="stop";capture.Barrier("stop");Render();}
    void StartPlayback() {
        if(pending)return;
        uint foregroundPid;Native.GetWindowThreadProcessId(Native.GetForegroundWindow(),out foregroundPid);
        if(!WindowIdentity.IsToolbar(foregroundPid,(uint)Process.GetCurrentProcess().Id))
            throw new Exception("Click Play in this popup to give Windows foreground control.");
        try {
            playback.Arm();awaitingPlayback=false;
            Command("play_ready",new {});
        } catch(Exception ex) {
            awaitingPlayback=false;playback.Disarm();Send("play_stop",new {reason=ex.Message});
        }
    }
    void Render(){
        // Interrupted recordings require explicit review before Save is accepted.
        heading.Text=ToolbarPresentation.Label(state,awaitingPlayback,playbackPaused,pendingKind,connected);
        if(state=="idle"&&tasks.SelectedItem!=null)contextName.Text="Selected recording: "+((Dictionary<string,object>)((ComboBoxItem)tasks.SelectedItem).Tag)["name"];
        controls.Children.Clear();savePanel.Visibility=state=="draft"?Visibility.Visible:Visibility.Collapsed;
        windowPanel.Visibility=state=="idle"?Visibility.Visible:Visibility.Collapsed;
        windows.IsEnabled=ToolbarPresentation.CanStart(state,pending||stopRequested,connected);
        advanced.IsEnabled=state=="idle"&&!pending&&!stopRequested&&connected;
        saveButton.IsEnabled=discardButton.IsEnabled=name.IsEnabled=connected&&!pending&&!stopRequested;
        contextName.Visibility=contextName.Text.Length==0?Visibility.Collapsed:Visibility.Visible;
        if(state=="idle"){
            controls.Children.Add(Button("Record",()=>{if(pending||stopRequested)return;if(windows.SelectedItem==null)throw new Exception("Choose the window you want to record.");pending=true;pendingKind="record";status.Text="Checking window…";capture.PrepareRecord((IntPtr)((ComboBoxItem)windows.SelectedItem).Tag);Render();}));
            if(tasks.SelectedItem!=null)controls.Children.Add(Button("Play",()=>{
                if(tasks.SelectedItem==null)throw new Exception("Choose a saved task.");
                var selected=(Dictionary<string,object>)((ComboBoxItem)tasks.SelectedItem).Tag;
                Command("play",new {id=selected["id"],revision=selected["revision"]});
            }));
        }else if(state=="playing"){
            if(awaitingPlayback)controls.Children.Add(Button("Play",StartPlayback));
            else controls.Children.Add(Button(playbackPaused?"Resume":"Pause",()=>Command(playbackPaused?"play_resume":"play_pause",new {})));
            controls.Children.Add(Button("Stop",()=>{if(stopRequested)return;stopRequested=true;pendingKind="stop";playback.Stop();Send("play_stop",new {reason="Stopped from the Windows popup."});Render();}));
        }else if(state=="recording"){
            controls.Children.Add(Button("Pause",()=>{if(pending||stopRequested)return;pending=true;pendingKind="pause";capture.Barrier("pause");Render();}));
            controls.Children.Add(Button("Stop",Stop));
        }else if(state=="paused"){
            controls.Children.Add(Button("Resume",()=>Command("resume",new {})));
            controls.Children.Add(Button("Stop",Stop));
        }else if(state=="interrupted")controls.Children.Add(Button("Review preserved draft",()=>Command("review",new {})));
        foreach(Button control in controls.Children){
            control.IsEnabled=ToolbarPresentation.CanControl(state,(string)control.Content,pending||stopRequested,connected);
            if((string)control.Content=="Record"&&windows.SelectedItem==null)control.IsEnabled=false;
            if((string)control.Content=="Record"||(string)control.Content=="Play"){
                control.Background=new SolidColorBrush(Color.FromRgb(184,154,66));control.Foreground=Brushes.White;
            }
        }
    }
    void Apply(Dictionary<string,object> d){
        if(!d.ContainsKey("v")||Convert.ToInt32(d["v"])!=1)return;
        if(d.ContainsKey("ack")&&(string)d["ack"]==pendingId){pending=false;pendingKind="";pendingId=null;}
        if((string)d["state"]=="interrupted"){pending=false;pendingKind="";pendingId=null;}
        string next=(string)d["state"];int epoch=Convert.ToInt32(d["generation"]);
        bool showSave=next=="draft"&&state!="draft";
        if(next=="idle"||next=="draft"||next=="interrupted")stopRequested=false;
        if(showSave&&d.ContainsKey("suggested_name"))name.Text=(string)d["suggested_name"];
        if(d.ContainsKey("recording_name"))contextName.Text=(string)d["recording_name"];
        if(next=="recording"&&(state!="recording"||epoch!=generation)){
            try{capture.Start(epoch);}catch(Exception e){Send("interrupt",new {reason=e.Message});return;}
        } else if(next!="recording"&&capture!=null)capture.Detach();
        state=next;generation=epoch;elapsed=Convert.ToInt64(d["elapsed_ms"]);segment.Reset();if(state=="recording")segment.Start();
        if(state=="idle"&&d.ContainsKey("tasks")){
            string previousRun=d.ContainsKey("run")&&d["run"]!=null?(string)((Dictionary<string,object>)d["run"])["task_id"]:null;
            TaskList.Update(tasks,(System.Collections.ArrayList)d["tasks"],previousRun);
            if(d.ContainsKey("last_saved")&&d["last_saved"]!=null){
                string saved=(string)((Dictionary<string,object>)d["last_saved"])["id"];
                if(saved!=lastSavedId){lastSavedId=saved;foreach(ComboBoxItem item in tasks.Items)if((string)((Dictionary<string,object>)item.Tag)["id"]==saved)tasks.SelectedItem=item;}
            }
        }
        playbackPaused=d.ContainsKey("run")&&d["run"]!=null&&(bool)((Dictionary<string,object>)d["run"])["pause_requested"];
        playbackProgress=null;
        if((state=="idle"||state=="playing")&&d.ContainsKey("run")&&d["run"]!=null){
            var run=(Dictionary<string,object>)d["run"];
            playbackProgress=((string)run["state"]=="completed"?"Completed":state=="playing"?(playbackPaused?"Paused":"Playing"):"Stopped")
                +" · "+run["next_step"]+"/"+run["total"]+" steps";
        }
        status.Text=(string)d["message"];Render();
        if(showSave){name.Focus();name.SelectAll();}
        if(d.ContainsKey("show_toolbar")&&(bool)d["show_toolbar"]){WindowState=WindowState.Normal;Show();if(state!="playing")Activate();}
        if(d.ContainsKey("instruction")&&d["instruction"]!=null){
            var instruction=(Dictionary<string,object>)d["instruction"];
            int serial=Convert.ToInt32(instruction["serial"]);
            if(serial>instructionSerial){
                instructionSerial=serial;
                try{
                    string kind=(string)instruction["kind"];
                    if(kind=="arm"){
                        uint foregroundPid;Native.GetWindowThreadProcessId(Native.GetForegroundWindow(),out foregroundPid);
                        bool localConfirmation=instruction.ContainsKey("require_local_confirmation")&&(bool)instruction["require_local_confirmation"];
                        if(!localConfirmation&&WindowIdentity.IsToolbar(foregroundPid,(uint)Process.GetCurrentProcess().Id))StartPlayback();
                        else {
                            awaitingPlayback=true;playbackProgress="Ready to play";
                            status.Text="Keep the recorded windows ready, then press Play here. Nothing has run yet.";
                            Render();
                        }
                    }
                    else if(kind=="execute")playback.Execute(Convert.ToInt32(instruction["step"]),(Dictionary<string,object>)instruction["action"]);
                    else if(kind=="disarm"){awaitingPlayback=false;playback.Disarm();}
                    else if(kind=="pause")playback.Pause();
                    else if(kind=="resume")playback.Resume();
                    else if(kind=="capture_pause")capture.Barrier("pause",(string)instruction["request_id"]);
                    else if(kind=="capture_stop")capture.Barrier("stop",(string)instruction["request_id"]);
                }catch(Exception ex){playback.Disarm();Send("play_stop",new {reason=ex.Message});}
            }
        }
        if(awaitingPlayback)playbackProgress="Ready to play";
    }
    [STAThread] public static void Main(string[] args) {
        if(!args.Contains("--candidate"))return;
        // A windowed executable has no console codepage handle. The inherited
        // anonymous streams still exist; wrap those directly with explicit UTF-8.
        Console.SetIn(new System.IO.StreamReader(Console.OpenStandardInput(),new System.Text.UTF8Encoding(false)));
        Console.SetOut(new System.IO.StreamWriter(Console.OpenStandardOutput(),new System.Text.UTF8Encoding(false)){AutoFlush=true});
        Native.SetProcessDpiAwarenessContext(new IntPtr(-4));
        bool created;
        using(var mutex=new Mutex(true,@"Local\SportsCaveDesktopRecorderCandidate",out created)){
            if(!created)return;
            new Application().Run(new Host(args.Contains("--accept-injected-test-input")));
        }
    }
}
