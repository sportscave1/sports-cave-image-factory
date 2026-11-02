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
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr window);
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
        if(n.Contains("computer-use")||new[]{"powershell","pwsh","cmd","windowsterminal","lockapp","credentialuibroker"}.Contains(n))
            throw new Exception("This application is outside the supported capture scope.");
    }
}

partial class Capture {
    readonly Action<string,object> send;
    readonly Action<string> fail;
    sealed class Work { public Action Run; public Func<bool> Redundant; public bool Control; public long Queued; public object Input; }
    readonly BlockingCollection<Work> queue=new BlockingCollection<Work>(128);
    readonly uint ownPid=(uint)Process.GetCurrentProcess().Id;
    readonly Stopwatch clock=Stopwatch.StartNew();
    readonly Native.Hook mouse,key;
    IntPtr mh,kh;
    public volatile bool Armed;
    public volatile bool Broken;
    public long BusySince;
    NativeMetrics metrics;
    int generation;
    IntPtr own,lastWindow;
    Dictionary<string,object> lastBrowser;
    sealed class BrowserWindowContext { public uint Pid;public string Title;public Dictionary<string,object> Browser; }
    readonly Dictionary<IntPtr,BrowserWindowContext> browserWindowContexts=new Dictionary<IntPtr,BrowserWindowContext>();
    readonly RunTransfer capturedTransfer=new RunTransfer();
    readonly RunImageTransfer capturedImage=new RunImageTransfer();
    bool imageDestinationEmpty;
    int transferSerial,latestTransfer=-1;
    AutomationElement pastedEditor;
    IntPtr preparedWindow;
    readonly Dictionary<IntPtr,uint> preparedWindows=new Dictionary<IntPtr,uint>();
    string lastTitle;
    AutomationElement field;
    AutomationElement editorAnchor;
    sealed class PromptPasteAnchor { public IntPtr Window; public int Epoch; public AutomationElement Editor; }
    volatile PromptPasteAnchor promptPasteAnchor;
    bool swallowedPromptPaste;
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
        public long LastAt;public bool Closed;public int Delta;
    }
    readonly object wheelGate=new object();
    WheelBurst wheelBurst;
    sealed class GenerationAnchor {
        public IntPtr Window;public uint Pid,Dpi;public int Epoch;public long DownAt,PreparedAt;
        public System.Windows.Rect Bounds,WindowBounds;
        public AutomationElement Control,Document;
        public Dictionary<string,object> Target;
        public ProductGenerationResult.Witness Before;
    }
    volatile GenerationAnchor preparedGeneration;
    readonly ConcurrentDictionary<IntPtr,GenerationAnchor> generationAnchors=new ConcurrentDictionary<IntPtr,GenerationAnchor>();
    IntPtr[] generationWindows=new IntPtr[0];
    readonly ConcurrentDictionary<IntPtr,GenerationAnchor> pickerAnchors=new ConcurrentDictionary<IntPtr,GenerationAnchor>();
    GenerationAnchor pendingPicker;
    bool expectedPickerDown;
    sealed class GenerationGesture { public long StartedAt,ReleasedAt,UtcMilliseconds;public SemanticClick Hover;public GenerationAnchor Generation,Picker; }
    GenerationGesture generationGesture;
    GenerationAnchor pendingGeneration;
    bool expectedGenerationDown;
    sealed class DropdownCapture {
        public AutomationElement Owner;
        public Dictionary<string,object> Target;
        public IntPtr Window;public uint Pid,Dpi;public int Epoch;
        public System.Windows.Rect WindowBounds;
        public System.Windows.Rect PopupBounds;
        public string Before,Candidate,View;
        public double? ScrollY;
        public bool Gesture;
    }
    DropdownCapture dropdown;
    sealed class SemanticClick {
        public AutomationElement Control;
        public Dictionary<string,object> Target;
        public IntPtr Window;public uint Pid,Dpi;public int Epoch;
        public System.Windows.Rect ControlBounds,WindowBounds;
        public long At;
        public string RuntimeId;
        public bool NeedsInvocation;
        public uint ClipboardBefore;
        public LocalSaveResult.Witness SaveBefore;
    }
    sealed class InvocationWitness { public string RuntimeId;public long At;public int Epoch,Pid;public string Name,Id;public System.Windows.Rect Bounds;public Dictionary<string,object> Browser; }
    readonly ConcurrentQueue<InvocationWitness> invocations=new ConcurrentQueue<InvocationWitness>();
    int invocationReceived,invocationRejected,invocationCacheFailures;
    string invocationCacheError;
    readonly InvocationSubscriptions invocationSubscriptions=new InvocationSubscriptions();
    IntPtr invocationWindow;
    int invocationEpoch;
    static string RuntimeIdentity(int[] ids) { return ids==null?null:String.Join(",",ids.Select(id=>id.ToString()).ToArray()); }
    void ObserveInvocations(IntPtr window) {
        if(invocationWindow==window)return;
        captureOperation="ensure invocation observer";
        int observerEpoch=Volatile.Read(ref invocationEpoch);
        invocationSubscriptions.Ensure(window,()=>{
        var invocationRoot=AutomationElement.FromHandle(window);
        AutomationEventHandler invocationHandler=(sender,args)=>{
            if(!Armed||Broken||observerEpoch!=Volatile.Read(ref invocationEpoch))return;
            Interlocked.Increment(ref invocationReceived);
            try {
                var source=(AutomationElement)sender;
                // Event-time cached metadata remains readable after a modal's
                // invoked button has been removed. Never read field values.
                if(source.Cached.ControlType!=ControlType.Button||source.Cached.IsPassword){Interlocked.Increment(ref invocationRejected);return;}
                var witness=new InvocationWitness{RuntimeId=RuntimeIdentity((int[])source.GetCachedPropertyValue(AutomationElement.RuntimeIdProperty)),At=MonotonicMs(),Epoch=generation};
                witness.Pid=source.Cached.ProcessId;witness.Bounds=source.Cached.BoundingRectangle;
                witness.Name=Safe(source.Cached.Name);witness.Id=Safe(source.Cached.AutomationId);
                witness.Browser=BrowserIdentity.ReadHelp(source.Cached.HelpText);
                if(witness.RuntimeId==null)return;
                invocations.Enqueue(witness);InvocationWitness old;
                while(invocations.Count>32)invocations.TryDequeue(out old);
            }catch(ElementNotAvailableException ex){invocationCacheError=ex.GetType().Name;Interlocked.Increment(ref invocationCacheFailures);}
            catch(InvalidOperationException ex){invocationCacheError=ex.GetType().Name;Interlocked.Increment(ref invocationCacheFailures);}
        };
        var cache=new CacheRequest();cache.TreeScope=TreeScope.Element;
        cache.Add(AutomationElement.RuntimeIdProperty);cache.Add(AutomationElement.ControlTypeProperty);cache.Add(AutomationElement.IsPasswordProperty);
        cache.Add(AutomationElement.ProcessIdProperty);cache.Add(AutomationElement.BoundingRectangleProperty);
        cache.Add(AutomationElement.NameProperty);cache.Add(AutomationElement.AutomationIdProperty);cache.Add(AutomationElement.HelpTextProperty);
        using(cache.Activate())Automation.AddAutomationEventHandler(InvokePattern.InvokedEvent,invocationRoot,TreeScope.Descendants,invocationHandler);
        return ()=>Automation.RemoveAutomationEventHandler(InvokePattern.InvokedEvent,invocationRoot,invocationHandler);
        });
        invocationWindow=window;
    }
    readonly ConcurrentDictionary<IntPtr,SemanticClick> saveAnchors=new ConcurrentDictionary<IntPtr,SemanticClick>();
    readonly ConcurrentDictionary<IntPtr,SemanticClick> imageAnchors=new ConcurrentDictionary<IntPtr,SemanticClick>();
    SemanticClick semanticClick;
    volatile SemanticClick hoverClick;
    sealed class HoverProbe {
        public Native.Point Point;public IntPtr Window;public int Epoch;
        public long Started,Completed;public bool Found;public string Error;
    }
    volatile HoverProbe activeHover,lastHover;
    readonly object hoverGate=new object();
    HoverProbe pendingHover;
    volatile HoverProbe physicalPointer;
    int hoverBusyUpdates;
    int hoverQueued;
    const int HoverFreshnessMs=1000;
    System.Threading.Timer hoverRefresh;
    System.Threading.Timer generationRefresh;
    int generationRefreshing;
    BrowserDownload.Session downloadSession;
    DateTime downloadClickAt;
    IntPtr downloadSaveOwner;
    volatile string captureOperation="idle";
    IntPtr observedWindow;
    public Capture(IntPtr own,Action<string,object> send,Action<string> fail,bool injected) {
        this.own=own;this.send=send;this.fail=fail;this.injected=injected;
        mouse=OnMouse;key=OnKey;
        var worker=new Thread(()=>{foreach(var work in queue.GetConsumingEnumerable()){
            if(Broken&&!work.Control)continue; // Cleanup still runs after an interruption.
            if(work.Redundant!=null&&work.Redundant())continue; // Metadata-only duplicate notifications; never input.
            Interlocked.Exchange(ref BusySince,Stopwatch.GetTimestamp());
            try {
                double queuedMs=(Stopwatch.GetTimestamp()-work.Queued)*1000.0/Stopwatch.Frequency;
                if(!work.Control&&queuedMs>500){send("diagnostic",new {kind="capture_queue_stale",queued_ms=queuedMs,callback=work.Run.Method.Name,metadata_notification=work.Redundant!=null,input=work.Input});throw new Exception("Capture fell behind input. Draft preserved; no delayed target was read.");}
                work.Run();
            } catch(Exception e){
                bool exists=observedWindow!=IntPtr.Zero&&Native.IsWindow(observedWindow);
                send("diagnostic",new {kind="capture_operation_failed",operation=captureOperation,error_type=e.GetType().Name,hresult=e.HResult,window_exists=exists,
                    methods=new StackTrace(e,false).GetFrames().Select(frame=>frame.GetMethod().Name).Take(8).ToArray()});
                Interrupt(e is ElementNotAvailableException?(exists?"The clicked control changed before its action could be identified. Draft preserved.":"The target window disappeared."):
                    e is COMException?"Windows accessibility failed during "+captureOperation+" (0x"+e.HResult.ToString("X8")+"). Draft preserved; no action was inferred.":
                    String.IsNullOrWhiteSpace(e.Message)?"Capture failed during "+captureOperation+". Draft preserved.":e.Message);
            }
            finally{Interlocked.Exchange(ref BusySince,0);}
        }}){IsBackground=true,Name="recorder-capture"};worker.SetApartmentState(ApartmentState.MTA);worker.Start();
    }
    void Put(Action a,Func<bool> redundant=null) { Enqueue(a,false,redundant); }
    void Enqueue(Action a,bool control,Func<bool> redundant=null) { EnqueueWork(new Work{Run=a,Redundant=redundant,Control=control,Queued=Stopwatch.GetTimestamp()}); }
    void PutObserved(Action a,object input) { EnqueueWork(new Work{Run=a,Input=input,Queued=Stopwatch.GetTimestamp()}); }
    void EnqueueWork(Work work) { if((!Broken||work.Control)&&!queue.TryAdd(work)) Interrupt("Capture queue is full. Stop and save the preserved draft."); }
    object MouseEvidence(string kind,IntPtr window,uint flags) {
        // Capture only bounded Win32 identity facts at input time. Never read
        // accessibility, titles, URLs, field values or clipboard contents here.
        // A stale queue reports these facts without inspecting a changed target.
        var owner=downloadSaveOwner;uint pid,ownerPid=0;
        Native.GetWindowThreadProcessId(window,out pid);
        if(owner!=IntPtr.Zero)Native.GetWindowThreadProcessId(owner,out ownerPid);
        return new {kind=kind,process_id=pid,download_owner_process_id=ownerPid,
            download_waiting=owner!=IntPtr.Zero,input_is_download_owner=owner!=IntPtr.Zero&&window==owner,
            foreground_matches_input=Native.Root(Native.GetForegroundWindow())==window,
            injected=(flags&1)!=0};
    }
    public void Interrupt(string reason) { if(Broken)return; Broken=true; Armed=false; fail(reason); }
    public void Watchdog() {
        long since=Interlocked.Read(ref BusySince);
        if(!Broken&&since!=0 && (Stopwatch.GetTimestamp()-since)/(double)Stopwatch.Frequency>3) {
            // Metadata only: never query the stalled accessibility provider from
            // the UI/watchdog thread, or include text/clipboard contents.
            send("diagnostic",new {kind="capture_provider_timeout",operation=captureOperation,
                elapsed_ms=(Stopwatch.GetTimestamp()-since)*1000.0/Stopwatch.Frequency,queued_work=queue.Count});
            Interrupt("Accessibility provider did not respond. Stop to preserve the draft, then restart the candidate.");
        }
    }
    public void Start(int epoch,bool resume=false) {
        if(Broken&&(Interlocked.Read(ref BusySince)!=0||queue.Count!=0))throw new Exception("Restart the candidate after an accessibility interruption.");
        Broken=false;field=null;fieldTarget=null;dirty=false;editorAnchor=null;editorAnchorTarget=null;promptPasteAnchor=null;swallowedPromptPaste=false;
        capturedTransfer.BeginCapture(resume);if(!resume){latestTransfer=-1;capturedImage.Clear();}pastedEditor=null;
        pendingEditorClick.Clear();
        pendingGeneration=null;expectedGenerationDown=false;
        pendingPicker=null;expectedPickerDown=false;
        dropdown=null;
        downloadDialogNotifications.Clear();
        semanticClick=null;
        hoverClick=null;
        physicalPointer=null;
        lock(hoverGate)pendingHover=null;
        activeHover=lastHover=null;hoverBusyUpdates=0;
        var eventWindow=preparedWindow!=IntPtr.Zero?preparedWindow:lastWindow;
        generation=epoch;lastWindow=IntPtr.Zero;lastTitle=null;lastBrowser=null;browserWindowContexts.Clear();
        InvocationWitness prior;while(invocations.TryDequeue(out prior)){}
        invocationReceived=invocationRejected=invocationCacheFailures=0;invocationCacheError=null;
        if(eventWindow!=IntPtr.Zero)Put(()=>ObserveInvocations(eventWindow));
        mh=Native.SetWindowsHookEx(14,mouse,Native.GetModuleHandle(null),0);
        kh=Native.SetWindowsHookEx(13,key,Native.GetModuleHandle(null),0);
        if(mh==IntPtr.Zero||kh==IntPtr.Zero) {Detach();throw new Exception("Windows capture hooks could not be armed.");}
        physicalMouseDowns=injectedMouseDowns=acceptedMouseDowns=shellMouseDowns=shellIdentityMisses=0;
        Armed=true;
        try{ArmSession();}catch{Detach();throw;}
        // A stationary physical pointer still needs fresh metadata: waiting to
        // renew it until mouse-down races controls that disappear on release.
        // Renew halfway through the existing freshness budget, never extend it.
        hoverRefresh=new System.Threading.Timer(_=>RefreshStationaryHover(),null,HoverFreshnessMs/2,HoverFreshnessMs/2);
        generationRefresh=new System.Threading.Timer(_=>RefreshGeneration(),null,0,250);
        StartShell(resume);
        metrics=NativeMetrics.Begin("recording");
        clock.Start();
    }
    public void PrepareRecord(IntPtr selected,bool desktopSession=false) {
        if(Interlocked.Read(ref BusySince)!=0||queue.Count!=0)throw new Exception("Wait for the accessibility check to finish.");
        Broken=false;
        DesktopSession=desktopSession;
        Put(()=>{if(selected!=IntPtr.Zero)selected=Native.Root(selected);
            downloadSession=new BrowserDownload.Session();
            var target=selected==IntPtr.Zero?null:Target(AutomationElement.FromHandle(selected),selected);
            preparedWindows.Clear();
            Native.EnumWindows((h,l)=>{
                if(preparedWindows.Count>=512)return false;
                if(Native.IsWindowVisible(h)){uint pid;Native.GetWindowThreadProcessId(h,out pid);preparedWindows[Native.Root(h)]=pid;}
                return true;
            },IntPtr.Zero);
            generationAnchors.Clear();pickerAnchors.Clear();imageAnchors.Clear();saveAnchors.Clear();
            var browserWindows=new List<IntPtr>();
            foreach(var h in preparedWindows.Keys) {
                try {if(!Mine(h)&&BrowserTabs.Chromium(h)&&(LocalSaveResult.Read(h)!=null||BrowserIdentity.Current(h)!=null))browserWindows.Add(h);}catch{}
            }
            if(browserWindows.Count>8)throw new Exception("Too many compatible preview windows. Prepare at most eight before Record.");
            generationWindows=browserWindows.ToArray();
            preparedWindow=selected;if(selected!=IntPtr.Zero){PreparePicker(selected);PrepareGeneration(selected);}clock.Reset();traceCount=0;ownExclusions=0;
            try {
                var shell=TaskbarRoute.Read(()=>{});
                send("diagnostic",new {kind="taskbar_preflight",items=shell.Where(x=>
                    ((string)x.Selector["name"]).IndexOf("Sports Cave",StringComparison.OrdinalIgnoreCase)>=0||
                    ((string)x.Selector["name"]).IndexOf("ChatGPT",StringComparison.OrdinalIgnoreCase)>=0).Select(x=>x.Selector).ToArray()});
            }catch(Exception error){send("diagnostic",new {kind="taskbar_preflight_failed",message=error.Message});}
            send("record",new {window=target,mode=DesktopSession?"desktop_session":"prepared"});});
    }
    public void Detach(bool finishMetrics=true) {
        bool wasArmed=Armed;
        Armed=false;
        if(wasArmed)send("diagnostic",new {kind="capture_input_summary",injected_test_input_enabled=injected,
            physical_mouse_downs=physicalMouseDowns,injected_mouse_downs=injectedMouseDowns,
            accepted_mouse_downs=acceptedMouseDowns,shell_mouse_downs=shellMouseDowns,
            shell_identity_misses=shellIdentityMisses});
        DisarmSession();
        var refresh=Interlocked.Exchange(ref hoverRefresh,null);if(refresh!=null)refresh.Dispose();
        StopShell();
        var generationTimer=Interlocked.Exchange(ref generationRefresh,null);if(generationTimer!=null)generationTimer.Dispose();
        Interlocked.Increment(ref invocationEpoch);
        invocationWindow=IntPtr.Zero;
        invocationSubscriptions.Reset();
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
        // A pending download can observe Detach and interrupt on this worker.
        // Its Stop/Pause acknowledgement must survive that interruption and
        // must not be treated as a stale input observation.
        Enqueue(()=>{if(!Broken){Flush();PollDropdown(true);FinishShellCapture();}FinishMetrics();send("diagnostic",new {kind="capture_barrier",toolbar_inputs_excluded=ownExclusions});send(command,new {request_id=requestId});},true);
    }
    bool Mine(IntPtr h) { uint id;Native.GetWindowThreadProcessId(h,out id);return WindowIdentity.IsToolbar(id,ownPid); }
    int physicalMouseDowns,injectedMouseDowns,acceptedMouseDowns,shellMouseDowns,shellIdentityMisses;
    IntPtr OnMouse(int c,IntPtr w,IntPtr l) {
        if(c>=0&&Armed&&(w.ToInt32()==0x200||w.ToInt32()==0x201||w.ToInt32()==0x202||w.ToInt32()==0x20A||w.ToInt32()==0x205)){
            var m=(Native.Mouse)Marshal.PtrToStructure(l,typeof(Native.Mouse));
            if(w.ToInt32()==0x201) {
                if((m.flags&1)==0)physicalMouseDowns++;else injectedMouseDowns++;
                if(injected||(m.flags&1)==0)acceptedMouseDowns++;
            }
            if(injected||(m.flags&1)==0){
                var hit=Native.WindowFromPoint(m.point);var window=Native.Root(hit);
                var shellRoot=Native.GetAncestor(hit,2);if(TaskbarRoute.Surface(shellRoot))window=shellRoot;
                if(BrowserDownload.OwnedSaveDialog(hit,downloadSaveOwner))return Native.CallNextHookEx(IntPtr.Zero,c,w,l);
                physicalPointer=new HoverProbe{Point=m.point,Window=window,Epoch=generation};
                if(Mine(window)){if(w.ToInt32()==0x202)ownExclusions++;return Native.CallNextHookEx(IntPtr.Zero,c,w,l);}
                if(w.ToInt32()==0x200){QueueHover(m.point,window);return Native.CallNextHookEx(IntPtr.Zero,c,w,l);}
                if(w.ToInt32()==0x201&&TaskbarRoute.Surface(window)) {
                    shellGesture=true;shellDown=TaskbarRoute.Hit(shellItems,window,m.point);
                    if(shellDown==null){
                        var observed=shellItems;var missedWindow=window;var missedPoint=m.point;long missedAt=Stopwatch.GetTimestamp();
                        Put(()=>send("diagnostic",new {kind="taskbar_capture_identity_miss",surface=TaskbarRoute.Class(missedWindow),
                            candidates=observed.Select(x=>new {same_surface=x.Window==missedWindow,contains_point=x.Bounds.Contains(new System.Windows.Point(missedPoint.X,missedPoint.Y)),
                                age_ms=(missedAt-x.At)*1000.0/Stopwatch.Frequency}).ToArray()}));
                    }
                    shellMouseDowns++;if(shellDown==null)shellIdentityMisses++;
                    var capturedDown=shellDown;
                    Put(()=>send("diagnostic",new {kind="taskbar_capture_down",resolved=capturedDown!=null,
                        thumbnail=capturedDown!=null&&TaskbarRoute.Thumbnail(capturedDown.Selector)}));
                    shellOrigin=Native.Root(Native.GetForegroundWindow());shellPressed=true;PhysicalTransition(m.time);
                    return Native.CallNextHookEx(IntPtr.Zero,c,w,l);
                }
                if(w.ToInt32()==0x202&&shellPressed) {
                    shellPressed=false;var item=shellDown;var origin=shellOrigin;int shellEpoch=generation;
                    Put(()=>{FlushForTransition();CaptureShell(item,origin,shellEpoch);});
                    return Native.CallNextHookEx(IntPtr.Zero,c,w,l);
                }
                if(w.ToInt32()==0x201&&shellGesture) {
                    Put(()=>Interrupt("Taskbar thumbnail selection was interrupted. Draft preserved."));
                    return Native.CallNextHookEx(IntPtr.Zero,c,w,l);
                }
                if(w.ToInt32()==0x201){var point=m.point;int epoch=generation;long at=MonotonicMs();
                    var input=MouseEvidence("mouse_down",window,m.flags);
                    moveGesture.Begin(window,epoch,m.time);
                    downloadClickAt=DateTime.UtcNow;
                    PhysicalTransition(m.time);mouseDownWindow=window;mouseDownState=DesktopWindowState.Read(window);string beforeState=mouseDownState;
                    GenerationAnchor generationAnchor,pickerAnchor;generationAnchors.TryGetValue(window,out generationAnchor);pickerAnchors.TryGetValue(window,out pickerAnchor);
                    var gesture=new GenerationGesture{StartedAt=at,UtcMilliseconds=(DateTime.UtcNow.Ticks-621355968000000000)/10000,Hover=SaveAnchor(window,m.point)??ImageAnchor(window,m.point)??hoverClick,Generation=generationAnchor,Picker=pickerAnchor};generationGesture=gesture;
                    PutObserved(()=>{observedWindow=window;
                        if(DesktopSession&&moveGesture.Matches(window,epoch))return;
                        if(DesktopSession&&DesktopWindowState.Read(window)!=beforeState)return;
                        try {
                        if(DesktopSession&&!Native.IsTaskbar(window)){Native.CheckProcess(window);ObserveInvocations(window);}
                        captureOperation="mouse-down generation";SnapshotGeneration(point,window,epoch,at,gesture);SnapshotGeneration(point,window,epoch,at,gesture,true);
                        captureOperation="mouse-down button";SnapshotSemanticClick(point,window,epoch,at,gesture);
                        // One physical gesture has one owner. The verified
                        // button may already have replaced the page; probing
                        // dropdowns then would inspect an unrelated old tree.
                        // A released click cannot establish a new pre-click dropdown
                        // owner. Preserve already anchored dropdown selection handling,
                        // but leave unanchored gestures to the validated mouse-up path.
                        if(semanticClick==null&&!expectedGenerationDown&&!expectedPickerDown&&
                           (dropdown!=null||Interlocked.Read(ref gesture.ReleasedAt)==0)) {
                            captureOperation="mouse-down dropdown";SnapshotDropdown(point,window,epoch);
                        }
                        }catch {if(!DesktopSession||DesktopWindowState.Read(window)==beforeState)throw;}
                    },input);}
                else if(w.ToInt32()==0x20A){QueueWheel(m.point,window,generation,unchecked((short)(m.data>>16)));}
                else if(w.ToInt32()==0x202){CloseWheelBurst();var point=m.point;int epoch=generation;
                    var input=MouseEvidence("mouse_up",window,m.flags);
                    var transitionWindow=mouseDownWindow;var transitionBefore=mouseDownState;
                    if(CompleteWindowGesture(epoch))return Native.CallNextHookEx(IntPtr.Zero,c,w,l);
                    var gesture=generationGesture;generationGesture=null;
                    if(gesture!=null)Interlocked.Exchange(ref gesture.ReleasedAt,MonotonicMs());
                    var foreground=Native.Root(Native.GetForegroundWindow());
                    PutObserved(()=>{observedWindow=window;captureOperation="mouse-up";TraceWindow("mouse",window,foreground,hit);
                        if(CompleteObservedWindowGesture(transitionWindow,transitionBefore,epoch))return;
                        try {Flush();if(!CompleteGeneration(point,window,epoch,true)&&!CompleteGeneration(point,window,epoch)&&!FinishDropdownClick()&&!CompleteBrowserNavigation(point,window,epoch,gesture)&&!CompleteSemanticClick(point,window,epoch))Click(point,window,epoch);}
                        catch {if(!CompleteObservedWindowGesture(transitionWindow,transitionBefore,epoch))throw;}
                    },input);}
                else {CloseWheelBurst();Put(()=>{Flush();Interrupt("Secondary clicks are not yet supported. Draft preserved.");});}
            }
        }
        return Native.CallNextHookEx(IntPtr.Zero,c,w,l);
    }
    void CloseWheelBurst(){lock(wheelGate){if(wheelBurst!=null)wheelBurst.Closed=true;}}
    void RefreshGeneration() {
        if(!Armed||Broken||Interlocked.CompareExchange(ref generationRefreshing,1,0)!=0)return;
        int epoch=generation;
        try {
            var window=Native.Root(Native.GetForegroundWindow());
            if(window==IntPtr.Zero)return;
            // The toolbar owns focus at Record. Keep only already identified
            // local-preview windows prepared without activating or navigating.
            var candidates=Mine(window)?generationWindows:new[]{window};
            foreach(var candidate in candidates) {
                if(!Armed||Broken||epoch!=generation)break;
                try {if(BrowserTabs.Chromium(candidate)){PrepareGeneration(candidate);PreparePicker(candidate);PrepareImage(candidate);}}
                catch {GenerationAnchor discarded;generationAnchors.TryRemove(candidate,out discarded);pickerAnchors.TryRemove(candidate,out discarded);SemanticClick imageDiscarded;imageAnchors.TryRemove(candidate,out imageDiscarded);saveAnchors.TryRemove(candidate,out imageDiscarded);}
                try {if(BrowserTabs.Chromium(candidate))PrepareSave(candidate);}
                catch(Exception ex){SemanticClick discarded;saveAnchors.TryRemove(candidate,out discarded);SavePreflight("error: "+ex.GetType().Name+": "+ex.Message);}
            }
            if(epoch!=generation||!Armed){preparedGeneration=null;generationAnchors.Clear();pickerAnchors.Clear();imageAnchors.Clear();saveAnchors.Clear();}
        }catch{preparedGeneration=null;generationAnchors.Clear();pickerAnchors.Clear();imageAnchors.Clear();saveAnchors.Clear();} // No action inferred from failed preflight.
        finally{Interlocked.Exchange(ref generationRefreshing,0);}
    }
    void PrepareGeneration(IntPtr window) {
        GenerationAnchor found=null;
        GenerationAnchor discarded;
        var process=Native.ProcessFor(window);
        if(!WindowIdentity.ChromiumApp(process.MainModule.FileName)){generationAnchors.TryRemove(window,out discarded);return;}
        var root=AutomationElement.FromHandle(window);
        if(root.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.AutomationIdProperty,ProductGenerationResult.Container)).Count==0){generationAnchors.TryRemove(window,out discarded);return;}
        var buttons=root.FindAll(TreeScope.Descendants,new AndCondition(
            new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Button),
            new PropertyCondition(AutomationElement.NameProperty,"Generate mockups")));
        if(buttons.Count>16)throw new Exception("Generate is ambiguous. Prepare one product page before Record.");
        foreach(AutomationElement button in buttons) {
            if(!button.Current.IsEnabled||button.Current.IsOffscreen)continue;
            var target=Target(button,window);
            if(!ProductGenerationResult.Supports(target))continue;
            if(found!=null)throw new Exception("Generate is ambiguous. Prepare one product page before Record.");
            found=new GenerationAnchor{Window=window,Pid=(uint)process.Id,Control=button,Target=target,
                Document=ProductGenerationResult.Document(button,window,(uint)process.Id),
                Before=ProductGenerationResult.Read(button,window,(uint)process.Id),
                Bounds=button.Current.BoundingRectangle,WindowBounds=root.Current.BoundingRectangle,Dpi=Native.GetDpiForWindow(window),Epoch=generation,PreparedAt=MonotonicMs()};
        }
        preparedGeneration=found;
        if(found!=null)generationAnchors[window]=found;
        else generationAnchors.TryRemove(window,out discarded);
    }
    string savePreflightStatus;
    void SavePreflight(string status) {
        if(status==savePreflightStatus)return;
        savePreflightStatus=status;send("diagnostic",new {kind="local_save_preflight",status=status});
    }
    void PrepareSave(IntPtr window) {
        SemanticClick discarded;var witness=LocalSaveResult.Read(window);
        if(witness==null){saveAnchors.TryRemove(window,out discarded);SavePreflight("receipt unavailable");return;}
        var root=AutomationElement.FromHandle(window);
        var buttons=root.FindAll(TreeScope.Descendants,new AndCondition(new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Button),new PropertyCondition(AutomationElement.NameProperty,"Save all")));
        if(buttons.Count!=1||!buttons[0].Current.IsEnabled||buttons[0].Current.IsOffscreen){saveAnchors.TryRemove(window,out discarded);return;}
        var button=buttons[0];var target=Target(button,window);target["postcondition"]=LocalSaveResult.Contract;
        saveAnchors[window]=new SemanticClick{Control=button,Target=target,Window=window,Pid=(uint)button.Current.ProcessId,
            Dpi=Native.GetDpiForWindow(window),Epoch=generation,At=MonotonicMs(),ControlBounds=button.Current.BoundingRectangle,
            WindowBounds=root.Current.BoundingRectangle,RuntimeId=RuntimeIdentity(button.GetRuntimeId()),SaveBefore=witness};
        SavePreflight("ready");
    }
    SemanticClick SaveAnchor(IntPtr window,Native.Point point) {
        SemanticClick a;if(!saveAnchors.TryGetValue(window,out a)||!a.ControlBounds.Contains(new System.Windows.Point(point.X,point.Y)))return null;
        return new SemanticClick{Control=a.Control,Target=a.Target,Window=a.Window,Pid=a.Pid,Dpi=a.Dpi,Epoch=a.Epoch,At=a.At,
            ControlBounds=a.ControlBounds,WindowBounds=a.WindowBounds,RuntimeId=a.RuntimeId,
            SaveBefore=new LocalSaveResult.Witness{Path=a.SaveBefore.Path,Source=a.SaveBefore.Source,
                Written=File.Exists(a.SaveBefore.Path)?File.GetLastWriteTimeUtc(a.SaveBefore.Path).Ticks:0}};
    }
    SemanticClick ImageAnchor(IntPtr window,Native.Point point) {
        SemanticClick anchor;
        if(!imageAnchors.TryGetValue(window,out anchor)||!anchor.ControlBounds.Contains(new System.Windows.Point(point.X,point.Y)))return null;
        // Sequence is sampled synchronously before Windows handles this down.
        return new SemanticClick{Control=anchor.Control,Target=anchor.Target,Window=anchor.Window,Pid=anchor.Pid,Dpi=anchor.Dpi,
            Epoch=anchor.Epoch,At=anchor.At,ControlBounds=anchor.ControlBounds,WindowBounds=anchor.WindowBounds,
            RuntimeId=anchor.RuntimeId,ClipboardBefore=ProductImageResult.GetClipboardSequenceNumber()};
    }
    void PrepareImage(IntPtr window) {
        SemanticClick found=null,discarded;
        var root=AutomationElement.FromHandle(window);
        foreach(AutomationElement button in root.FindAll(TreeScope.Descendants,new AndCondition(
            new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Button),
            new PropertyCondition(AutomationElement.AutomationIdProperty,"copyImage")))) {
            if(button.Current.IsOffscreen||!button.Current.IsEnabled||!ProductImageResult.HasStatus(button.Current.HelpText,ProductImageResult.Ready))continue;
            var target=Target(button,window);
            if(!ProductImageResult.Supports(target))continue;
            if(found!=null)throw new Exception("Image copy control is ambiguous.");
            found=new SemanticClick{Control=button,Target=target,Window=window,Pid=(uint)button.Current.ProcessId,
                Dpi=Native.GetDpiForWindow(window),Epoch=generation,At=MonotonicMs(),ControlBounds=button.Current.BoundingRectangle,
                WindowBounds=root.Current.BoundingRectangle,RuntimeId=RuntimeIdentity(button.GetRuntimeId())};
        }
        if(found!=null)imageAnchors[window]=found;else imageAnchors.TryRemove(window,out discarded);
    }
    void PreparePicker(IntPtr window) {
        GenerationAnchor found=null,discarded;
        var process=Native.ProcessFor(window);
        if(!WindowIdentity.ChromiumApp(process.MainModule.FileName)){pickerAnchors.TryRemove(window,out discarded);return;}
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
            if(found!=null)throw new Exception("Prepare one Product Uploads PSD picker before Record.");
            found=new GenerationAnchor{Window=window,Pid=(uint)process.Id,Control=button,Target=target,Document=document,
                Bounds=button.Current.BoundingRectangle,WindowBounds=root.Current.BoundingRectangle,Dpi=Native.GetDpiForWindow(window),Epoch=generation,PreparedAt=MonotonicMs()};
        }
        if(found!=null)pickerAnchors[window]=found;
        else pickerAnchors.TryRemove(window,out discarded);
    }
    void SnapshotGeneration(Native.Point point,IntPtr window,int epoch,long at,GenerationGesture gesture,bool picker=false) {
        if(picker){pendingPicker=null;expectedPickerDown=false;}else{pendingGeneration=null;expectedGenerationDown=false;}
        var prepared=picker?gesture.Picker:gesture.Generation;
        if(prepared==null||window!=prepared.Window||!prepared.Bounds.Contains(new System.Windows.Point(point.X,point.Y)))return;
        if(picker)expectedPickerDown=true;else expectedGenerationDown=true;
        // Freeze the preflight on mouse-down for BOTH controls. The picker can
        // replace the hit-tested node before mouse-up just as Generate can.
        uint actualPid;Native.GetWindowThreadProcessId(window,out actualPid);
        if(prepared.Epoch!=epoch||prepared.PreparedAt>at||at-prepared.PreparedAt>HoverFreshnessMs||
            (!picker&&(prepared.Before==null||prepared.Before.State!="idle"))||actualPid!=prepared.Pid||
            Native.GetDpiForWindow(window)!=prepared.Dpi||
            AutomationElement.FromHandle(window).Current.BoundingRectangle!=prepared.WindowBounds)
            throw new Exception((picker?"PSD picker":"Generate")+" preflight is stale or changed. Draft preserved; no action guessed.");
        var pending=new GenerationAnchor{Window=window,Pid=prepared.Pid,Dpi=prepared.Dpi,
            Bounds=prepared.Bounds,WindowBounds=prepared.WindowBounds,Epoch=epoch,DownAt=at,
            Target=prepared.Target,Before=prepared.Before,Document=prepared.Document};
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
        while(picker&&!Broken&&wait.ElapsedMilliseconds<1500) {
            InputWindow(window);
            if(picker) {
                if(anchor.Target.ContainsKey("browser")&&!BrowserIdentity.SamePage(BrowserIdentity.Current(window),(Dictionary<string,object>)anchor.Target["browser"]))
                    throw new Exception("PSD picker product or browser identity changed. Draft preserved.");
                if(ProductPickerResult.Open(anchor.Document,window,pid)) {
                    WindowAction(window,epoch,(string)anchor.Target["window_key"]);Emit("invoke",anchor.Target,null,epoch);
                    send("diagnostic",new {kind="psd_picker_click_acknowledged",pre_click_identity_verified=true,modal_verified=true});
                    GenerationAnchor discarded;pickerAnchors.TryRemove(window,out discarded);return true;
                }
                Thread.Sleep(25);continue;
            }
        }
        if(!picker) {
            send("diagnostic",new {kind="generation_ack_wait",deadline_ms=30000});
            var acknowledged=ProductGenerationResult.WaitAcknowledgement(anchor.Before,()=>{
            // A fresh poll renews the watchdog; a hung UIA read still trips it.
            Interlocked.Exchange(ref BusySince,Stopwatch.GetTimestamp());
            InputWindow(window);
            var document=anchor.Document;
            if(anchor.Target.ContainsKey("browser")) {
                var expected=(Dictionary<string,object>)anchor.Target["browser"];
                if(!BrowserIdentity.SamePage(BrowserIdentity.Current(window),expected))
                    throw new Exception("Generate product or browser identity changed. Draft preserved.");
                var containers=AutomationElement.FromHandle(window).FindAll(TreeScope.Descendants,
                    new PropertyCondition(AutomationElement.AutomationIdProperty,ProductGenerationResult.Container));
                if(containers.Count!=1)throw new Exception("Generate acknowledgement is missing or ambiguous. Draft preserved.");
                document=ProductGenerationResult.Document(containers[0],window,pid);
            }
            return ProductGenerationResult.ReadForDocument(document,window,pid);
            },()=>{
                if(Broken||!Armed||generation!=epoch)
                    throw new Exception("Generate capture stopped. Inspect the pending result before retrying.");
            },()=>wait.ElapsedMilliseconds,()=>Thread.Sleep(100),30000);
            if(acknowledged!=null) {
                WindowAction(window,epoch,(string)anchor.Target["window_key"]);Emit("invoke",anchor.Target,null,epoch);
                send("diagnostic",new {kind="generation_click_acknowledged",pre_click_identity_verified=true,
                    fresh_application_acknowledgement=true,elapsed_ms=wait.ElapsedMilliseconds});
                preparedGeneration=null;return true;
            }
        }
        throw new Exception("Generate click was not acknowledged by the prepared product page. Draft preserved.");
    }
    void QueueWheel(Native.Point point,IntPtr window,int epoch,int delta) {
        WheelBurst burst;
        lock(wheelGate){
            if(wheelBurst!=null&&!wheelBurst.Closed&&wheelBurst.Window==window&&wheelBurst.Epoch==epoch&&
               wheelBurst.Point.X==point.X&&wheelBurst.Point.Y==point.Y){wheelBurst.LastAt=MonotonicMs();wheelBurst.Delta+=delta;return;}
            if(wheelBurst!=null)wheelBurst.Closed=true;
            burst=new WheelBurst(){Point=point,Window=window,Epoch=epoch,LastAt=MonotonicMs(),Delta=delta};wheelBurst=burst;
        }
        Put(()=>{Flush();CaptureScroll(burst);
            // Refresh metadata for a stationary pointer without delaying the
            // ordered action queue behind provider hover inspection.
            if(!Broken&&dropdown==null)QueueHover(burst.Point,burst.Window,true);
        });
    }
    void CaptureScroll(WheelBurst burst) {
        var wait=Stopwatch.StartNew();
        while(!Broken){
            lock(wheelGate){if(burst.Closed||MonotonicMs()-burst.LastAt>=80||wait.ElapsedMilliseconds>=300){burst.Closed=true;break;}}
            Thread.Sleep(10);
        }
        if(Broken)return;
        if(dropdown!=null&&DropdownSelection.ContainsPopup(dropdown.Owner,dropdown.Pid,new System.Windows.Point(burst.Point.X,burst.Point.Y))) {
            ValidateDropdown();
            string view=DropdownSelection.View(dropdown.Owner,dropdown.Pid);
            if(view.Length==0)throw new Exception("Dropdown scrolling exposed no verifiable option view. Draft preserved.");
            var position=DropdownSelection.ScrollPosition(dropdown.Owner,dropdown.Pid);
            bool moved=dropdown.View!=null&&dropdown.View!=view||position.HasValue&&dropdown.ScrollY.HasValue&&Math.Abs(position.Value-dropdown.ScrollY.Value)>0.01;
            bool boundary=position.HasValue&&(burst.Delta<0&&position.Value>=99.99||burst.Delta>0&&position.Value<=0.01);
            if(!moved&&!boundary)throw new Exception("Dropdown scrolling could not confirm movement or a boundary. Draft preserved.");
            // Traversing a choice list belongs to its selection transaction.
            // Replay resolves that option in this owning control, including
            // ScrollItem/ScrollPattern navigation, rather than transient IDs.
            send("diagnostic",new {kind="dropdown_list_navigation",recorded_as="owning control selection",owned_popup=true,
                movement_verified=moved,boundary_verified=boundary});
            dropdown.View=view;dropdown.ScrollY=position;
            return;
        }
        InputWindow(burst.Window);
        var e=AutomationElement.FromPoint(new System.Windows.Point(burst.Point.X,burst.Point.Y));
        var page=e.Current.ControlType==ControlType.Document&&e.Current.AutomationId=="RootWebArea"?e:null;
        uint pid;Native.GetWindowThreadProcessId(burst.Window,out pid);
        var pickerScroll=ProductPickerResult.ScrollContainer(burst.Window,pid,new System.Windows.Point(burst.Point.X,burst.Point.Y));
        if(pickerScroll!=null) {
            if(Broken)return;
            InputWindow(burst.Window);
            var target=Target(pickerScroll,burst.Window);object pattern;
            if(!pickerScroll.TryGetCurrentPattern(ScrollPattern.Pattern,out pattern))
                throw new Exception("The PSD picker scroll position changed. Draft preserved.");
            var position=((ScrollPattern)pattern).Current;
            if(!position.HorizontallyScrollable&&!position.VerticallyScrollable)
                throw new Exception("The PSD picker is no longer scrollable. Draft preserved.");
            WindowAction(burst.Window,burst.Epoch);
            Emit("scroll",target,RecordedScroll(position),burst.Epoch);
            send("diagnostic",new {kind="psd_picker_scroll_resolved",control_type=target["control_type"],automation_id=target["automation_id"]});
            return;
        }
        var inspected=new List<object>();
        // Scroll containers can be layout elements omitted from Control View.
        // Follow the provider's raw ancestry, still bounded to the selected app.
        for(int depth=0;e!=null&&depth<16;depth++,e=TreeWalker.RawViewWalker.GetParent(e)){
            if(e.Current.ProcessId!=pid)throw new Exception("Scroll target left the intended application. Draft preserved.");
            Privacy(e);object pattern;
            // A wheel hit can be a non-scrollable layout group within the page.
            // Retain its nearest document for the same bounded fallback used
            // when Chromium returns the document itself as the hit target.
            if(page==null&&e.Current.ControlType==ControlType.Document&&e.Current.AutomationId=="RootWebArea")page=e;
            bool supported=e.TryGetCurrentPattern(ScrollPattern.Pattern,out pattern);
            var bounds=e.Current.BoundingRectangle;
            inspected.Add(new {control_type=e.Current.ControlType.ProgrammaticName,
                automation_id=Safe(e.Current.AutomationId),is_control=e.Current.IsControlElement,
                contains_pointer=bounds.Contains(new System.Windows.Point(burst.Point.X,burst.Point.Y)),
                scroll_pattern=supported});
            if(supported){
                var scroll=((ScrollPattern)pattern).Current;
                if(!scroll.HorizontallyScrollable&&!scroll.VerticallyScrollable)continue;
                var target=Target(e,burst.Window,true);WindowAction(burst.Window,burst.Epoch);
                Emit("scroll",target,RecordedScroll(scroll),burst.Epoch);
                return;
            }
            if(e.Current.NativeWindowHandle==burst.Window.ToInt32())break;
        }
        // Chromium sometimes reports a document or layout group for a wheel hit, while
        // the actual overflow container is a raw descendant. Search only that
        // page, only branches under the pointer, and require one eligible target.
        if(page!=null) {
            var point=new System.Windows.Point(burst.Point.X,burst.Point.Y);
            var search=new ScrollTargetSearch<AutomationElement>(
                node=>node.Current.ProcessId==pid&&!node.Current.IsOffscreen&&node.Current.BoundingRectangle.Contains(point),
                node=>{object candidate;if(!node.TryGetCurrentPattern(ScrollPattern.Pattern,out candidate))return false;
                    var position=((ScrollPattern)candidate).Current;return position.HorizontallyScrollable||position.VerticallyScrollable;},
                RawChildren,transparent:node=>TransparentLayout(node,pid));
            var container=search.Find(page);
            if(container!=null) {
                if(Broken)return;
                if(Native.Root(Native.GetForegroundWindow())!=burst.Window)
                    throw new Exception("Focus changed while identifying the scroll container. Draft preserved.");
                var target=Target(container,burst.Window,true);object pattern;
                if(!container.TryGetCurrentPattern(ScrollPattern.Pattern,out pattern))
                    throw new Exception("The scroll container changed before its position was read. Draft preserved.");
                var position=((ScrollPattern)pattern).Current;
                if(!position.HorizontallyScrollable&&!position.VerticallyScrollable)
                    throw new Exception("The scroll container is no longer scrollable. Draft preserved.");
                WindowAction(burst.Window,burst.Epoch);
                Emit("scroll",target,RecordedScroll(position),burst.Epoch);
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
    static bool TransparentLayout(AutomationElement node,uint pid) {
        var current=node.Current;
        return current.ProcessId==pid&&!current.IsOffscreen&&current.BoundingRectangle.IsEmpty&&
            (current.ControlType==ControlType.Group||current.ControlType==ControlType.Pane||current.ControlType==ControlType.Custom);
    }
    static Dictionary<string,object> RecordedScroll(ScrollPattern.ScrollPatternInformation position) {
        return new Dictionary<string,object>{
            {"horizontal",position.HorizontallyScrollable?position.HorizontalScrollPercent:ScrollPattern.NoScroll},
            {"vertical",position.VerticallyScrollable?position.VerticalScrollPercent:ScrollPattern.NoScroll},
            {"horizontal_view_size",position.HorizontalViewSize},{"vertical_view_size",position.VerticalViewSize}};
    }
    IntPtr OnKey(int c,IntPtr w,IntPtr l) {
        // Suppress the matching release/repeats even if the worker interrupts.
        // No accessibility or clipboard access is performed on the hook thread.
        if(c>=0&&swallowedPromptPaste) {
            var held=(Native.Key)Marshal.PtrToStructure(l,typeof(Native.Key));
            if(held.vk==86) {
                if(w.ToInt32()==0x101||w.ToInt32()==0x105)swallowedPromptPaste=false;
                return new IntPtr(1);
            }
        }
        if(BrowserDownload.OwnedSaveDialog(Native.GetForegroundWindow(),downloadSaveOwner))return Native.CallNextHookEx(IntPtr.Zero,c,w,l);
        if(c>=0&&Armed&&!Mine(Native.Root(Native.GetForegroundWindow()))&&(w.ToInt32()==0x100||w.ToInt32()==0x104||w.ToInt32()==0x101||w.ToInt32()==0x105)){
            var k=(Native.Key)Marshal.PtrToStructure(l,typeof(Native.Key));
            if(ChatImageAttachment.OwnPasteKey(k.flags,k.extra,k.vk)||LocalUploads.OwnConfirmKey(k.flags,k.extra,k.vk))
                return Native.CallNextHookEx(IntPtr.Zero,c,w,l);
            if(injected||(k.flags&16)==0){
                bool transitionKey=DesktopSession&&k.vk==9&&(Native.GetAsyncKeyState(18)&0x8000)!=0;
                if(w.ToInt32()==0x100||w.ToInt32()==0x104){
                    var lease=promptPasteAnchor;
                    if(lease!=null&&KeyboardIntent.ControlledPromptPaste(k.vk,(Native.GetAsyncKeyState(17)&0x8000)!=0,
                        (Native.GetAsyncKeyState(18)&0x8000)!=0,lease.Window==Native.Root(Native.GetForegroundWindow()),lease.Epoch==generation)) {
                        promptPasteAnchor=null;swallowedPromptPaste=true;
                        Put(()=>ControlledPromptPaste(lease));return new IntPtr(1);
                    }
                    if(transitionKey)PhysicalTransition(k.time);return Native.CallNextHookEx(IntPtr.Zero,c,w,l);
                }
                if(transitionKey)return Native.CallNextHookEx(IntPtr.Zero,c,w,l);
                if(k.vk==16||k.vk==17||k.vk==18||k.vk==91||k.vk==92||(k.vk>=160&&k.vk<=165))return Native.CallNextHookEx(IntPtr.Zero,c,w,l);
                CloseWheelBurst();
                var window=Native.Root(Native.GetForegroundWindow());int epoch=generation;
                long observed=Stopwatch.GetTimestamp();
                bool ctrl=(Native.GetAsyncKeyState(17)&0x8000)!=0;
                bool alt=(Native.GetAsyncKeyState(18)&0x8000)!=0;
                bool shortcut=ctrl||alt;
                bool editShortcut=ctrl&&!alt&&(k.vk==86||k.vk==88);
                bool copyShortcut=ctrl&&!alt&&k.vk==67;
                bool selectAll=ctrl&&!alt&&k.vk==65;
                bool tab=KeyboardIntent.EditorTab(k.vk,ctrl,alt);
                bool browserTab=KeyboardIntent.BrowserTab(k.vk,ctrl,alt);
                Put(()=>{if(browserTab){Flush();RecordBrowserTab(window,epoch);return;}if(DropdownKey(window,shortcut))return;if(tab){Flush();AnchorFocusedEditor(window);return;}if(selectAll)return;if(copyShortcut){if((Stopwatch.GetTimestamp()-observed)/(double)Stopwatch.Frequency>0.25)throw new Exception("Copy observation was delayed. Draft preserved.");Flush();CopyIntent(window,epoch);return;}if(ctrl&&!alt&&k.vk==86){PasteIntent(window,epoch);return;}if(shortcut&&!editShortcut){Flush();Interrupt("This keyboard shortcut is not yet supported. Draft preserved.");return;}
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
    Dictionary<string,object> Target(AutomationElement e,IntPtr h,bool allowAnonymousScroll=false) {
        Native.CheckProcess(h);Privacy(e);
        var proc=Native.ProcessFor(h);
        string title=Safe(Native.Title(h));
        string id=Safe(e.Current.AutomationId),name=Safe(e.Current.Name);
        bool anonymous=id.Length==0&&name.Length==0;
        if(anonymous&&(!allowAnonymousScroll||!ScrollAccess.IsLayout(e)))throw new Exception("This control has no reliable identity. Draft preserved.");
        if(title.Length==0)throw new Exception("This window has no document identity.");
        var scope=new List<object>();
        bool productPicker=ProductPickerResult.KnownButton(proc.MainModule.FileName,e.Current.ControlType.ProgrammaticName.Replace("ControlType.",""),id,name);
        if(!productPicker&&ProductPickerResult.KnownScrollTarget(proc.MainModule.FileName,id,name))
            productPicker=ProductPickerResult.Document(e,h,(uint)proc.Id)!=null;
        bool combo=e.Current.ControlType==ControlType.ComboBox;
        int ancestryLimit=DropdownSelection.AncestryLimit;
        // Named owning controls survive generated option/input IDs changing
        // after a browser rerender. Exact ancestor scope and uniqueness remain.
        if(combo&&name.Length>0)id="";
        bool productImage=ProductImageResult.KnownButton(proc.MainModule.FileName,e.Current.ControlType.ProgrammaticName.Replace("ControlType.",""),id,name);
        bool productCopy=productImage||ProductCopyResult.KnownButton(proc.MainModule.FileName,e.Current.ControlType.ProgrammaticName.Replace("ControlType.",""),id,name),hostSkipped=false;
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
        if(anonymous) {
            if(scope.Count==0)throw new Exception("Anonymous scroll container has no stable owning scope. Draft preserved.");
            target["selector"]=ScrollAccess.ScopedSelector;
            var unique=ScrollAccess.ResolveScoped(h,target);
            if(!Automation.Compare(e,unique))throw new Exception("Anonymous scroll container identity changed. Draft preserved.");
        }
        if(ProductPickerResult.KnownButton(proc.MainModule.FileName,(string)target["control_type"],id,name)&&
            ProductPickerResult.Document(e,h,(uint)proc.Id)!=null)target["postcondition"]=ProductPickerResult.Contract;
        if(generation) {
            if(!ProductGenerationResult.StableScope(scope))throw new Exception("Generation scope is not supported. Draft preserved.");
            target["postcondition"]=ProductGenerationResult.Contract;
        }
        var browser=e.Current.NativeWindowHandle==h.ToInt32()||productCopy||(e.Current.ControlType==ControlType.Edit&&name==ChatImageAttachment.EditorName)?BrowserIdentity.Current(h):BrowserIdentity.Read(e);
        if(browser!=null)target["browser"]=browser;
        if(productImage) {
            if(!ProductImageResult.Supports(target))throw new Exception("Image copy needs the verified prepared product and gallery scope.");
            target["postcondition"]=ProductImageResult.Contract;
        }
        var download=BrowserDownload.Read(e);
        if(download!=null){
            if(!BrowserTabs.Edge(h))throw new Exception("Download receipts require the configured Edge bridge. Chrome download capture is not enabled.");
            if(browser==null)throw new Exception("Download requires the verified preview adapter.");target["download"]=download;
        }
        if((generation||productCopy&&name=="Copy Black Frame Prompt")&&(browser==null||!browser.ContainsKey("product"))) {
            send("diagnostic",new {kind="prepared_product_identity_missing",browser_identity_present=browser!=null,
                product_fingerprint_present=browser!=null&&browser.ContainsKey("product"),generation_control=generation});
            throw new Exception(browser==null?
                "The browser adapter has not identified this control. Draft preserved.":
                "The prepared product fingerprint is unavailable. Verify the product, category and exact PSD revision. Draft preserved.");
        }
        if(productCopy&&name=="Copy Black Frame Prompt") {
            var proof=ProductPromptProof.Parse(e.Current.HelpText);
            if(proof==null)throw new Exception("The complete prompt is not ready for verification. Draft preserved.");
            target["prompt_proof"]=proof;
        }
        return target;
    }
    void WindowAction(IntPtr h,int epoch,string anchoredTitle=null,Dictionary<string,object> anchoredBrowser=null) {
        if(!DesktopSession&&lastWindow==IntPtr.Zero&&preparedWindow!=IntPtr.Zero&&h!=preparedWindow)
            throw new Exception("Start in the selected prepared window. Stop and save, then select the intended window.");
        string title=anchoredTitle??Native.Title(h);
        if(lastWindow==h&&lastTitle==title)return;
        Native.CheckProcess(h);
        var root=AutomationElement.FromHandle(h);
        Dictionary<string,object> target;
        if(anchoredBrowser!=null&&BrowserDownload.OwnedSaveDialog(Native.GetForegroundWindow(),h)) {
            // Windows disables the owner during Save As. This is metadata for
            // the witnessed browser window switch, not an action on a disabled
            // control. The actual source button was independently identified.
            BrowserDownload.ValidateSaveDialogProcess(Native.GetForegroundWindow(),h);
            target=new Dictionary<string,object>{{"app",Native.ProcessFor(h).MainModule.FileName},
                {"control_type","Window"},{"scope",new object[0]}};
            Safe(title);
        } else target=Target(root,h);
        target["automation_id"]="window";target["window_key"]=title;target["name"]=title;
        if(anchoredBrowser!=null) {
            var browser=new Dictionary<string,object>(anchoredBrowser);
            browser["control"]="document";browser["frame"]="top";
            target["browser"]=browser;
        }
        // Retain the witnessed source page when leaving a browser for a native
        // app. A later tab transition must still validate that source on replay.
        if(lastWindow!=h&&lastWindow!=IntPtr.Zero&&lastBrowser!=null&&BrowserTabs.Chromium(lastWindow)) {
            uint previousPid;Native.GetWindowThreadProcessId(lastWindow,out previousPid);
            browserWindowContexts[lastWindow]=new BrowserWindowContext{Pid=previousPid,Title=lastTitle,Browser=new Dictionary<string,object>(lastBrowser)};
        }
        Emit("focus_window",target,null,epoch);lastWindow=h;lastTitle=title;preparedWindow=IntPtr.Zero;
        if(DesktopSession){ObserveInvocations(h);sessionStates[h]=DesktopWindowState.Read(h);}
    }
    void InputWindow(IntPtr h) {
        if(!DesktopSession&&!WindowIdentity.InitialMatches(preparedWindow,h))
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
        if(kind=="invoke"&&target.ContainsKey("download")) {
            Dictionary<string,object> result;
            var source=(Dictionary<string,object>)target["download"];
            // Dialog gestures belong to this download, not separate replayable
            // text/click actions. Only a completed receipt retains the chosen folder.
            if((bool)source["save_as"])downloadSaveOwner=lastWindow;
            Func<bool> ownedDialog=()=>{
                var modal=Native.GetForegroundWindow();
                if(!BrowserDownload.OwnedSaveDialog(modal,downloadSaveOwner))return false;
                if(!downloadDialogNotifications.IsObserved(modal,downloadSaveOwner,epoch)) {
                    BrowserDownload.ValidateSaveDialogProcess(modal,downloadSaveOwner);
                    downloadDialogNotifications.Observe(modal,downloadSaveOwner,epoch,MonotonicMs());
                    send("diagnostic",new {kind="download_capture_dialog_observed",owned_save_dialog=true});
                }
                return true;
            };
            try {
                ownedDialog();
                result=downloadSession.Wait(source,downloadClickAt,()=>{
                    if(Broken||!Armed||generation!=epoch)throw new Exception("Download capture stopped. Draft preserved; check the pending file before another download.");
                },()=>Interlocked.Exchange(ref BusySince,Stopwatch.GetTimestamp()),
                  ownedDialog);
            } finally {downloadDialogNotifications.Complete(MonotonicMs());downloadSaveOwner=IntPtr.Zero;}
            BrowserDownload.Persist(result);
            kind="browser_download";value=new Dictionary<string,object>{{"directory",System.IO.Path.GetDirectoryName((string)result["path"])}};
        }
        if(kind=="invoke"&&target.ContainsKey("prompt_proof")) {
            capturedTransfer.Clear();capturedImage.Clear();latestTransfer=-1;
            var proof=(Dictionary<string,object>)target["prompt_proof"];
            var wait=Stopwatch.StartNew();
            while(!ProductPromptProof.ClipboardMatches(proof)&&wait.ElapsedMilliseconds<1500&&!Broken) {
                Interlocked.Exchange(ref BusySince,Stopwatch.GetTimestamp());Thread.Sleep(20);
            }
            if(!Broken&&!ProductPromptProof.ClipboardMatches(proof)) {
                string observed=RunTransfer.ClipboardText();
                send("diagnostic",new {kind="prompt_copy_mismatch",utf16_length=observed.Length,
                    utf8_length=System.Text.Encoding.UTF8.GetByteCount(observed),
                    crlf_count=(observed.Length-observed.Replace("\r\n","").Length)/2,
                    normalized_matches=ProductPromptProof.Matches(observed.Replace("\r\n","\n"),proof)});
            }
            if(Broken||!ProductPromptProof.ClipboardMatches(proof))throw new Exception("Copy prompt result was not verified. No transfer retained; draft preserved.");
            string copiedPrompt=RunTransfer.ClipboardText();
            if(!ProductPromptProof.Matches(copiedPrompt,proof))throw new Exception("Clipboard changed during Copy validation. No transfer retained.");
            latestTransfer=transferSerial++;capturedTransfer.Observe(latestTransfer,copiedPrompt);
            target=new Dictionary<string,object>(target);target.Remove("prompt_proof");
            kind="transfer_copy_button";value=new Dictionary<string,object>{{"slot",latestTransfer},{"mode","application_prompt"}};
        }
        if(target.ContainsKey("browser")) {
            lastBrowser=(Dictionary<string,object>)target["browser"];
            // A successfully recorded in-page action may intentionally change
            // scope. Subsequent taskbar returns must use that witnessed scope.
            if(kind!="taskbar_activate"&&lastWindow!=IntPtr.Zero)
                shellBrowserScopes[lastWindow]=new Dictionary<string,object>(lastBrowser);
        }
        var caps=new Dictionary<string,string>{{"invoke","uia.invoke.v1"},{"set_text","uia.value.v1"},{"copy_text","clipboard.copy-text.v1"},{"select","uia.selection.v1"},{"toggle","uia.toggle.v1"},{"focus_window","windows.focus.v1"},{"window_state","windows.state.v1"},{"expand","uia.expand.v1"},{"scroll","uia.scroll.v1"}};
        caps["taskbar_activate"]="windows.taskbar.v3";
        caps["browser_tab"]="edge.tab.v1";
        caps["browser_navigation"]="edge.navigation.v3";
        caps["browser_download"]="edge.download.v3";
        caps["local_upload"]="local.upload.v3";caps["chat_download"]="chat.download.v3";caps["chat_wait"]="chat.wait.v3";caps["chat_submit"]="chat.submit.v3";caps["image_paste"]="image.paste.v3";caps["transfer_copy"]="transfer.editor-copy.v3";caps["transfer_copy_button"]="transfer.prompt-copy.v3";caps["transfer_paste"]="transfer.paste.v3";
        var a=new Dictionary<string,object>{{"version",kind.StartsWith("transfer_")||kind=="local_upload"||kind=="chat_download"||kind=="chat_wait"||kind=="chat_submit"||kind=="image_paste"||kind=="browser_download"||kind=="browser_navigation"||kind=="taskbar_activate"?3:2},{"kind",kind},{"requires",new[]{caps[kind].Replace(".v1",".v2")}},{"target",target},{"timeout_ms",(kind=="local_upload"||kind=="chat_download")?300000:kind=="chat_wait"?900000:kind=="browser_download"||kind=="chat_submit"||LocalSaveResult.Supports(target)?30000:8000},{"observed_ms",clock.ElapsedMilliseconds}};
        if(kind=="image_paste"||kind=="invoke"&&(ProductGenerationResult.Supports(target)||ProductImageResult.Supports(target)))a["timeout_ms"]=30000;
        if(kind=="taskbar_activate"&&value is Dictionary<string,object>) {
            var route=(Dictionary<string,object>)value;
            if(route.ContainsKey("thumbnail")&&Equals(((Dictionary<string,object>)route["thumbnail"])["class_name"],ThumbnailCaption.Marker)) {
                a["requires"]=new[]{"windows.taskbar.v3","windows.taskbar.caption.v1"};a["timeout_ms"]=20000;
            }
        }
        if(value!=null)a["value"]=value;
        send("event",new {generation=epoch,privacy="safe",action=a});
    }
    bool CompleteBrowserNavigation(Native.Point point,IntPtr window,int epoch,GenerationGesture gesture) {
        if(gesture==null||!BrowserTabs.Chromium(window))return false;
        // An anchored download has its own completion contract. In particular,
        // Save As transfers focus to an owned modal without navigating the page.
        if(semanticClick!=null&&semanticClick.Target.ContainsKey("download"))return false;
        // Prefer the pre-click control identity. A navigation may be the
        // first action, so a previous recorded page is not required when
        // the trusted gesture itself supplies its source identity.
        var source=semanticClick!=null&&semanticClick.Target.ContainsKey("browser")?
            (Dictionary<string,object>)semanticClick.Target["browser"]:lastBrowser;
        uint pid;Native.GetWindowThreadProcessId(window,out pid);
        InvocationWitness found=null;var wait=Stopwatch.StartNew();
        do {
            foreach(var witness in invocations.ToArray()) {
                if(witness.Epoch!=epoch||witness.Pid!=pid||witness.At<gesture.StartedAt||witness.At-gesture.StartedAt>1500||
                    !witness.Bounds.Contains(new System.Windows.Point(point.X,point.Y))||witness.Browser==null||
                    (source!=null&&!BrowserIdentity.SamePage(witness.Browser,source)))continue;
                if(found!=null&&found.RuntimeId!=witness.RuntimeId)throw new Exception("Browser invocation identity is ambiguous. Draft preserved.");
                found=witness;
            }
            if(found!=null||wait.ElapsedMilliseconds>=300||Broken)break;
            Thread.Sleep(10);
        }while(true);
        bool browserWitness=false;Dictionary<string,object> witnessedDownload=null;
        if(found==null||BrowserDownload.OwnedSaveDialog(Native.GetForegroundWindow(),window)) {
            send("diagnostic",new {kind="navigation_capture_stage",stage="gesture-marker-lookup"});
            var marker=AutomationElement.FromHandle(window).FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.AutomationIdProperty,"sc-recorder-button-gesture"));
            send("diagnostic",new {kind="navigation_witness_lookup",marker_count=marker.Count,gesture_age_ms=MonotonicMs()-gesture.StartedAt,source=source});
            if(marker.Count==1) {
                string help=marker[0].Current.HelpText;
                string prefix=help.StartsWith("Sports Cave button gesture v2: ",StringComparison.Ordinal)?"Sports Cave button gesture v2: ":"Sports Cave button gesture v1: ";
                if(help.StartsWith(prefix,StringComparison.Ordinal)&&help.Length<=7000) {
                    var raw=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(Uri.UnescapeDataString(help.Substring(prefix.Length)));
                    if((raw.Count==3||prefix.Contains("v2")&&raw.Count==5)&&raw.ContainsKey("identity")&&raw.ContainsKey("time")&&raw.ContainsKey("name")) {
                        long timestamp=Convert.ToInt64(raw["time"]);
                        var identity=BrowserIdentity.ReadHelp("Sports Cave browser v2: "+Uri.EscapeDataString(new JavaScriptSerializer().Serialize(raw["identity"])));
                        send("diagnostic",new {kind="navigation_witness_check",control=Safe((string)raw["name"]),identity=identity,source_matches=source==null||BrowserIdentity.SamePage(identity,source),pointer_delta_ms=timestamp-gesture.UtcMilliseconds,witness_age_ms=(DateTime.UtcNow.Ticks-621355968000000000)/10000-timestamp});
                        if(timestamp>=gesture.UtcMilliseconds-20&&timestamp<=gesture.UtcMilliseconds+300&&
                            (DateTime.UtcNow.Ticks-621355968000000000)/10000-timestamp<=2000&&identity!=null&&
                            (source==null||BrowserIdentity.SamePage(identity,source))) {
                            if(found!=null&&!BrowserIdentity.SameControl(found.Browser,identity))throw new Exception("Browser click witnesses disagree. Draft preserved.");
                            witnessedDownload=BrowserDownload.WitnessDownload(raw,identity,point,AutomationElement.FromHandle(window).Current.BoundingRectangle,Native.GetDpiForWindow(window));
                            found=new InvocationWitness{Browser=identity,Name=Safe((string)raw["name"]),Id=""};browserWitness=true;
                        }
                    }
                }
            }
        }
        if(found==null){send("diagnostic",new {kind="navigation_invocation_unavailable",received=invocationReceived,cache_failures=invocationCacheFailures});return false;}
        var localFollowupTarget=new Dictionary<string,object>{{"app",Native.ProcessFor(window).MainModule.FileName},{"window_key",Safe(Native.Title(window))},
            {"control_type","Button"},{"automation_id","send"},{"name",found.Name},{"scope",new object[0]},{"browser",found.Browser}};
        if(LocalFollowupResult.Supports(localFollowupTarget)) {
            LocalFollowupResult.Wait(window,localFollowupTarget,()=>{
                if(Broken||!Armed||epoch!=generation||Native.Root(Native.GetForegroundWindow())!=window)throw new OperationCanceledException();
                Interlocked.Exchange(ref BusySince,Stopwatch.GetTimestamp());
            },8000);
            semanticClick=null;WindowAction(window,epoch,null,found.Browser);
            Emit("invoke",localFollowupTarget,null,epoch);
            send("diagnostic",new {kind="local_followup_capture_verified",trusted_pointer_witness=browserWitness,simulated=true});return true;
        }
        Dictionary<string,object> destination=null;
        string expectedMapping=BrowserIdentity.MappingDestination(found.Browser);
        var transitionWait=Stopwatch.StartNew();
        do {
        if(BrowserDownload.OwnedSaveDialog(Native.GetForegroundWindow(),window)) {
            BrowserDownload.ValidateSaveDialogProcess(Native.GetForegroundWindow(),window);
            // The trusted pointer-down witness retains only bounded source
            // metadata, after browser-level unique-control validation. Do not
            // query a disabled webpage behind its owned modal: even an exact
            // AutomationId lookup can stall in the accessibility provider.
            if(witnessedDownload==null)throw new Exception("Save As capture requires browser adapter 0.3.4. Reload the prepared development adapter; draft preserved. Check the pending download before trying again.");
            string control=(string)found.Browser["control"];
            var downloadTarget=new Dictionary<string,object>{{"app",Native.ProcessFor(window).MainModule.FileName},{"window_key",Safe(Native.Title(window))},
                {"control_type","Button"},{"automation_id",control.StartsWith("id:",StringComparison.Ordinal)?control.Substring(3):""},
                {"name",found.Name},{"scope",new object[0]},{"browser",found.Browser},{"download",witnessedDownload}};
            send("diagnostic",new {kind="save_as_source_witness",browser_identity=true,unique_control=true,physical_point_and_scale=true});
            if(Broken||epoch!=generation||!BrowserDownload.OwnedSaveDialog(Native.GetForegroundWindow(),window))
                throw new Exception("Save As ownership changed during capture. Draft preserved.");
            send("diagnostic",new {kind="navigation_capture_stage",stage="save-as-window-action"});
            RecordInvocation(window,epoch,downloadTarget);
            return true;
        }
            if(Broken||epoch!=generation||Native.Root(Native.GetForegroundWindow())!=window) {
                var foreground=Native.GetForegroundWindow();
                send("diagnostic",new {kind="navigation_focus_lost",foreground=Native.WindowMetadata(foreground),
                    foreground_root=Native.WindowMetadata(Native.GetAncestor(foreground,2)),
                    foreground_owner=Native.WindowMetadata(Native.GetAncestor(foreground,3)),
                    owned_save_as=BrowserDownload.OwnedSaveDialog(foreground,window)});
                throw new Exception("Navigation capture lost its owning window. Draft preserved.");
            }
            destination=BrowserIdentity.Current(window);
            if(destination!=null&&Equals(destination["profile"],found.Browser["profile"])&&!Equals(destination["page"],found.Browser["page"])) {
                if(expectedMapping!=null&&!Equals(destination["page"],expectedMapping))throw new Exception("Mapping opened an unexpected page. Draft preserved.");
                break;
            }
            if(transitionWait.ElapsedMilliseconds>=(expectedMapping==null?1500:8000)) {
                send("diagnostic",new {kind="navigation_destination_timeout",expected=expectedMapping,source=found.Browser,destination=destination,elapsed_ms=transitionWait.ElapsedMilliseconds});
                if(expectedMapping!=null)throw new Exception("Mapping destination was not verified within eight seconds. Draft preserved; no generic click recorded.");
                return false;
            }
            Interlocked.Exchange(ref BusySince,Stopwatch.GetTimestamp());
            Thread.Sleep(25);
        }while(true);
        WindowAction(window,epoch,null,found.Browser);
        var target=new Dictionary<string,object>{{"app",Native.ProcessFor(window).MainModule.FileName},{"window_key",Safe(lastTitle)},
            {"control_type","Button"},{"automation_id",found.Id},{"name",found.Name},{"scope",new object[0]},{"browser",found.Browser}};
        semanticClick=null; // The same physical gesture cannot also emit Invoke.
        Emit("browser_navigation",target,destination,epoch);lastBrowser=destination;
        send("diagnostic",new {kind="browser_navigation_captured",invocation_witness=!browserWitness,trusted_browser_witness=browserWitness,source_and_destination_verified=true});
        return true;
    }
    void RecordBrowserTab(IntPtr h,int epoch) {
        captureOperation="browser tab: validate input window";
        InputWindow(h);
        if(lastWindow!=h) {
            BrowserWindowContext previous;uint currentPid;Native.GetWindowThreadProcessId(h,out currentPid);
            if(!DesktopSession||!browserWindowContexts.TryGetValue(h,out previous)||previous.Pid!=currentPid||String.IsNullOrEmpty(previous.Title))
                throw new Exception("Record an action on the starting page before switching tabs. Draft preserved.");
            WindowAction(h,epoch,previous.Title,previous.Browser);
        }
        if(String.IsNullOrEmpty(lastTitle))throw new Exception("The starting browser page was not identified. Draft preserved.");
        string page=null,profile;
        var tabReady=Stopwatch.StartNew();
        while(true) {
            if(Broken)return;
            InputWindow(h);
            if(Native.Root(Native.GetForegroundWindow())!=h)throw new Exception("Browser focus changed during tab capture. Draft preserved.");
            // Edge publishes selected-tab, caption and document updates in
            // separate UIA notifications. Retry only these reads; never click
            // again or suppress an ambiguous selected-tab result.
            captureOperation="browser tab: selected chrome tab lookup";
            var tab=BrowserTabs.Find(h,null,true);
            captureOperation="browser tab: document agreement";
            if(WindowIdentity.EdgeTitle(Native.Title(h),out page,out profile)&&
               WindowIdentity.EdgeTabNameMatches(page,tab.Current.Name)&&BrowserTabs.Document(h,page))break;
            if(tabReady.ElapsedMilliseconds>=750)
                throw new Exception("The selected browser tab, window title and document did not agree within the readiness deadline. Draft preserved.");
            Thread.Sleep(25);
        }
        Safe(page);
        if(Native.Root(Native.GetForegroundWindow())!=h)throw new Exception("Browser focus changed during tab capture. Draft preserved.");
        var target=new Dictionary<string,object>{{"app",Native.ProcessFor(h).MainModule.FileName},
            {"window_key",Safe(lastTitle)},{"control_type","TabItem"},{"automation_id",""},{"name",page},{"scope",new object[0]}};
        captureOperation="browser tab: destination identity";
        var destination=BrowserIdentity.Current(h);
        if(lastBrowser==null||destination==null)throw new Exception("Both tabs need the compatible preview browser adapter. Draft preserved.");
        if(!Equals(lastBrowser["profile"],destination["profile"]))throw new Exception("Browser profile changed during tab capture. Draft preserved.");
        target["source_browser"]=lastBrowser;target["browser"]=destination;
        Emit("browser_tab",target,null,epoch);
        lastTitle=Native.Title(h);editorAnchor=null;editorAnchorTarget=null;pendingEditorClick.Clear();
    }
    void Click(Native.Point p,IntPtr h,int epoch) {
        if(Broken)return;
        if(Native.IsTaskbar(h)){
            throw new Exception("Taskbar click has no verified pre-click shell identity. Draft preserved.");
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
            if(e.Current.ControlType==ControlType.TabItem&&BrowserTabs.Edge(h)&&BrowserTabs.ChromeTab(e,h)){RecordBrowserTab(h,epoch);return;}
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
                if(e.Current.ControlType==ControlType.ComboBox&&expanded==ExpandCollapseState.Expanded) {
                    // A fast opening click may finish before the mouse-down worker
                    // can inspect it. The mouse-up path has identified this exact
                    // combobox at the physical point; anchor its current owned
                    // popup now, before a later option click can close it. Never
                    // infer an option from the page exposed after that later click.
                    AnchorReleasedDropdown(e,p,h,epoch);return;
                }
                var t=Target(e,h);WindowAction(h,epoch);Emit("expand",t,expanded==ExpandCollapseState.Expanded,epoch);return;
            }
            if(e.TryGetCurrentPattern(InvokePattern.Pattern,out pattern)){
                var t=Target(e,h);
                if(ProductImageResult.Supports(t))throw new Exception("Image Copy lacked a verified pre-click clipboard anchor. Draft preserved; Copy was not repeated.");
                RecordInvocation(h,epoch,t);return;
            }
        }
        send("diagnostic",new {kind="unsupported_click",control_types=seen,window_title=Native.Title(h),
            foreground_title=Native.Title(Native.Root(Native.GetForegroundWindow()))});
        Interrupt("This clicked control is not supported ("+String.Join(", ",seen.ToArray())+"). Draft preserved.");
    }
    void ValidateDropdown(bool foreground=true) {
        var active=dropdown;
        if(active==null)return;
        uint pid;Native.GetWindowThreadProcessId(active.Window,out pid);
        if(active.Epoch!=generation||pid!=active.Pid||foreground&&Native.Root(Native.GetForegroundWindow())!=active.Window||
            Native.GetDpiForWindow(active.Window)!=active.Dpi||
            AutomationElement.FromHandle(active.Window).Current.BoundingRectangle!=active.WindowBounds)
            throw new Exception("The dropdown's owning window moved or changed. Draft preserved.");
        try{DropdownSelection.Safe(active.Owner,pid);}
        catch(ElementNotAvailableException){RebindDropdown();}
    }
    void RebindDropdown() {
        var active=dropdown;var wait=Stopwatch.StartNew();var json=new JavaScriptSerializer();
        string expected=json.Serialize(active.Target);
        do {
            var root=AutomationElement.FromHandle(active.Window);
            var matches=root.FindAll(TreeScope.Descendants,new AndCondition(
                new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.ComboBox),
                new PropertyCondition(AutomationElement.NameProperty,active.Target["name"])));
            if(matches.Count>64)throw new Exception("The dropdown's replacement is ambiguous.");
            AutomationElement found=null;
            foreach(AutomationElement item in matches) {
                if(item.Current.IsOffscreen)continue;
                DropdownSelection.Safe(item,active.Pid);
                if(json.Serialize(Target(item,active.Window))!=expected)continue;
                if(found!=null)throw new Exception("The dropdown's replacement is not unique.");
                found=item;
            }
            if(found!=null){active.Owner=found;return;}
            if(wait.ElapsedMilliseconds>=500)break;
            Thread.Sleep(25);
        }while(!Broken);
        throw new Exception("The owning dropdown did not return after its document updated. Draft preserved.");
    }
    void SnapshotSemanticClick(Native.Point point,IntPtr window,int epoch,long at,GenerationGesture gesture) {
        semanticClick=null;
        if(Broken||Native.IsTaskbar(window)||expectedGenerationDown||expectedPickerDown||dropdown!=null)return;
        var cached=gesture.Hover;
        if(cached!=null&&(invocationWindow==window||LocalSaveResult.Supports(cached.Target))&&cached.Window==window&&cached.Epoch==epoch&&at>=cached.At&&at-cached.At<=HoverFreshnessMs&&
            cached.ControlBounds.Contains(new System.Windows.Point(point.X,point.Y))) {
            uint actualPid;Native.GetWindowThreadProcessId(window,out actualPid);
            if(actualPid!=cached.Pid||Native.GetDpiForWindow(window)!=cached.Dpi||
                AutomationElement.FromHandle(window).Current.BoundingRectangle!=cached.WindowBounds)
                throw new Exception("The hovered control changed before the click. Draft preserved.");
            semanticClick=new SemanticClick{Control=cached.Control,Target=cached.Target,Window=window,Pid=cached.Pid,Dpi=cached.Dpi,
                Epoch=epoch,At=at,ControlBounds=cached.ControlBounds,WindowBounds=cached.WindowBounds,RuntimeId=cached.RuntimeId,NeedsInvocation=true,ClipboardBefore=cached.ClipboardBefore,SaveBefore=cached.SaveBefore};
            send("diagnostic",new {kind="semantic_button_before_click",control_type=cached.Target["control_type"],scope_validated=true,
                pre_click_age_ms=at-cached.At,confirmation=DialogResult.Supports(cached.Target)?"containing modal dismissal":"invocation event"});
            return;
        }
        var active=activeHover;var completed=lastHover;
        send("diagnostic",new {kind="button_preflight_missing",released_before_discovery=Interlocked.Read(ref gesture.ReleasedAt)!=0,
            queue_delay_ms=MonotonicMs()-at,cached_present=cached!=null,
            cached_contains_click=cached!=null&&cached.ControlBounds.Contains(new System.Windows.Point(point.X,point.Y)),
            cached_age_ms=cached==null?(long?)null:at-cached.At,hover_updates_coalesced=hoverBusyUpdates,
            active_hover_ms=active==null?(long?)null:MonotonicMs()-active.Started,
            active_point_matches=active!=null&&active.Window==window&&active.Point.X==point.X&&active.Point.Y==point.Y,
            completed_hover_ms=completed==null?(long?)null:completed.Completed-completed.Started,
            completed_found=completed!=null&&completed.Found,completed_error=completed==null?null:completed.Error,
            completed_point_matches=completed!=null&&completed.Window==window&&completed.Point.X==point.X&&completed.Point.Y==point.Y});
        if(Interlocked.Read(ref gesture.ReleasedAt)!=0)return; // Never discover a target after its action.
        captureOperation="mouse-down button discovery";
        semanticClick=ReadButton(point,window,epoch,at);
        if(Interlocked.Read(ref gesture.ReleasedAt)!=0||MonotonicMs()-at>250)semanticClick=null;
        if(semanticClick!=null)send("diagnostic",new {kind="semantic_button_before_click",control_type=semanticClick.Target["control_type"],scope_validated=true});
    }
    void QueueHover(Native.Point point,IntPtr window,bool force=false) {
        // Metadata preflight only while armed; never read field values. A
        // physical mouse-down takes a completed, fresh pre-action snapshot.
        long now=MonotonicMs();
        if(Native.IsTaskbar(window))return;
        // A completed wheel observation must not replace a newer physical
        // pointer location with the old location of that wheel burst.
        var pointer=physicalPointer;
        if(force&&(pointer==null||pointer.Window!=window||pointer.Point.X!=point.X||pointer.Point.Y!=point.Y))return;
        var old=hoverClick;
        if(!force&&old!=null&&old.Window==window&&now-old.At<HoverFreshnessMs/2&&old.ControlBounds.Contains(new System.Windows.Point(point.X,point.Y)))return;
        lock(hoverGate) {
            pendingHover=new HoverProbe{Point=point,Window=window,Epoch=generation};
            if(hoverQueued!=0){Interlocked.Increment(ref hoverBusyUpdates);return;}
            hoverQueued=1;
        }
        // Provider calls for hover must never sit ahead of a mouse-down in the
        // action queue. Only one metadata preflight may be outstanding.
        ThreadPool.QueueUserWorkItem(_=>{
          while(true) {
            HoverProbe probe;
            lock(hoverGate){probe=pendingHover;pendingHover=null;if(probe==null){hoverQueued=0;return;}}
            int epoch=probe.Epoch;probe.Started=MonotonicMs();activeHover=probe;
            try {
                if(Broken||!Armed||epoch!=generation||dropdown!=null)continue;
                Native.CheckProcess(probe.Window);
                var anchor=ReadButton(probe.Point,probe.Window,epoch,MonotonicMs());
                probe.Found=anchor!=null;
                if(anchor!=null)anchor.At=MonotonicMs(); // Completed preflight must precede mouse-down.
                if(!Broken&&Armed&&epoch==generation)hoverClick=anchor;
            }catch(Exception ex){probe.Error=ex.GetType().Name;if(epoch==generation)hoverClick=null;} // Never read values for a hover.
            finally{probe.Completed=MonotonicMs();if(epoch==generation){lastHover=probe;activeHover=null;}}
          }
        });
    }
    void RefreshStationaryHover() {
        if(!Armed||Broken||dropdown!=null)return;
        var pointer=physicalPointer;var anchor=hoverClick;
        // Renew a known button only; do not scan arbitrary stationary content.
        if(pointer==null||anchor==null||pointer.Epoch!=generation||anchor.Epoch!=generation||
            pointer.Window!=anchor.Window||Mine(pointer.Window)||Native.Root(Native.GetForegroundWindow())!=pointer.Window||
            !anchor.ControlBounds.Contains(new System.Windows.Point(pointer.Point.X,pointer.Point.Y)))return;
        QueueHover(pointer.Point,pointer.Window,true);
    }
    internal static bool HasNonButtonOwner(ControlType type) {
        // These controls own their gesture. Scanning every button in the
        // browser after finding one can hit stale entries from the old tab,
        // and cannot turn a tab/field/toggle into an invocation.
        return type==ControlType.TabItem||type==ControlType.CheckBox||
            type==ControlType.RadioButton||type==ControlType.Edit||type==ControlType.ComboBox;
    }
    SemanticClick ReadButton(Native.Point point,IntPtr window,int epoch,long at) {
        if(Broken||!Armed||epoch!=generation)return null;
        Native.CheckProcess(window);
        var root=AutomationElement.FromHandle(window);
        uint pid;Native.GetWindowThreadProcessId(window,out pid);
        AutomationElement found=null;var location=new System.Windows.Point(point.X,point.Y);
        if(Thread.CurrentThread.Name=="recorder-capture")captureOperation="button point lookup";
        var hit=AutomationElement.FromPoint(location);
        for(int depth=0;hit!=null&&depth<8;depth++,hit=TreeWalker.ControlViewWalker.GetParent(hit)) {
            if(hit.Current.ProcessId!=pid||hit.Current.NativeWindowHandle==window.ToInt32())break;
            var hitType=hit.Current.ControlType;
            if(hitType==ControlType.Button){found=hit;break;}
            if(HasNonButtonOwner(hitType))return null;
            if(hitType==ControlType.Document)break;
        }
        if(found==null) {
          if(Thread.CurrentThread.Name=="recorder-capture")captureOperation="button bounded search";
          // One provider round trip for each bounded candidate set, without
          // reading text values or making four calls per unrelated button.
          var cache=new CacheRequest();cache.TreeScope=TreeScope.Element;
          cache.Add(AutomationElement.ProcessIdProperty);cache.Add(AutomationElement.IsOffscreenProperty);
          cache.Add(AutomationElement.BoundingRectangleProperty);cache.Add(AutomationElement.IsInvokePatternAvailableProperty);
          AutomationElementCollection buttons;
          using(cache.Activate())buttons=root.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Button));
          if(buttons.Count>256)throw new Exception("Clicked button search exceeded its bounded budget.");
          foreach(AutomationElement button in buttons) {
            if(Broken||!Armed||epoch!=generation)return null;
            try {
                if(button.Cached.ProcessId!=pid||button.Cached.IsOffscreen||!button.Cached.BoundingRectangle.Contains(location))continue;
            }catch(ElementNotAvailableException){continue;} // No identity was selected from this obsolete entry.
            if(!Equals(button.GetCachedPropertyValue(AutomationElement.IsInvokePatternAvailableProperty),true))continue;
            Privacy(button);
            if(found!=null)throw new Exception("More than one semantic button contains the click. Draft preserved.");
            found=button;
          }
        }
        if(found==null)return null;
        if(Broken||!Armed||epoch!=generation)return null;
        if(Thread.CurrentThread.Name=="recorder-capture")captureOperation="button classification";
        object invoke;
        if(!found.TryGetCurrentPattern(InvokePattern.Pattern,out invoke))return null;
        Privacy(found);
        var parent=TreeWalker.ControlViewWalker.GetParent(found);
        if(parent!=null&&parent.Current.ControlType==ControlType.Group) {
            var combos=parent.FindAll(TreeScope.Children,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.ComboBox));
            var peers=parent.FindAll(TreeScope.Children,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Button));
            if(combos.Count==1&&peers.Count==1)return null; // Classify the owning dropdown, not its disclosure button.
        }
        if(Thread.CurrentThread.Name=="recorder-capture")captureOperation="button target ancestry";
        var target=Target(found,window);
        if(!target.ContainsKey("postcondition")&&DialogResult.CaptureModal(found,window,pid)&&DialogResult.Target(target)!=null)
            target["postcondition"]=DialogResult.Contract;
        return new SemanticClick{Control=found,Window=window,Pid=pid,Dpi=Native.GetDpiForWindow(window),Epoch=epoch,At=at,
            Target=target,ControlBounds=found.Current.BoundingRectangle,WindowBounds=root.Current.BoundingRectangle,RuntimeId=RuntimeIdentity(found.GetRuntimeId())};
    }
    bool CompleteSemanticClick(Native.Point point,IntPtr window,int epoch) {
        var click=semanticClick;semanticClick=null;if(click==null)return false;
        uint pid;Native.GetWindowThreadProcessId(window,out pid);
        if(click.Window!=window||click.Pid!=pid||click.Epoch!=epoch||generation!=epoch||
            (!click.Target.ContainsKey("download")&&Native.Root(Native.GetForegroundWindow())!=window)||Native.GetDpiForWindow(window)!=click.Dpi||
            Native.Title(window)!=(string)click.Target["window_key"]||AutomationElement.FromHandle(window).Current.BoundingRectangle!=click.WindowBounds||
            !click.ControlBounds.Contains(new System.Windows.Point(point.X,point.Y))||MonotonicMs()-click.At>2000)
            throw new Exception("The clicked button's window, identity or gesture changed. Draft preserved.");
        if(LocalSaveResult.Supports(click.Target)) {
            LocalSaveResult.Wait(window,click.SaveBefore,()=>{if(Broken||!Armed||epoch!=generation)throw new OperationCanceledException();},
                ()=>Interlocked.Exchange(ref BusySince,Stopwatch.GetTimestamp()),30000);
            RecordInvocation(window,epoch,click.Target);
            send("diagnostic",new {kind="local_save_verified",fresh_receipt=true});return true;
        }
        if(ProductImageResult.Supports(click.Target)) {
            capturedImage.Clear();capturedTransfer.Clear();latestTransfer=-1;
            bool copied=ProductImageResult.Wait(click.ClipboardBefore,()=>{
                if(!BrowserIdentity.SamePage(BrowserIdentity.Current(window),(Dictionary<string,object>)click.Target["browser"]))
                    throw new Exception("Image copy product identity changed.");
                if(!DesktopPlayback.ScopeMatches(click.Control,window,click.Target)||click.Control.Current.AutomationId!="copyImage")
                    throw new Exception("Image copy scope changed.");
                return click.Control;
            },()=>{
                if(Broken||!Armed||generation!=epoch||Native.Root(Native.GetForegroundWindow())!=window)
                    throw new Exception("Image copy capture stopped or lost focus; inspect before retrying.");
            },()=>Interlocked.Exchange(ref BusySince,Stopwatch.GetTimestamp()),30000,capturedImage.Retain);
            if(!copied)throw new Exception("A fresh image copy was not verified. Copy was not repeated.");
            RecordInvocation(window,epoch,click.Target);
            send("diagnostic",new {kind="image_copy_verified",fresh_clipboard=true,stable_image=true});
            return true;
        }
        // Edge's HTML modal buttons do not reliably publish InvokedEvent for
        // physical clicks. This strategy has its own pre-click modal witness
        // and an observed, scoped result; absence of an event is not failure.
        bool modalDismissed=false;
        if(DialogResult.Supports(click.Target)) {
            var dialog=DialogResult.Target(click.Target);
            var root=AutomationElement.FromHandle(window);
            var matches=root.FindAll(TreeScope.Descendants,new AndCondition(
                new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Window),
                new PropertyCondition(AutomationElement.AutomationIdProperty,dialog["automation_id"]),
                new PropertyCondition(AutomationElement.NameProperty,dialog["name"])));
            int visible=0;
            foreach(AutomationElement item in matches)
                if(!item.Current.IsOffscreen&&DesktopPlayback.ScopeMatches(item,window,dialog))visible++;
            if(visible>1)throw new Exception("The containing modal is ambiguous. Draft preserved.");
            modalDismissed=visible==0;
            send("diagnostic",new {kind="modal_button_result",dialog_dismissed=modalDismissed,scope_verified=true});
            if(!modalDismissed)throw new Exception("The button's containing modal did not close. Its result is unsupported. Draft preserved.");
        }
        if(click.NeedsInvocation&&!modalDismissed&&!click.Target.ContainsKey("download")) {
            var wait=Stopwatch.StartNew();bool matched=false;
            do {
                foreach(var witness in invocations.ToArray())if(witness.Epoch==epoch&&witness.RuntimeId==click.RuntimeId&&witness.At>=click.At&&witness.At-click.At<=2000){matched=true;break;}
                if(matched||wait.ElapsedMilliseconds>=500||Broken)break;
                Thread.Sleep(10);
            }while(true);
            if(!matched){
                send("diagnostic",new {kind="button_invocation_missing",received=invocationReceived,rejected=invocationRejected,
                    cache_failures=invocationCacheFailures,cache_error=invocationCacheError,subscription_matches=invocationWindow==window,
                    cached_age_ms=MonotonicMs()-click.At,witnesses=invocations.ToArray().Select(witness=>new {
                        runtime_matches=witness.RuntimeId==click.RuntimeId,epoch_matches=witness.Epoch==epoch,relative_ms=witness.At-click.At}).ToArray()});
                throw new Exception("Windows did not identify the invoked button for this click. Draft preserved; no action guessed.");
            }
            send("diagnostic",new {kind="semantic_button_invocation_matched",runtime_identity_verified=true});
        }
        RecordInvocation(window,epoch,click.Target);
        return true;
    }
    void RecordInvocation(IntPtr window,int epoch,Dictionary<string,object> target) {
        var browser=BrowserDownload.CaptureWindowAnchor(target);
        if(browser!=null)send("diagnostic",new {kind="download_window_context",browser_anchor=true,
            owned_save_as=BrowserDownload.OwnedSaveDialog(Native.GetForegroundWindow(),window)});
        WindowAction(window,epoch,null,browser);
        Emit("invoke",target,null,epoch);
    }
    void AnchorReleasedDropdown(AutomationElement identified,Native.Point point,IntPtr window,int epoch) {
        InputWindow(window);uint pid;Native.GetWindowThreadProcessId(window,out pid);
        if(Broken||epoch!=generation||dropdown!=null)
            throw new Exception("Dropdown capture changed before its opening click was verified. Draft preserved.");
        var owner=DropdownSelection.AtPoint(window,pid,new System.Windows.Point(point.X,point.Y));
        if(owner==null||!Automation.Compare(owner,identified)||!DropdownSelection.Open(owner,pid))
            throw new Exception("The opened dropdown does not uniquely match the clicked control. Draft preserved.");
        // Reuse the same owner, selection, DPI and popup validation as a
        // pre-release capture. Subsequent input keeps its ordinary deadline.
        SnapshotDropdown(point,window,epoch);
        if(dropdown==null||!Automation.Compare(dropdown.Owner,identified)||!FinishDropdownClick())
            throw new Exception("The opened dropdown could not retain its owner. Draft preserved.");
        send("diagnostic",new {kind="dropdown_owner_after_release",physical_point_and_owner_verified=true});
    }
    void SnapshotDropdown(Native.Point point,IntPtr window,int epoch) {
        if(Broken)return;
        if(Native.IsTaskbar(window))return;
        Native.CheckProcess(window);
        var location=new System.Windows.Point(point.X,point.Y);
        if(dropdown!=null) {
            ValidateDropdown();
            if(!DropdownSelection.Open(dropdown.Owner,dropdown.Pid)&&dropdown.PopupBounds.Contains(location)) {
                // The option click can close a portal before this worker sees
                // it. Its verified owner and pre-click popup bounds remain;
                // use the owner's actual selection, never the page underneath.
                dropdown.Candidate=DropdownSelection.Selected(dropdown.Owner,dropdown.Pid);
                if(dropdown.Candidate.Length==0)throw new Exception("Closed dropdown did not expose a selected option. Draft preserved.");
                dropdown.Gesture=true;return;
            }
            var option=DropdownSelection.OptionAt(dropdown.Owner,dropdown.Pid,location);
            if(option!=null){dropdown.Candidate=Safe(option.Current.Name);dropdown.Gesture=true;return;}
            if(dropdown.Owner.Current.BoundingRectangle.Contains(location)){dropdown.Gesture=true;return;}
            PollDropdown(true);
        }
        uint pid;Native.GetWindowThreadProcessId(window,out pid);
        var owner=DropdownSelection.AtPoint(window,pid,location);
        if(owner==null)return;
        InputWindow(window);
        var target=Target(owner,window);
        dropdown=new DropdownCapture{Owner=owner,Target=target,Window=window,Pid=pid,Epoch=epoch,
            Dpi=Native.GetDpiForWindow(window),WindowBounds=AutomationElement.FromHandle(window).Current.BoundingRectangle,
            Before=DropdownSelection.Selected(owner,pid),Gesture=true};
        send("diagnostic",new {kind="dropdown_owner_anchored",control_type=target["control_type"],
            generated_id_omitted=(string)target["automation_id"]=="",controller_for_available=DropdownSelection.Lists(owner,pid).Count>0});
    }
    bool FinishDropdownClick() {
        if(dropdown==null||!dropdown.Gesture)return false;
        dropdown.Gesture=false;
        var wait=Stopwatch.StartNew();
        do {
            ValidateDropdown();
            if(DropdownSelection.Open(dropdown.Owner,dropdown.Pid)){
                var lists=DropdownSelection.Lists(dropdown.Owner,dropdown.Pid);
                if(lists.Count>1)throw new Exception("Dropdown popup ownership is ambiguous.");
                dropdown.PopupBounds=DropdownSelection.PopupBounds(dropdown.Owner,dropdown.Pid);
                dropdown.View=DropdownSelection.View(dropdown.Owner,dropdown.Pid);dropdown.ScrollY=DropdownSelection.ScrollPosition(dropdown.Owner,dropdown.Pid);return true;
            }
            if(dropdown.Candidate!=null||DropdownSelection.Selected(dropdown.Owner,dropdown.Pid)!=dropdown.Before){PollDropdown(true);return true;}
            if(wait.ElapsedMilliseconds>=250)break;
            Thread.Sleep(15);
        }while(!Broken);
        return true; // The identified control may publish its owned popup late.
    }
    bool DropdownKey(IntPtr window,bool shortcut) {
        if(dropdown==null)return false;
        ValidateDropdown();
        if(window!=dropdown.Window||shortcut)throw new Exception("Unsupported input while choosing a dropdown option. Draft preserved.");
        PollDropdown(false);return true;
    }
    void PollDropdown(bool final,bool transition=false) {
        if(dropdown==null||dropdown.Gesture)return;
        ValidateDropdown(!transition);
        if(DropdownSelection.Open(dropdown.Owner,dropdown.Pid)) {
            if(final)throw new Exception("Finish or cancel the open dropdown before continuing or saving. Draft preserved.");
            return;
        }
        string selected;
        try{selected=DropdownSelection.Selected(dropdown.Owner,dropdown.Pid);}
        catch(ElementNotAvailableException){RebindDropdown();selected=DropdownSelection.Selected(dropdown.Owner,dropdown.Pid);}
        if(dropdown.Candidate!=null&&selected!=dropdown.Candidate)
            throw new Exception("Dropdown did not expose the chosen option against its owning control. Draft preserved.");
        if(dropdown.Candidate!=null||selected!=dropdown.Before) {
            if(selected.Length==0)throw new Exception("Dropdown selection has no verifiable identity.");
            WindowAction(dropdown.Window,dropdown.Epoch);
            Emit("select",dropdown.Target,selected,dropdown.Epoch);
            send("diagnostic",new {kind="dropdown_selection_committed",owning_control=true,selected_value_verified=true});
        }else send("diagnostic",new {kind="dropdown_cancelled",selected_value_unchanged=true});
        dropdown=null;
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
            RawChildren,256,16,"Clicked control",500,node=>TransparentLayout(node,expectedPid));
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
        // BaseWeb's editable input can be much narrower than its selection
        // surface. The adapter explicitly projects that owning group; reuse
        // its same-process, unique-combobox and physical-point validation.
        // A nearby arbitrary parent or matching text is never sufficient.
        if(stateful&&control.Current.ControlType==ControlType.ComboBox&&
           EdgeDropdownAdapter.Contains(control,expectedPid,new System.Windows.Point(point.X,point.Y))) {
            Target(control,h);
            send("diagnostic",new {kind="focused_dropdown_owner_click",control_name=Safe(control.Current.Name),
                resolution="physical click inside adapter-identified unique dropdown owner; ancestry validated"});
            return control;
        }
        if((stateful||button)&&
           EditorClickTarget.Matches(new System.Windows.Point(point.X,point.Y),control.Current.BoundingRectangle,System.Windows.Rect.Empty,false)) {
            send("diagnostic",new {kind="focused_semantic_candidate",control_type=control.Current.ControlType.ProgrammaticName,automation_id=Safe(control.Current.AutomationId),control_name=Safe(control.Current.Name),runtime_id=RuntimeIdentity(control.GetRuntimeId())});
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
        promptPasteAnchor=null;
        Privacy(editor,true);
        if(editor.Current.AutomationId=="RootWebArea")
            throw new Exception("The browser page itself is not a supported text field. Draft preserved; no page contents were read.");
        editorAnchorTarget=Target(editor,h);
        editorAnchor=editor;
        imageDestinationEmpty=capturedImage.Present&&ChatImageAttachment.Supports(editorAnchorTarget)&&ChatImageAttachment.Inspect(editor,true)&&ChatImageAttachment.EmptyText(editor);
        if(!capturedImage.Present&&latestTransfer>=0&&!dirty&&ChatImageAttachment.Supports(editorAnchorTarget)&&
           ChatImageAttachment.EmptyText(editor))
            promptPasteAnchor=new PromptPasteAnchor{Window=h,Epoch=generation,Editor=editor};
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
    void CopyIntent(IntPtr h,int epoch) {
        if(Broken)return;
        InputWindow(h);ResolvePendingEditorClick();
        var editor=AutomationElement.FocusedElement;
        uint pid;Native.GetWindowThreadProcessId(h,out pid);
        if(editor==null||editor.Current.ProcessId!=pid||!editor.Current.HasKeyboardFocus||
            Native.Root(Native.GetForegroundWindow())!=h)
            throw new Exception("Copy focus changed. Draft preserved.");
        var target=Target(editor,h);
        if(editorAnchor==null||!Automation.Compare(editorAnchor,editor))
            throw new Exception("Click the copy source editor before copying. Draft preserved.");
        capturedTransfer.Clear();capturedImage.Clear();latestTransfer=-1;
        string observed=RunTransfer.ReadEditor(editor,true,RunTransfer.NativeDocument(target));
        latestTransfer=transferSerial++;capturedTransfer.ObserveEditor(latestTransfer,observed);
        var value=new Dictionary<string,object>{{"slot",latestTransfer},{"mode","whole_text"}};
        // The source was focused when observation began. Observe verifies its
        // unchanged contents and exact clipboard result; a subsequent app
        // switch does not invalidate that already identified copy operation.
        WindowAction(h,epoch);Emit("transfer_copy",target,value,epoch);
    }
    public void RecordLocalUploads() {
        if(!Armed||Broken||Interlocked.Read(ref BusySince)!=0||queue.Count!=0)throw new Exception("Start capture and wait until ready.");
        int epoch=generation;Put(()=>{
            var value=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(LocalUploads.Input));LocalUploads.Validate(value);
            IntPtr window=IntPtr.Zero;
            Native.EnumWindows((h,l)=>{Interlocked.Exchange(ref BusySince,Stopwatch.GetTimestamp());if(Native.IsWindowVisible(h)&&LocalUploads.Matches(h)){if(window!=IntPtr.Zero)throw new Exception("More than one visible local upload page.");window=h;}return true;},IntPtr.Zero);
            if(window==IntPtr.Zero||!Native.SetForegroundWindow(window))throw new Exception("Prepare one visible isolated upload window.");
            Action check=()=>{if(Broken||!Armed||generation!=epoch||!LocalUploads.Focus(window))throw new Exception("Upload capture stopped or focus changed.");};
            var target=Target(AutomationElement.FromHandle(window),window);target["automation_id"]="window";
            WindowAction(window,epoch);Emit("local_upload",target,value,epoch);
            string receipt=LocalUploads.Run(window,value,check,()=>Interlocked.Exchange(ref BusySince,Stopwatch.GetTimestamp()));
            send("diagnostic",new {kind="local_upload_verified",receipt=receipt});
        });
    }
    public void ObserveSubmission(string requestId,string page,bool waitOutputs=false,bool downloadOutputs=false) {
        if(Armed!=waitOutputs||Interlocked.Read(ref BusySince)!=0||queue.Count!=0)throw new Exception(waitOutputs?"Start capture and wait until ready before recording an output wait.":"Stop capture before inspecting an existing submission.");
        Guid id;if(!Guid.TryParseExact(requestId,"D",out id)||!ChatSubmission.Conversation(page))throw new Exception("Enter the exact attempt ID and conversation URL.");
        Broken=false;int epoch=generation;
        Put(()=>{
            captureOperation="observe existing submission";
            string receipt=Path.Combine(ChatSubmission.ReceiptDirectory,id.ToString("D")+".json");
            var data=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(receipt));
            var request=(Dictionary<string,object>)data["request"];string profile=(string)data["profile"];
            if(!Equals(request["request_id"],requestId))throw new Exception("Attempt receipt identity does not match.");
            IntPtr window=IntPtr.Zero;
            Native.EnumWindows((h,l)=>{
                Interlocked.Exchange(ref BusySince,Stopwatch.GetTimestamp());
                if(!Native.IsWindowVisible(h)||!BrowserTabs.Chromium(h))return true;
                var identity=BrowserIdentity.Current(h);
                if(identity==null||!Equals(identity["page"],page)||!Equals(identity["profile"],profile))return true;
                if(window!=IntPtr.Zero)throw new Exception("Conversation window is ambiguous.");window=h;return true;
            },IntPtr.Zero);
            if(window==IntPtr.Zero||!Native.SetForegroundWindow(window))throw new Exception("The exact attempted conversation is unavailable.");
            Action check=()=>{if(Broken||waitOutputs&&(!Armed||generation!=epoch)||Native.Root(Native.GetForegroundWindow())!=window)throw new Exception("Acknowledgement inspection stopped.");
                if(!waitOutputs){var current=BrowserIdentity.Current(window);if(current==null||!Equals(current["page"],page)||!Equals(current["profile"],profile))throw new Exception("Conversation identity changed.");}};
            if(waitOutputs) {
                var value=new Dictionary<string,object>{{"request_id",requestId},{"conversation",page}};
                var target=Target(AutomationElement.FromHandle(window),window);
                target["automation_id"]="window";
                if(downloadOutputs) { value=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(ChatSubmission.ReceiptDirectory,requestId+".gallery.json"))); if(!Equals(value["request_id"],requestId)||!Equals(value["conversation"],page))throw new Exception("Gallery binding is for another request."); ChatDownloads.Validate(value); WindowAction(window,epoch); Emit("chat_download",target,value,epoch); var files=ChatDownloads.Run(window,value,check,()=>Interlocked.Exchange(ref BusySince,Stopwatch.GetTimestamp())); send("diagnostic",new {kind="chat_downloads_verified",receipt=files}); return; } WindowAction(window,epoch);Emit("chat_wait",target,value,epoch);
                var outputs=ChatOutputs.Wait(window,value,check,()=>Interlocked.Exchange(ref BusySince,Stopwatch.GetTimestamp()),900000);
                send("diagnostic",new {kind="chat_outputs_ready",receipt=outputs});return;
            }
            var result=ChatSubmission.Observe(window,request,profile,receipt,check,()=>Interlocked.Exchange(ref BusySince,Stopwatch.GetTimestamp()),30000);
            send("diagnostic",new {kind="chat_submission_acknowledged",receipt=result,recovered_without_input=true});
        });
    }
    public void SubmitPreparedRequest() {
        if(!Armed||Broken||Interlocked.Read(ref BusySince)!=0||queue.Count!=0)throw new Exception("Wait until capture is ready before submitting.");
        int epoch=generation;
        Put(()=>{
            captureOperation="submit prepared request";IntPtr window=IntPtr.Zero;
            foreach(var candidate in preparedWindows.Keys) {
                Interlocked.Exchange(ref BusySince,Stopwatch.GetTimestamp());
                if(!Native.IsWindow(candidate)||!WindowIdentity.ChromiumApp(Native.ProcessFor(candidate).MainModule.FileName))continue;
                var identity=BrowserIdentity.Current(candidate);
                if(identity==null||!Equals(identity["page"],ChatImageAttachment.Page))continue;
                if(window!=IntPtr.Zero)throw new Exception("More than one prepared project window. Nothing sent.");window=candidate;
            }
            if(window==IntPtr.Zero)throw new Exception("The prepared project window is unavailable. Nothing sent.");
            if(!Native.SetForegroundWindow(window))throw new Exception("Could not activate the prepared project. Nothing sent.");
            Action check=()=>{if(Broken||!Armed||epoch!=generation||Native.Root(Native.GetForegroundWindow())!=window)
                throw new Exception("Submission stopped or window changed. Check the receipt before any new request.");Interlocked.Exchange(ref BusySince,Stopwatch.GetTimestamp());};
            check();var root=AutomationElement.FromHandle(window);
            var buttons=root.FindAll(TreeScope.Descendants,new AndCondition(new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Button),new PropertyCondition(AutomationElement.NameProperty,"Send")));
            AutomationElement button=null;Dictionary<string,object> target=null;
            foreach(AutomationElement item in buttons)if(!item.Current.IsOffscreen) {
                var identified=Target(item,window);if(!ChatSubmission.Supports(identified))continue;
                if(button!=null)throw new Exception("Send is ambiguous. Nothing sent.");button=item;target=identified;
            }
            if(button==null)throw new Exception("The exact project Send control is unavailable.");
            check();string text=ChatSubmission.Preflight(window,button,target);
            var request=new Dictionary<string,object>{{"request_id",Guid.NewGuid().ToString("D")},{"sha256",ChatSubmission.Digest(text)},{"characters",text.Length}};
            var result=ChatSubmission.Execute(window,button,target,request,check,()=>Interlocked.Exchange(ref BusySince,Stopwatch.GetTimestamp()),
                ()=>{WindowAction(window,epoch);Emit("chat_submit",target,request,epoch);},30000);
            send("diagnostic",new {kind="chat_submission_acknowledged",receipt=result});
        });
    }
    void ControlledPromptPaste(PromptPasteAnchor lease) {
        captureOperation="controlled prompt paste";
        Action check=()=>{
            if(Broken||!Armed||generation!=lease.Epoch||Native.Root(Native.GetForegroundWindow())!=lease.Window||
               !lease.Editor.Current.HasKeyboardFocus||!Automation.Compare(lease.Editor,AutomationElement.FocusedElement)||
               !Automation.Compare(lease.Editor,editorAnchor))throw new Exception("Prompt paste destination changed. No retry was made.");
            Interlocked.Exchange(ref BusySince,Stopwatch.GetTimestamp());
        };
        check();InputWindow(lease.Window);
        var target=Target(lease.Editor,lease.Window);
        if(dirty||capturedImage.Present||!ChatImageAttachment.Supports(target)||!ChatImageAttachment.EmptyText(lease.Editor)||
           !ChatImageAttachment.Inspect(lease.Editor,false))
            throw new Exception("Controlled prompt Paste requires an empty supported composer with one completed image.");
        string expected=capturedTransfer.Get(latestTransfer);object pattern;
        if(!lease.Editor.TryGetCurrentPattern(ValuePattern.Pattern,out pattern)||((ValuePattern)pattern).Current.IsReadOnly)
            throw new Exception("Prompt destination does not support verified whole-field replacement.");
        check();((ValuePattern)pattern).SetValue(expected);
        var timer=Stopwatch.StartNew();bool verified=false;
        while(timer.ElapsedMilliseconds<10000) {
            check();
            if(RunTransfer.SameEditorText(RunTransfer.ReadEditor(lease.Editor,false,false,true),expected)){verified=true;break;}
            Thread.Sleep(100);
        }
        if(!verified)throw new Exception("Complete prompt text was not confirmed. Paste was not repeated.");
        check();capturedTransfer.Get(latestTransfer);
        WindowAction(lease.Window,lease.Epoch);
        Emit("transfer_paste",target,new Dictionary<string,object>{{"slot",latestTransfer},{"mode","replace_all"}},lease.Epoch);
        pastedEditor=lease.Editor;
        send("diagnostic",new {kind="controlled_prompt_paste_verified",characters=expected.Length});
    }
    void PasteIntent(IntPtr h,int epoch) {
        if(Broken)return;
        InputWindow(h);ResolvePendingEditorClick();
        var editor=AutomationElement.FocusedElement;uint pid;Native.GetWindowThreadProcessId(h,out pid);
        if(editor==null||editor.Current.ProcessId!=pid||!editor.Current.HasKeyboardFocus||editorAnchor==null||
            !Automation.Compare(editorAnchor,editor))throw new Exception("Paste destination changed. Draft preserved.");
        var target=Target(editor,h);
        if(capturedImage.Present) {
            if(!imageDestinationEmpty||!ChatImageAttachment.Supports(target)||!ChatImageAttachment.EmptyText(editor)||dirty)
                throw new Exception("Image Paste requires the previously identified empty project composer.");
            imageDestinationEmpty=false;
            if(!ChatImageAttachment.Wait(editor,capturedImage,()=>{
                if(Broken||!Armed||generation!=epoch||Native.Root(Native.GetForegroundWindow())!=h||
                   !BrowserIdentity.SamePage(BrowserIdentity.Current(h),(Dictionary<string,object>)target["browser"]))
                    throw new Exception("Image paste destination changed or capture stopped.");
            },()=>Interlocked.Exchange(ref BusySince,Stopwatch.GetTimestamp()),30000))
                throw new Exception("Image attachment did not finish. Paste was not repeated.");
            capturedImage.Clear();WindowAction(h,epoch);Emit("image_paste",target,null,epoch);return;
        }
        string expected=capturedTransfer.Get(latestTransfer);
        string pasteObserved=RunTransfer.ReadEditor(editor,false,RunTransfer.NativeDocument(target));
        if(!RunTransfer.SameEditorText(pasteObserved,expected))
            throw new Exception("Automatic Paste requires an empty or fully selected destination field. Mixed edits are not guessed.");
        // A pending typed value was replaced by this explicit whole-field Paste.
        if(dirty)throw new Exception("Finish pending typing before a transfer Paste. Draft preserved.");
        WindowAction(h,epoch);Emit("transfer_paste",target,new Dictionary<string,object>{{"slot",latestTransfer},{"mode","replace_all"}},epoch);
        pastedEditor=editor;
    }
    void TextIntent(IntPtr h,int epoch) {
        if(Broken)return;
        InputWindow(h);
        ResolvePendingEditorClick();
        var e=AutomationElement.FocusedElement;
        if(pastedEditor!=null&&Automation.Compare(pastedEditor,e))
            throw new Exception("Editing transferred text in the same field is not yet supported. Stop preserves the dynamic Paste.");
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
        if(!Broken)PollDropdown(false);
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
        // Read-only provider evidence: no field names or values, and no input.
        // Inspect the whole window so a failed point hit can be compared with
        // containers omitted from that hit's raw ancestry.
        var scrollNodes=e.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.IsScrollPatternAvailableProperty,true));
        var scrollRows=new List<object>();
        for(int i=0;i<Math.Min(16,scrollNodes.Count);i++) {
            var node=scrollNodes[i];object pattern;
            if(!node.TryGetCurrentPattern(ScrollPattern.Pattern,out pattern))continue;
            var position=((ScrollPattern)pattern).Current;
            var ancestry=new List<object>();
            for(var parent=TreeWalker.RawViewWalker.GetParent(node);parent!=null&&ancestry.Count<16;parent=TreeWalker.RawViewWalker.GetParent(parent)) {
                ancestry.Add(ScrollMetadata(parent));
                if(parent.Current.NativeWindowHandle==h.ToInt32())break;
            }
            scrollRows.Add(new {element=ScrollMetadata(node),position=RecordedScroll(position),
                horizontal_scrollable=position.HorizontallyScrollable,vertical_scrollable=position.VerticallyScrollable,ancestry=ancestry});
        }
        send("diagnostic",new {kind="scroll_provider_inspection",candidate_count=scrollNodes.Count,truncated=scrollNodes.Count>16,containers=scrollRows});
        send("diagnostic",new {kind="dropdown_provider_inspection",controls=DropdownSelection.Inspect(h)});
    });}
    static object ScrollMetadata(AutomationElement e) {
        var current=e.Current;var bounds=current.BoundingRectangle;
        return new {control_type=current.ControlType.ProgrammaticName,automation_id=Safe(current.AutomationId),
            name_empty=current.Name.Length==0,is_control=current.IsControlElement,offscreen=current.IsOffscreen,
            bounds=bounds.IsEmpty?null:new double[]{bounds.X,bounds.Y,bounds.Width,bounds.Height}};
    }
}

