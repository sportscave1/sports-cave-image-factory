using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Automation;

// UIA-only candidate executor. Never falls back to coordinates or raw key input.
class DesktopPlayback {
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr hwnd);
    [DllImport("user32.dll")] static extern bool RegisterHotKey(IntPtr hwnd,int id,uint modifiers,uint key);
    [DllImport("user32.dll")] static extern bool UnregisterHotKey(IntPtr hwnd,int id);
    readonly IntPtr owner;
    readonly Action<string,object> send;
    readonly ManualResetEvent cancelled=new ManualResetEvent(false);
    readonly ManualResetEvent ready=new ManualResetEvent(true);
    Native.Hook mouse,key;
    IntPtr mh,kh;
    volatile bool busy;
    long started;
    long pausedAt;
    int currentStep,timeout,resultSent;
    NativeMetrics metrics;
    public bool Active {get;private set;}
    public const int Hotkey=0x5343;
    public DesktopPlayback(IntPtr owner,Action<string,object> send){this.owner=owner;this.send=send;}
    public void Arm() {
        if(Active||busy)throw new Exception("Playback is already active.");
        if(!RegisterHotKey(owner,Hotkey,0x4003,0x7B)) // Ctrl+Alt+F12, MOD_NOREPEAT.
            throw new Exception("Emergency Stop shortcut is unavailable. Playback refused.");
        cancelled.Reset();
        ready.Set();
        mouse=Intervention;key=Intervention;
        mh=Native.SetWindowsHookEx(14,mouse,Native.GetModuleHandle(null),0);
        kh=Native.SetWindowsHookEx(13,key,Native.GetModuleHandle(null),0);
        if(mh==IntPtr.Zero||kh==IntPtr.Zero){Disarm();throw new Exception("Manual-intervention protection is unavailable.");}
        Active=true;
        metrics=NativeMetrics.Begin("playback");
    }
    IntPtr Intervention(int code,IntPtr message,IntPtr data) {
        if(code>=0&&Active) {
            IntPtr inputWindow=Native.Root(Native.GetForegroundWindow());
            int eventType=message.ToInt32();
            if(eventType>=0x200&&eventType<=0x20E){
                var pointer=(Native.Mouse)Marshal.PtrToStructure(data,typeof(Native.Mouse));
                inputWindow=Native.Root(Native.WindowFromPoint(pointer.point));
            }
            uint pid; Native.GetWindowThreadProcessId(inputWindow,out pid);
            // Movement does not cancel, but clicks, wheel and keyboard intervention do.
            // Mouse-down is observed before Windows activates its target. Use
            // the hit window so recorder controls remain usable from another app.
            if(!WindowIdentity.IsToolbar(pid,(uint)Process.GetCurrentProcess().Id)&&eventType!=0x200){
                Stop();send("play_stop",new {reason="Manual input stopped playback. Check any unconfirmed action."});
            }
        }
        return Native.CallNextHookEx(IntPtr.Zero,code,message,data);
    }
    public void Stop(){cancelled.Set();}
    public void Pause(){Interlocked.CompareExchange(ref pausedAt,Stopwatch.GetTimestamp(),0);ready.Reset();}
    public void Resume(){long began=Interlocked.Exchange(ref pausedAt,0);if(began!=0)Interlocked.Add(ref started,Stopwatch.GetTimestamp()-began);ready.Set();}
    public void Watchdog(){
        if(busy&&ready.WaitOne(0)&&(Stopwatch.GetTimestamp()-Interlocked.Read(ref started))/(double)Stopwatch.Frequency>timeout/1000.0+3){
            Stop();
            if(Interlocked.Exchange(ref resultSent,1)==0)
                send("play_result",new {step=currentStep,verified=false,message="Accessibility provider did not finish. Outcome uncertain; Stop and inspect the application before restarting the helper."});
        }
    }
    public void Disarm() {
        Stop();Active=false;
        if(mh!=IntPtr.Zero)Native.UnhookWindowsHookEx(mh);
        if(kh!=IntPtr.Zero)Native.UnhookWindowsHookEx(kh);
        mh=kh=IntPtr.Zero;UnregisterHotKey(owner,Hotkey);
        var completed=Interlocked.Exchange(ref metrics,null);
        if(completed!=null)completed.Finish(send);
        // This executor sends no keyboard/button-down input, so none can be held.
    }
    void Check(){
        while(!ready.WaitOne(0))if(cancelled.WaitOne(100))throw new OperationCanceledException("Playback stopped.");
        if(cancelled.WaitOne(0))throw new OperationCanceledException("Playback stopped.");
    }
    static bool Match(AutomationElement e,Dictionary<string,object> target) {
        return e.Current.ControlType.ProgrammaticName=="ControlType."+(string)target["control_type"]&&
            e.Current.AutomationId==(string)target["automation_id"]&&e.Current.Name==(string)target["name"];
    }
    static bool ScopeMatches(AutomationElement e,IntPtr hwnd,Dictionary<string,object> target) {
        if(!target.ContainsKey("scope"))return false;
        var expected=(System.Collections.ArrayList)target["scope"];int index=0;
        bool productCopy=ProductCopyResult.Supports(target);
        uint pid;Native.GetWindowThreadProcessId(hwnd,out pid);
        if(e.Current.ProcessId!=pid)return false;
        if(productCopy)return ProductCopyResult.ScopeMatches(expected,ProductAncestors(e,hwnd,pid));
        var parent=TreeWalker.ControlViewWalker.GetParent(e);
        for(int depth=0;parent!=null&&depth<16;depth++){
            if(parent.Current.ProcessId!=pid)return false;
            if(parent.Current.NativeWindowHandle==hwnd.ToInt32())
                return index==expected.Count;
            if(parent.Current.AutomationId.Length>0||parent.Current.Name.Length>0){
                if(index>=expected.Count||!Match(parent,(Dictionary<string,object>)expected[index]))return false;
                index++;
            }
            parent=TreeWalker.ControlViewWalker.GetParent(parent);
        }
        return false;
    }
    static IEnumerable<ProductCopyResult.ScopeAnchor> ProductAncestors(AutomationElement element,IntPtr hwnd,uint pid) {
        var parent=TreeWalker.ControlViewWalker.GetParent(element);
        for(int depth=0;parent!=null&&depth<16;depth++,parent=TreeWalker.ControlViewWalker.GetParent(parent)) {
            if(parent.Current.ProcessId!=pid)throw new Exception("Control ancestry left the intended application.");
            if(parent.Current.NativeWindowHandle==hwnd.ToInt32())yield break;
            var current=parent;
            yield return new ProductCopyResult.ScopeAnchor(current.Current.ControlType.ProgrammaticName.Replace("ControlType.",""),
                current.Current.AutomationId,()=>current.Current.Name,()=>Capture.SafeAnonymousHost(current));
        }
        throw new Exception("Control ancestry does not reach the intended window within the supported bound.");
    }
    bool EdgeDocumentMatches(IntPtr hwnd,string name) {
        Check();uint pid;Native.GetWindowThreadProcessId(hwnd,out pid);
        var root=AutomationElement.FromHandle(hwnd);
        var documents=root.FindAll(TreeScope.Descendants,new AndCondition(
            new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Document),
            new PropertyCondition(AutomationElement.AutomationIdProperty,"RootWebArea"),
            new PropertyCondition(AutomationElement.NameProperty,name)));
        if(documents.Count>16)return false;
        int matches=0;
        foreach(AutomationElement document in documents) {
            Check();
            if(document.Current.ProcessId!=pid)continue;
            try{Privacy(document);}catch{continue;}
            var parent=TreeWalker.ControlViewWalker.GetParent(document);
            for(int depth=0;parent!=null&&depth<16;depth++,parent=TreeWalker.ControlViewWalker.GetParent(parent)) {
                Check();
                if(parent.Current.ProcessId!=pid)break;
                if(parent.Current.NativeWindowHandle==hwnd.ToInt32()){matches++;break;}
                if(parent.Current.ControlType==ControlType.Document)break; // A named iframe cannot identify the browser page.
            }
        }
        return matches==1;
    }
    IntPtr Window(Dictionary<string,object> target) {
        var matches=new List<IntPtr>();
        var normalized=new HashSet<IntPtr>();
        Native.EnumWindows((h,l)=>{
            string title=Native.Title(h);
            if(Native.IsWindowVisible(h)&&WindowIdentity.PlaybackTitleMatches((string)target["app"],
                (string)target["window_key"],title,page=>true)){
                try{
                    Check();Native.CheckProcess(h);
                    if(String.Equals(Native.ProcessFor(h).MainModule.FileName,(string)target["app"],StringComparison.OrdinalIgnoreCase)&&
                       WindowIdentity.PlaybackTitleMatches((string)target["app"],(string)target["window_key"],title,
                           page=>EdgeDocumentMatches(h,page))){
                        matches.Add(h);
                        if(title!=(string)target["window_key"])normalized.Add(h);
                    }
                }catch(OperationCanceledException){return false;}catch{}
            }return true;
        },IntPtr.Zero);
        Check();
        if(matches.Count!=1)throw new Exception(matches.Count==0?"Prepare the recorded window before Play.":"More than one matching window is open. Close the ambiguity before Play.");
        if(normalized.Contains(matches[0]))send("diagnostic",new {kind="playback_edge_document_identity",step=currentStep,
            tab_count_changed=true,top_level_document_verified=true,dpi=Native.GetDpiForWindow(matches[0]),monitors=Native.GetSystemMetrics(80)});
        return matches[0];
    }
    static void Privacy(AutomationElement e,bool allowDisabled=false) {
        object value=e.GetCurrentPropertyValue(AutomationElement.IsPasswordProperty,true);
        if(!(value is bool)||(bool)value)throw new Exception("Protected or unclassified target. Playback refused.");
        if((!allowDisabled&&!e.Current.IsEnabled)||e.Current.IsOffscreen)throw new Exception("Target is not ready.");
    }
    AutomationElement Resolve(IntPtr hwnd,Dictionary<string,object> target,string kind,bool allowDisabled=false) {
        var root=AutomationElement.FromHandle(hwnd);
        if(kind=="focus_window")return root;
        var condition=new AndCondition(
            new PropertyCondition(AutomationElement.AutomationIdProperty,(string)target["automation_id"]),
            new PropertyCondition(AutomationElement.NameProperty,(string)target["name"]));
        var matches=root.FindAll(TreeScope.Descendants,condition);
        AutomationElement found=null;int count=0;
        for(int i=0;i<matches.Count;i++)if(Match(matches[i],target)&&ScopeMatches(matches[i],hwnd,target)){found=matches[i];count++;}
        if(count!=1)throw new Exception(count==0?"Recorded control is not ready.":"Recorded control is ambiguous. No input sent.");
        Privacy(found,allowDisabled);return found;
    }
    static string DiagnosticGroupName(AutomationElement parent) {
        if(parent.Current.Name.Length>180)return "[excluded]";
        try{return Capture.Safe(parent.Current.Name);}catch{return "[excluded]";}
    }
    void DiagnoseResolution(IntPtr hwnd,Dictionary<string,object> target,int step) {
        // Failure-only metadata. Retain only a bounded, privacy-checked name
        // for an unexpected Group; never retain field values, clipboard,
        // coordinates or runtime IDs from the current application.
        var root=AutomationElement.FromHandle(hwnd);
        var matches=root.FindAll(TreeScope.Descendants,new PropertyCondition(
            AutomationElement.AutomationIdProperty,(string)target["automation_id"]));
        var candidates=new List<object>();
        var expected=(System.Collections.ArrayList)target["scope"];
        uint pid;Native.GetWindowThreadProcessId(hwnd,out pid);
        for(int i=0;i<matches.Count&&i<3;i++) {
            var candidate=matches[i];var ancestry=new List<object>();
            var parent=TreeWalker.ControlViewWalker.GetParent(candidate);bool reached=false;
            for(int depth=0;parent!=null&&depth<16;depth++,parent=TreeWalker.ControlViewWalker.GetParent(parent)) {
                if(parent.Current.NativeWindowHandle==hwnd.ToInt32()){reached=true;break;}
                if(ProductCopyResult.Supports(target)&&ancestry.Count==3&&
                   ProductCopyResult.HostBoundary(ancestry.Count,parent.Current.ControlType.ProgrammaticName.Replace("ControlType.",""),parent.Current.AutomationId)) {
                    ancestry.Add(new {control_type="ControlType.Group",id_empty=true,host_layout_group=true,name_read=false,host_allowed=Capture.SafeAnonymousHost(parent),
                        process_matches=parent.Current.ProcessId==pid});
                    continue;
                }
                if(parent.Current.AutomationId.Length==0&&parent.Current.Name.Length==0)continue;
                var corresponding=new List<int>();
                for(int j=0;j<expected.Count;j++)if(Match(parent,(Dictionary<string,object>)expected[j]))corresponding.Add(j);
                ancestry.Add(new {control_type=parent.Current.ControlType.ProgrammaticName,
                    name_empty=parent.Current.Name.Length==0,id_empty=parent.Current.AutomationId.Length==0,
                    matches_expected=corresponding,process_matches=parent.Current.ProcessId==pid,
                    unexpected_group_name=corresponding.Count==0&&parent.Current.ControlType==ControlType.Group?DiagnosticGroupName(parent):null,
                    component_wrapper=parent.Current.ControlType==ControlType.Group&&parent.Current.AutomationId.Length==0&&parent.Current.Name==ProductCopyResult.Component});
            }
            candidates.Add(new {type_matches=candidate.Current.ControlType.ProgrammaticName=="ControlType."+(string)target["control_type"],
                name_matches=candidate.Current.Name==(string)target["name"],process_matches=candidate.Current.ProcessId==pid,
                enabled=candidate.Current.IsEnabled,offscreen=candidate.Current.IsOffscreen,
                scope_matches=ScopeMatches(candidate,hwnd,target),reached_window=reached,ancestors=ancestry,
                copy_ready=candidate.Current.HelpText==ProductCopyResult.Ready,
                copy_success=candidate.Current.HelpText==ProductCopyResult.Success});
        }
        send("diagnostic",new {kind="playback_resolution_unavailable",step=step,
            id_candidate_count=matches.Count,expected_ancestor_count=expected.Count,candidates=candidates});
    }
    void Focus(IntPtr hwnd) {
        IntPtr initial=Native.Root(Native.GetForegroundWindow());
        if(initial==hwnd)return;
        if(!SetForegroundWindow(hwnd))throw new Exception("Could not safely focus the intended window. No input sent.");
        var activation=Stopwatch.StartNew();
        while(activation.ElapsedMilliseconds<1500){
            Check();
            IntPtr current=Native.Root(Native.GetForegroundWindow());
            if(current==hwnd)return;
            // Windows may still report the initiating toolbar while activation
            // is pending. A third window is an intervention, not a retry.
            if(current!=initial&&current!=IntPtr.Zero)
                throw new Exception("Another window took focus. No input sent.");
            if(cancelled.WaitOne(25))Check();
        }
        throw new Exception("The intended window did not become active. No input sent.");
    }
    bool VerifyResult(IntPtr hwnd,Dictionary<string,object> target,string kind,object expected) {
        // Provider mutations can return before the browser publishes its new
        // accessibility value. Re-resolve and observe; never repeat the effect.
        var wait=Stopwatch.StartNew();
        while(wait.ElapsedMilliseconds<2000) {
            Check();
            if(Native.Root(Native.GetForegroundWindow())!=hwnd)
                throw new Exception("Focus changed while verifying the result. Action was not repeated.");
            var current=Resolve(hwnd,target,kind,kind=="invoke");object pattern;
            if(kind=="invoke"&&ProductCopyResult.Supports(target)&&current.Current.IsEnabled&&
                current.Current.HelpText==ProductCopyResult.Success)return true;
            if(kind=="set_text"&&current.TryGetCurrentPattern(ValuePattern.Pattern,out pattern)
                &&((ValuePattern)pattern).Current.Value==(string)expected)return true;
            if(kind=="toggle"&&current.TryGetCurrentPattern(TogglePattern.Pattern,out pattern)
                &&((TogglePattern)pattern).Current.ToggleState==((bool)expected?ToggleState.On:ToggleState.Off))return true;
            if(kind=="select"&&current.TryGetCurrentPattern(SelectionItemPattern.Pattern,out pattern)
                &&((SelectionItemPattern)pattern).Current.IsSelected)return true;
            if(kind=="expand"&&current.TryGetCurrentPattern(ExpandCollapsePattern.Pattern,out pattern)
                &&((ExpandCollapsePattern)pattern).Current.ExpandCollapseState==((bool)expected?ExpandCollapseState.Expanded:ExpandCollapseState.Collapsed))return true;
            if(kind=="scroll"&&current.TryGetCurrentPattern(ScrollPattern.Pattern,out pattern)){
                var desired=(Dictionary<string,object>)expected;var actual=((ScrollPattern)pattern).Current;
                double horizontal=Convert.ToDouble(desired["horizontal"]),vertical=Convert.ToDouble(desired["vertical"]);
                if((horizontal==ScrollPattern.NoScroll||Math.Abs(actual.HorizontalScrollPercent-horizontal)<=0.5)&&
                   (vertical==ScrollPattern.NoScroll||Math.Abs(actual.VerticalScrollPercent-vertical)<=0.5))return true;
            }
            if(cancelled.WaitOne(50))Check();
        }
        return false;
    }
    public void Execute(int step,Dictionary<string,object> action) {
        if(!Active||busy)throw new Exception("Executor unavailable.");
        ready.Set();
        currentStep=step;timeout=Convert.ToInt32(action["timeout_ms"]);resultSent=0;
        Interlocked.Exchange(ref pausedAt,0);
        Interlocked.Exchange(ref started,Stopwatch.GetTimestamp());
        busy=true;
        var worker=new Thread(()=>{
            bool verified=false,effectStarted=false;string reason="";
            Dictionary<string,object> diagnosticTarget=null;IntPtr diagnosticWindow=IntPtr.Zero;
            try {
                Check();
                var target=(Dictionary<string,object>)action["target"];
                diagnosticTarget=target;
                string kind=(string)action["kind"];
                AutomationElement e=null;IntPtr hwnd=IntPtr.Zero;
                while(true){
                    Check();
                    try {hwnd=Window(target);diagnosticWindow=hwnd;e=Resolve(hwnd,target,kind);
                        if(kind=="invoke"&&ProductCopyResult.Supports(target)&&e.Current.HelpText!=ProductCopyResult.Ready)
                            throw new Exception("Copy prompt is not ready for verified playback. Wait for feedback to clear or refresh the prepared Product Uploads page.");
                        break;}
                    catch(ElementNotAvailableException){reason="The document changed.";}
                    catch(Exception ex){reason=ex.Message;}
                    if((Stopwatch.GetTimestamp()-Interlocked.Read(ref started))*1000.0/Stopwatch.Frequency>=timeout)throw new Exception(reason);
                    if(cancelled.WaitOne(150))Check();
                }
                Check();
                Focus(hwnd);
                Check();
                if(Native.Root(Native.GetForegroundWindow())!=hwnd)throw new Exception("Window focus changed. No input sent.");
                e=Resolve(hwnd,target,kind);object pattern;
                Check();
                if(Native.Root(Native.GetForegroundWindow())!=hwnd)throw new Exception("Window focus changed during target validation. No input sent.");
                switch(kind){
                    case "focus_window": verified=true;break;
                    case "wait_ready":verified=true;break;
                    case "set_text":
                        if(!e.TryGetCurrentPattern(ValuePattern.Pattern,out pattern)||((ValuePattern)pattern).Current.IsReadOnly)
                            throw new Exception("This editor does not support safe semantic text replacement.");
                        effectStarted=true;((ValuePattern)pattern).SetValue((string)action["value"]);
                        verified=VerifyResult(hwnd,target,kind,action["value"]);break;
                    case "toggle":
                        if(!e.TryGetCurrentPattern(TogglePattern.Pattern,out pattern))throw new Exception("Toggle pattern unavailable.");
                        var toggle=(TogglePattern)pattern;
                        var desired=(bool)action["value"]?ToggleState.On:ToggleState.Off;
                        if(toggle.Current.ToggleState!=desired){effectStarted=true;toggle.Toggle();}
                        verified=VerifyResult(hwnd,target,kind,action["value"]);break;
                    case "select":
                        if(!e.TryGetCurrentPattern(SelectionItemPattern.Pattern,out pattern))throw new Exception("Selection pattern unavailable.");
                        effectStarted=true;((SelectionItemPattern)pattern).Select();verified=VerifyResult(hwnd,target,kind,null);break;
                    case "expand":
                        if(!e.TryGetCurrentPattern(ExpandCollapsePattern.Pattern,out pattern))throw new Exception("Menu expansion pattern unavailable.");
                        var expandable=(ExpandCollapsePattern)pattern;
                        var expansion=(bool)action["value"]?ExpandCollapseState.Expanded:ExpandCollapseState.Collapsed;
                        if(expandable.Current.ExpandCollapseState!=expansion){effectStarted=true;if((bool)action["value"])expandable.Expand();else expandable.Collapse();}
                        verified=VerifyResult(hwnd,target,kind,action["value"]);break;
                    case "scroll":
                        if(!e.TryGetCurrentPattern(ScrollPattern.Pattern,out pattern))throw new Exception("Scroll pattern unavailable.");
                        var position=(Dictionary<string,object>)action["value"];
                        effectStarted=true;((ScrollPattern)pattern).SetScrollPercent(Convert.ToDouble(position["horizontal"]),Convert.ToDouble(position["vertical"]));
                        verified=VerifyResult(hwnd,target,kind,position);break;
                    case "invoke":
                        if(!e.TryGetCurrentPattern(InvokePattern.Pattern,out pattern))throw new Exception("Invoke pattern unavailable.");
                        bool productCopy=ProductCopyResult.Supports(target);
                        if(productCopy&&e.Current.HelpText!=ProductCopyResult.Ready)
                            throw new Exception("Copy prompt readiness changed. No input sent.");
                        effectStarted=true;((InvokePattern)pattern).Invoke();
                        // Provider return is not application result verification.
                        if(productCopy)verified=VerifyResult(hwnd,target,kind,null);
                        else reason="Button invoked; its application result needs verification before continuing.";
                        break;
                    default:throw new Exception("Unsupported desktop action.");
                }
                if(!verified&&reason.Length==0)reason="The expected control result was not observed within 2 seconds. Action was not repeated.";
                Check();
            }catch(Exception ex){reason=ex.Message;verified=false;
                if(!effectStarted&&!(ex is OperationCanceledException)&&diagnosticWindow!=IntPtr.Zero&&diagnosticTarget!=null&&diagnosticTarget.ContainsKey("scope")) {
                    try{DiagnoseResolution(diagnosticWindow,diagnosticTarget,step);}catch{ /* Original failure remains authoritative. */ }
                }
            }
            finally{busy=false;if(Interlocked.Exchange(ref resultSent,1)==0)send("play_result",new {step=step,verified=verified,no_effect=!effectStarted,message=reason});}
        }){IsBackground=true};
        worker.SetApartmentState(ApartmentState.MTA);worker.Start();
    }
}