class Host : Window {
    static readonly JavaScriptSerializer json=new JavaScriptSerializer(){MaxJsonLength=65536};
    readonly BlockingCollection<string> outbound=new BlockingCollection<string>(128);
    readonly ComboBox windows=new ComboBox(){Margin=new Thickness(0,4,0,6),MinHeight=30};
    readonly CheckBox desktopSession=new CheckBox(){Content="Desktop session · supported apps",IsChecked=true,Margin=new Thickness(0,4,0,6)};
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
    readonly StackPanel recoveryPanel=new StackPanel(){Margin=new Thickness(0,8,0,0)};
    readonly ComboBox reviewRuns=new ComboBox(){MinHeight=30};
    readonly TextBlock reviewSummary=new TextBlock(){TextWrapping=TextWrapping.Wrap,Margin=new Thickness(0,6,0,6)};
    readonly TextBox reviewEvidence=new TextBox(){MaxLength=500,MinHeight=52,AcceptsReturn=true,TextWrapping=TextWrapping.Wrap};
    readonly CheckBox reviewChecked=new CheckBox(){Content="I checked the result and prepared the app",Margin=new Thickness(0,6,0,6)};
    Button reviewButton;string reviewIdentity;
    readonly TextBlock actionLog=new TextBlock(){TextWrapping=TextWrapping.Wrap,Margin=new Thickness(0,6,0,6)};
    string liveActionLog="";
    readonly StackPanel detailTools=new StackPanel(){Orientation=Orientation.Horizontal};
    Capture capture;IntPtr hwnd;string state="idle";string playbackProgress;int generation;long elapsed;Stopwatch segment=new Stopwatch();
    bool closeAllowed;bool pending;bool testInput;
    readonly RecordingIndicator indicator=new RecordingIndicator();
    long pendingSince;int libraryOffset,reviewOffset;int? libraryNext,reviewNext;
    readonly TextBlock buildLabel=new TextBlock(){Text="local-phase5-20261022 / IPC 2",FontSize=10,Foreground=Brushes.DimGray};
    volatile string pendingId;
    DesktopPlayback playback;
    int instructionSerial;
    bool playbackPaused;
    bool awaitingPlayback;
    bool connected=true,stopRequested;
    string pendingKind="";
    string lastSavedId;
    string lastSelectedRunId;
    string lastPresentedTaskId;
    public Host(bool testInput) {
        this.testInput=testInput;
        Title="Sports Cave · Task Recorder";Width=390;SizeToContent=SizeToContent.Height;Topmost=true;
        MaxHeight=SystemParameters.WorkArea.Height-30;FontFamily=new FontFamily("Segoe UI");FontSize=12;
        ResizeMode=ResizeMode.CanMinimize;WindowStartupLocation=WindowStartupLocation.Manual;
        Left=Math.Max(SystemParameters.WorkArea.Left,SystemParameters.WorkArea.Right-Width-20);Top=SystemParameters.WorkArea.Top+70;
        Background=new SolidColorBrush(Color.FromRgb(255,253,248));Foreground=new SolidColorBrush(Color.FromRgb(36,39,32));
        var layout=new StackPanel(){Margin=new Thickness(14)};Content=new ScrollViewer(){Content=layout,VerticalScrollBarVisibility=ScrollBarVisibility.Auto};layout.Children.Add(buildLabel);
        var title=new TextBlock(){Text="SPORTS CAVE  /  TASK RECORDER",FontSize=10,Foreground=Brushes.DimGray};
        title.MouseLeftButtonDown+=(s,e)=>DragMove();layout.Children.Add(title);
        layout.Children.Add(heading);layout.Children.Add(contextName);
        windowPanel.Children.Add(desktopSession);
        windowPanel.Children.Add(new TextBlock(){Text="Starting window (optional for desktop session)",Foreground=Brushes.DimGray});windowPanel.Children.Add(windows);layout.Children.Add(windowPanel);
        layout.Children.Add(controls);layout.Children.Add(timer);layout.Children.Add(status);
        recoveryPanel.Children.Add(new TextBlock(){Text="Review an interrupted replay",FontWeight=FontWeights.SemiBold});
        recoveryPanel.Children.Add(reviewRuns);recoveryPanel.Children.Add(reviewSummary);
        recoveryPanel.Children.Add(new TextBlock(){Text="What happened in the application?",Margin=new Thickness(0,4,0,4)});
        recoveryPanel.Children.Add(reviewEvidence);recoveryPanel.Children.Add(reviewChecked);
        reviewButton=Button("Save review · keep run stopped",()=>{
            var item=reviewRuns.SelectedItem as ComboBoxItem;
            if(item==null||reviewChecked.IsChecked!=true||String.IsNullOrWhiteSpace(reviewEvidence.Text))return;
            var reviewedRun=(Dictionary<string,object>)item.Tag;
            Command("reconcile",new {run_id=reviewedRun["id"],revision=reviewedRun["revision"],step=reviewedRun["step"],evidence=reviewEvidence.Text.Trim(),reviewed=true});
        });
        recoveryPanel.Children.Add(reviewButton);
        recoveryPanel.Children.Add(new TextBlock(){Text="This keeps the failed run in history. Nothing resumes or repeats. A new Play starts from the beginning.",TextWrapping=TextWrapping.Wrap});
        reviewRuns.SelectionChanged+=(s,e)=>UpdateReview();
        reviewEvidence.TextChanged+=(s,e)=>UpdateReviewEnabled();
        reviewChecked.Checked+=(s,e)=>UpdateReviewEnabled();reviewChecked.Unchecked+=(s,e)=>UpdateReviewEnabled();
        savePanel.Children.Add(new TextBlock(){Text="Recording name"});
        savePanel.Children.Add(name);var row=new StackPanel(){Orientation=Orientation.Horizontal};
        saveButton=Button("Save recording",()=>Command("save",new {name=name.Text.Trim()}));
        discardButton=Button("Discard draft",()=>{if(MessageBox.Show(this,"Discard this unsaved recording?","Discard recording",MessageBoxButton.YesNo,MessageBoxImage.Question)==MessageBoxResult.Yes)Command("discard",new {});});
        row.Children.Add(saveButton);row.Children.Add(discardButton);savePanel.Children.Add(row);layout.Children.Add(savePanel);
        var details=new StackPanel();details.Children.Add(recoveryPanel);details.Children.Add(new TextBlock(){Text="Saved recording",Margin=new Thickness(0,6,0,0)});details.Children.Add(tasks);
        var pages=new StackPanel(){Orientation=Orientation.Horizontal};
        pages.Children.Add(Button("Previous recordings",()=>Command("library_page",new {offset=Math.Max(0,libraryOffset-20)})));
        pages.Children.Add(Button("Next recordings",()=>{if(libraryNext.HasValue)Command("library_page",new {offset=libraryNext.Value});}));details.Children.Add(pages);
        details.Children.Add(Button("Previous reviews",()=>Command("review_page",new {offset=Math.Max(0,reviewOffset-20)})));
        details.Children.Add(Button("Next reviews",()=>{if(reviewNext.HasValue)Command("review_page",new {offset=reviewNext.Value});}));
        details.Children.Add(new TextBlock(){Text="Action log",FontWeight=FontWeights.SemiBold});details.Children.Add(actionLog);
        detailTools.Children.Add(Button("Refresh windows",RefreshWindows));
        detailTools.Children.Add(Button("Inspect window",()=>{if(windows.SelectedItem!=null)capture.Diagnostic((IntPtr)((ComboBoxItem)windows.SelectedItem).Tag);}));
        details.Children.Add(detailTools);details.Children.Add(new TextBlock(){Text="Ctrl+Alt+F12 stops playback immediately.",TextWrapping=TextWrapping.Wrap,Margin=new Thickness(0,5,0,0)});
        var attemptId=new TextBox(){MaxLength=36};var conversationUrl=new TextBox(){MaxLength=500};
        details.Children.Add(new TextBlock(){Text="Inspect an existing submission (never sends)"});
        System.Windows.Automation.AutomationProperties.SetName(attemptId,"Submission attempt ID");
        System.Windows.Automation.AutomationProperties.SetName(conversationUrl,"Submitted conversation URL");
        details.Children.Add(attemptId);details.Children.Add(conversationUrl);
        details.Children.Add(Button("Record local uploads",()=>capture.RecordLocalUploads()));
        details.Children.Add(Button("Check acknowledgement",()=>capture.ObserveSubmission(attemptId.Text.Trim(),conversationUrl.Text.Trim())));
        details.Children.Add(Button("Record output wait",()=>capture.ObserveSubmission(attemptId.Text.Trim(),conversationUrl.Text.Trim(),true))); details.Children.Add(Button("Record retained downloads",()=>capture.ObserveSubmission(attemptId.Text.Trim(),conversationUrl.Text.Trim(),true,true)));
        details.Children.Add(new TextBlock(){Text="Desktop session follows supported applications. Unsupported controls interrupt capture and preserve the draft. Prepare the recorded windows before replay.",TextWrapping=TextWrapping.Wrap,Margin=new Thickness(0,5,0,0)});
        advanced.Content=details;layout.Children.Add(advanced);
        windows.SelectionChanged+=(s,e)=>Render();tasks.DropDownClosed+=(s,e)=>{
            if(state=="idle"&&tasks.SelectedItem!=null&&!pending){
                var selectedTask=(Dictionary<string,object>)((ComboBoxItem)tasks.SelectedItem).Tag;
                if(!selectedTask.ContainsKey("action_log"))Command("inspect_task",new {id=selectedTask["id"],revision=selectedTask["revision"]});
            }
            Render();
        };
        desktopSession.Checked+=(s,e)=>Render();desktopSession.Unchecked+=(s,e)=>Render();
        SourceInitialized+=(s,e)=>{
            hwnd=new WindowInteropHelper(this).Handle;
            playback=new DesktopPlayback(hwnd,Send);
            HwndSource.FromHwnd(hwnd).AddHook((IntPtr h,int msg,IntPtr w,IntPtr l,ref bool handled)=>{
                if(msg==0x312&&w.ToInt32()==DesktopPlayback.Hotkey){playback.Stop();Send("diagnostic",new {kind="emergency_stop",source="registered_windows_hotkey"});Send("play_stop",new {reason="Emergency Stop requested."});handled=true;}return IntPtr.Zero;
            });
            EdgeDropdownAdapter.Observed=()=>Send("diagnostic",new {kind="adapter_seen",protocol=1});
            capture=new Capture(hwnd,Send,reason=>Dispatcher.BeginInvoke(new Action(()=>{capture.Detach();Send("interrupt",new {reason});status.Text=reason;})),testInput);
            RefreshWindows();Render();Send("diagnostic",new {kind="toolbar_ready",protocol=2,build="local-phase5-20261022"});
        };
        Closed+=(s,e)=>indicator.Dispose();
        Closing+=(s,e)=>{
            if(state=="playing"){playback.Disarm();Send("play_stop",new {reason="Toolbar closed. Pending effects remain uncertain."});closeAllowed=true;}
            if(!closeAllowed&&state!="idle"){e.Cancel=true;status.Text="Stop, then Save or Discard before closing.";if(state=="recording"||state=="paused")Stop();}
            else {if(capture!=null)capture.Detach();if(playback!=null)playback.Disarm();Send("close",new {});}
        };
        var tick=new DispatcherTimer(){Interval=TimeSpan.FromMilliseconds(250)};
        tick.Tick+=(s,e)=>{UpdateIndicator();if(pending){if(pendingSince==0)pendingSince=Stopwatch.GetTimestamp();else if((Stopwatch.GetTimestamp()-pendingSince)/(double)Stopwatch.Frequency>8){if(capture!=null)capture.Detach();if(playback!=null)playback.Disarm();connected=false;pending=false;status.Text="Helper acknowledgement timed out. Actions stopped; review preserved state. Reopen the popup.";Render();Environment.Exit(79);}}else pendingSince=0;string display=playbackProgress??((state=="recording"?"● Recording  ":state=="paused"?"Paused  ":"")+TimeSpan.FromMilliseconds(elapsed+segment.ElapsedMilliseconds).ToString(@"hh\:mm\:ss"));if(timer.Text!=display)timer.Text=display;if(capture!=null)capture.Watchdog();if(playback!=null)playback.Watchdog();};tick.Start();
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
    Button Button(string text,Action action){var b=new Button(){Content=text,Padding=new Thickness(12,6,12,6),Margin=new Thickness(0,0,6,0),MinWidth=64,Background=Brushes.White,BorderBrush=new SolidColorBrush(Color.FromRgb(211,207,195))};System.Windows.Automation.AutomationProperties.SetName(b,text);b.Click+=(s,e)=>{try{action();}catch(Exception ex){status.Text=ex.Message;pending=false;pendingKind="";Render();}};return b;}
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
        uint ownProcess=(uint)Process.GetCurrentProcess().Id;
        Native.EnumWindows((h,l)=>{uint pid;Native.GetWindowThreadProcessId(h,out pid);if(h!=hwnd&&Native.IsWindowVisible(h)&&pid!=ownProcess){string title=Native.Title(h);if(title.Length>0){try{Native.CheckProcess(h);windows.Items.Add(new ComboBoxItem(){Content=title,Tag=h});}catch{}}}return true;},IntPtr.Zero);
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
    string indicatorMode="";
    void UpdateIndicator(){
        string label=RecordingIndicator.Mode(state,awaitingPlayback,playbackPaused,connected,stopRequested);
        if(capture!=null&&capture.Broken&&state=="recording")label="";
        indicator.Update(label,state=="playing"?(playbackProgress??"Preparing") : TimeSpan.FromMilliseconds(elapsed+segment.ElapsedMilliseconds).ToString(@"hh\:mm\:ss"));
        if(label!=indicatorMode){indicatorMode=label;Send("diagnostic",new {kind="recording_indicator",mode=label,displays=indicator.Snapshot()});}
    }
    void Render(){
        UpdateIndicator();
        // Interrupted recordings require explicit review before Save is accepted.
        heading.Text=ToolbarPresentation.Label(state,awaitingPlayback,playbackPaused,pendingKind,connected);
        if(state=="recording"&&capture!=null&&capture.DesktopSession)heading.Text="● Recording desktop session";
        Title=state=="recording"?"● Recording · Sports Cave Task Recorder":"Sports Cave · Task Recorder";
        if(state=="idle"&&tasks.SelectedItem!=null)contextName.Text="Selected recording: "+((Dictionary<string,object>)((ComboBoxItem)tasks.SelectedItem).Tag)["name"];
        controls.Children.Clear();savePanel.Visibility=state=="draft"?Visibility.Visible:Visibility.Collapsed;
        windowPanel.Visibility=state=="idle"?Visibility.Visible:Visibility.Collapsed;
        windows.IsEnabled=ToolbarPresentation.CanStart(state,pending||stopRequested,connected);
        desktopSession.IsEnabled=windows.IsEnabled;
        detailTools.IsEnabled=state=="idle"&&!pending&&!stopRequested&&connected;
        // The action log remains readable while capture/playback is running.
        advanced.IsEnabled=connected;
        tasks.IsEnabled=state=="idle"&&!pending&&!stopRequested&&connected;
        actionLog.Text=liveActionLog;
        if(state=="idle"&&tasks.SelectedItem!=null){
            var logTask=(Dictionary<string,object>)((ComboBoxItem)tasks.SelectedItem).Tag;
            actionLog.Text=logTask.ContainsKey("action_log")?FormatLog((System.Collections.ArrayList)logTask["action_log"]):"Loading selected recording…";
        }
        if(actionLog.Text.Length==0)actionLog.Text="No actions captured yet.";
        recoveryPanel.IsEnabled=state=="idle"&&!pending&&!stopRequested&&connected;
        saveButton.IsEnabled=discardButton.IsEnabled=name.IsEnabled=connected&&!pending&&!stopRequested;
        contextName.Visibility=contextName.Text.Length==0?Visibility.Collapsed:Visibility.Visible;
        if(state=="idle"){
            controls.Children.Add(Button("Record",()=>{if(pending||stopRequested)return;if(windows.SelectedItem==null&&desktopSession.IsChecked!=true)throw new Exception("Choose the window you want to record.");pending=true;pendingKind="record";status.Text="Checking recording scope…";capture.PrepareRecord(windows.SelectedItem==null?IntPtr.Zero:(IntPtr)((ComboBoxItem)windows.SelectedItem).Tag,desktopSession.IsChecked==true);Render();}));
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
            controls.Children.Add(Button("Submit prepared",()=>capture.SubmitPreparedRequest()));
        }else if(state=="paused"){
            controls.Children.Add(Button("Resume",()=>Command("resume",new {})));
            controls.Children.Add(Button("Stop",Stop));
        }else if(state=="interrupted")controls.Children.Add(Button("Review preserved draft",()=>Command("review",new {})));
        foreach(Button control in controls.Children){
            control.IsEnabled=ToolbarPresentation.CanControl(state,(string)control.Content,pending||stopRequested,connected);
            if((string)control.Content=="Record"&&windows.SelectedItem==null&&desktopSession.IsChecked!=true)control.IsEnabled=false;
            if((string)control.Content=="Record"||(string)control.Content=="Play"){
                control.Background=new SolidColorBrush(Color.FromRgb(184,154,66));control.Foreground=Brushes.White;
            }
        }
    }
    static string FormatLog(System.Collections.ArrayList rows) {return String.Join("\n",rows.Cast<object>().Select(x=>Convert.ToString(x)).ToArray());}
    void UpdateReviewEnabled() {
        if(reviewButton!=null)reviewButton.IsEnabled=state=="idle"&&connected&&!pending&&!stopRequested&&reviewRuns.SelectedItem!=null&&reviewChecked.IsChecked==true&&!String.IsNullOrWhiteSpace(reviewEvidence.Text);
    }
    void UpdateReview() {
        var item=reviewRuns.SelectedItem as ComboBoxItem;
        var row=item==null?null:(Dictionary<string,object>)item.Tag;
        string key=row==null?null:(string)row["id"]+":"+row["revision"]+":"+row["step"];
        if(key!=reviewIdentity){reviewIdentity=key;reviewEvidence.Text="";reviewChecked.IsChecked=false;}
        reviewSummary.Text=row==null?"":(string)row["summary"]+"\n"+(string)row["message"];
        UpdateReviewEnabled();
    }
    void Apply(Dictionary<string,object> d){
        if(!d.ContainsKey("v")||Convert.ToInt32(d["v"])!=1)return;
        if(!d.ContainsKey("runtime")||Convert.ToInt32(((Dictionary<string,object>)d["runtime"])["ipc"])!=2)throw new Exception("Incompatible helper protocol.");
        var runtime=(Dictionary<string,object>)d["runtime"];if(runtime.ContainsKey("native_sha256"))buildLabel.Text="local-phase5-20261022 / IPC 2 / "+Convert.ToString(runtime["native_sha256"]).Substring(0,8);
        if(d.ContainsKey("ack")&&(string)d["ack"]==pendingId){pending=false;pendingKind="";pendingId=null;}
        if((string)d["state"]=="interrupted"){pending=false;pendingKind="";pendingId=null;}
        string next=(string)d["state"];int epoch=Convert.ToInt32(d["generation"]);
        var lp=(Dictionary<string,object>)d["library_page"];libraryOffset=Convert.ToInt32(lp["offset"]);libraryNext=lp["next"]==null?(int?)null:Convert.ToInt32(lp["next"]);
        var rp=(Dictionary<string,object>)d["review_page"];reviewOffset=Convert.ToInt32(rp["offset"]);reviewNext=rp["next"]==null?(int?)null:Convert.ToInt32(rp["next"]);
        bool showSave=next=="draft"&&state!="draft";
        if(next=="idle"||next=="draft"||next=="interrupted")stopRequested=false;
        if(showSave&&d.ContainsKey("suggested_name"))name.Text=(string)d["suggested_name"];
        if(d.ContainsKey("recording_name"))contextName.Text=(string)d["recording_name"];
        if(next=="recording"&&(state!="recording"||epoch!=generation)){
            try{capture.Start(epoch,state=="paused");}catch(Exception e){Send("interrupt",new {reason=e.Message});return;}
        } else if(next!="recording"&&capture!=null)capture.Detach();
        state=next;generation=epoch;elapsed=Convert.ToInt64(d["elapsed_ms"]);segment.Reset();if(state=="recording")segment.Start();
        if(d.ContainsKey("action_log"))liveActionLog=FormatLog((System.Collections.ArrayList)d["action_log"]);
        if(state=="idle"&&d.ContainsKey("tasks")){
            var finished=d.ContainsKey("run")?d["run"] as Dictionary<string,object>:null;
            string previousRun=finished==null?null:(string)finished["task_id"],prefer=null;
            // Select a newly finished OS-started run once. Later snapshots must
            // preserve an explicit library choice made by the user.
            if(finished!=null&&(string)finished["id"]!=lastSelectedRunId){lastSelectedRunId=(string)finished["id"];prefer=previousRun;}
            if(d.ContainsKey("last_saved")&&d["last_saved"]!=null){
                string saved=(string)((Dictionary<string,object>)d["last_saved"])["id"];
                if(saved!=lastSavedId){lastSavedId=saved;prefer=saved;}
            }
            var recent=d.ContainsKey("selected_task")?d["selected_task"] as Dictionary<string,object>:null;
            // A Play request may expire before it creates a run. Keep that
            // requested task selected too, without reselecting it on every poll.
            if(recent!=null&&(string)recent["id"]!=lastPresentedTaskId){lastPresentedTaskId=(string)recent["id"];prefer=lastPresentedTaskId;}
            TaskList.Update(tasks,(System.Collections.ArrayList)d["tasks"],previousRun,recent,prefer);
        }
        if(d.ContainsKey("reviews"))TaskList.Update(reviewRuns,(System.Collections.ArrayList)d["reviews"],null);
        recoveryPanel.Visibility=state=="idle"&&reviewRuns.Items.Count>0?Visibility.Visible:Visibility.Collapsed;
        UpdateReview();
        playbackPaused=d.ContainsKey("run")&&d["run"]!=null&&(bool)((Dictionary<string,object>)d["run"])["pause_requested"];
        playbackProgress=null;
        if((state=="idle"||state=="playing")&&d.ContainsKey("run")&&d["run"]!=null){
            var run=(Dictionary<string,object>)d["run"];
            playbackProgress=((string)run["state"]=="completed"?"Completed":state=="playing"?(playbackPaused?"Paused":"Playing"):"Stopped")
                +" · "+run["next_step"]+"/"+run["total"]+" steps";
            if(state=="playing"&&run.ContainsKey("pending")&&run["pending"]!=null)
                playbackProgress="Step "+(Convert.ToInt32(run["pending"])+1)+" of "+run["total"]+" · "+(playbackPaused?"Pausing":"Playing");
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


