using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
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
    int identityReportedStep=-1;
    NativeMetrics metrics;
    readonly RunTransfer transfer=new RunTransfer();
    public bool Active {get;private set;}
    public const int Hotkey=0x5343;
    public DesktopPlayback(IntPtr owner,Action<string,object> send){this.owner=owner;this.send=send;}
    public void Arm() {
        if(Active||busy)throw new Exception("Playback is already active.");
        transfer.Clear();
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
    public void Stop(){cancelled.Set();transfer.Clear();}
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
            (e.Current.AutomationId==(string)target["automation_id"]||
                (string)target["control_type"]=="ComboBox"&&(string)target["automation_id"]==""&&((string)target["name"]).Length>0)&&e.Current.Name==(string)target["name"];
    }
    internal static bool ScopeMatches(AutomationElement e,IntPtr hwnd,Dictionary<string,object> target) {
        if(!target.ContainsKey("scope"))return false;
        var expected=(System.Collections.IList)target["scope"];int index=0;
        bool productCopy=ProductCopyResult.Supports(target);
        uint pid;Native.GetWindowThreadProcessId(hwnd,out pid);
        if(e.Current.ProcessId!=pid)return false;
        if(productCopy)return ProductCopyResult.ScopeMatches(expected,ProductAncestors(e,hwnd,pid));
        if(ProductGenerationResult.Supports(target))return ProductGenerationResult.ScopeMatches(expected,ProductAncestors(e,hwnd,pid));
        int ancestryLimit=DropdownSelection.AncestryLimit;
        var parent=TreeWalker.ControlViewWalker.GetParent(e);
        for(int depth=0;parent!=null&&depth<ancestryLimit;depth++){
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
        if(target.ContainsKey("browser")){
            var expected=(Dictionary<string,object>)target[target.ContainsKey("source_browser")?"source_browser":"browser"];
            Native.EnumWindows((h,l)=>{if(Native.IsWindowVisible(h)){try{if(String.Equals(Native.ProcessFor(h).MainModule.FileName,(string)target["app"],StringComparison.OrdinalIgnoreCase)&&BrowserIdentity.SamePage(BrowserIdentity.Current(h),expected))matches.Add(h);}catch{}}return true;},IntPtr.Zero);
            Check();if(matches.Count!=1)throw new Exception("Prepare exactly one matching browser profile and page. No window guessed.");return matches[0];
        }
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
        if(normalized.Contains(matches[0])&&identityReportedStep!=currentStep){identityReportedStep=currentStep;
            if(String.Equals(System.IO.Path.GetFileName((string)target["app"]),"msedge.exe",StringComparison.OrdinalIgnoreCase))
                send("diagnostic",new {kind="playback_edge_document_identity",step=currentStep,
                    tab_count_changed=true,top_level_document_verified=true,dpi=Native.GetDpiForWindow(matches[0]),monitors=Native.GetSystemMetrics(80)});
            else send("diagnostic",new {kind="playback_named_document_identity",step=currentStep,dirty_marker_changed=true});}
        return matches[0];
    }
    static void Privacy(AutomationElement e,bool allowDisabled=false,bool allowOffscreen=false) {
        object value=e.GetCurrentPropertyValue(AutomationElement.IsPasswordProperty,true);
        if(!(value is bool)||(bool)value)throw new Exception("Protected or unclassified target. Playback refused.");
        if((!allowDisabled&&!e.Current.IsEnabled)||(!allowOffscreen&&e.Current.IsOffscreen))throw new Exception("Target is not ready.");
    }
    internal sealed class ControlNotReadyException : Exception {
        public ControlNotReadyException(string message):base(message){}
    }
    AutomationElement Resolve(IntPtr hwnd,Dictionary<string,object> target,string kind,bool allowDisabled=false,bool allowOffscreen=false) {
        var root=AutomationElement.FromHandle(hwnd);
        if(kind=="browser_tab")return BrowserTabs.Find(hwnd,(string)target["name"],false);
        if(kind=="focus_window"||kind=="window_state")return root;
        if(target.ContainsKey("browser")){var foundBrowser=BrowserIdentity.Resolve(hwnd,target);Privacy(foundBrowser,allowDisabled,allowOffscreen);return foundBrowser;}
        if(target.ContainsKey("selector")) {
            if(kind!="scroll"||(string)target["selector"]!=ScrollAccess.ScopedSelector)
                throw new Exception("Unsupported scoped control selector.");
            var scroll=ScrollAccess.ResolveScoped(hwnd,target);Privacy(scroll,allowDisabled,allowOffscreen);return scroll;
        }
        Condition condition=new AndCondition(
            new PropertyCondition(AutomationElement.AutomationIdProperty,(string)target["automation_id"]),
            new PropertyCondition(AutomationElement.NameProperty,(string)target["name"]));
        if((string)target["control_type"]=="ComboBox"&&(string)target["automation_id"]=="")condition=new AndCondition(
            new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.ComboBox),
            new PropertyCondition(AutomationElement.NameProperty,(string)target["name"]));
        var matches=root.FindAll(TreeScope.Descendants,condition);
        AutomationElement found=null;int count=0;
        for(int i=0;i<matches.Count;i++)if(Match(matches[i],target)&&ScopeMatches(matches[i],hwnd,target)){found=matches[i];count++;}
        if(count==0)throw new ControlNotReadyException("Recorded control is not ready.");
        if(count!=1)throw new Exception("Recorded control is ambiguous. No input sent.");
        Privacy(found,allowDisabled,allowOffscreen);return found;
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
        var matches=root.FindAll(TreeScope.Descendants,new AndCondition(
            new PropertyCondition(AutomationElement.AutomationIdProperty,(string)target["automation_id"]),
            new PropertyCondition(AutomationElement.NameProperty,(string)target["name"]),
            new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Button)));
        // Non-button diagnostics keep their actual type rather than sampling
        // arbitrary controls that share an empty AutomationId.
        if((string)target["control_type"]!="Button")matches=root.FindAll(TreeScope.Descendants,new AndCondition(
            new PropertyCondition(AutomationElement.AutomationIdProperty,(string)target["automation_id"]),
            new PropertyCondition(AutomationElement.NameProperty,(string)target["name"])));
        var candidates=new List<object>();
        var expected=(System.Collections.IList)target["scope"];
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
        DesktopWindowState.Restore(hwnd,Check);
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
    bool VerifyResult(IntPtr hwnd,Dictionary<string,object> target,string kind,object expected,AutomationElement appliedScroll=null) {
        // Provider mutations can return before the browser publishes its new
        // accessibility value. Re-resolve and observe; never repeat the effect.
        double verificationBegan=ActionElapsedMs();
        double? lastHorizontal=null,lastVertical=null,lastVerticalView=null;string lastScrollMethod=null;
        while(ActionElapsedMs()-verificationBegan<2000) {
            Check();
            if(Native.Root(Native.GetForegroundWindow())!=hwnd)
                throw new Exception("Focus changed while verifying the result. Action was not repeated.");
            try {
            // Scrolling can give an anonymous Chromium layout container a
            // generated accessible name. Observe the exact provider we used,
            // with its scope/protection rechecked; do not widen the selector.
            // This reference lives only for this action's result verification.
            var current=appliedScroll??Resolve(hwnd,target,kind,kind=="invoke");object pattern;
            if(appliedScroll!=null) {
                Privacy(current);
                if(kind!="scroll"||!target.ContainsKey("selector")||
                    (string)target["selector"]!=ScrollAccess.ScopedSelector||
                    current.Current.ControlType.ProgrammaticName!="ControlType."+(string)target["control_type"]||
                    current.Current.AutomationId!=(string)target["automation_id"]||
                    !ScopeMatches(current,hwnd,target))
                    throw new Exception("The applied scroll container identity changed. Action was not repeated.");
            }
            if(kind=="invoke"&&ProductCopyResult.Supports(target)&&current.Current.IsEnabled) {
                if(target.ContainsKey("prompt_proof")) {
                    var proof=(Dictionary<string,object>)target["prompt_proof"];
                    if(!ProductPromptProof.Same(proof,ProductPromptProof.Parse(current.Current.HelpText)))
                        throw new Exception("The complete prompt changed during Copy. Result is unverified.");
                    if(current.Current.HelpText.Split('\n').Contains(ProductCopyResult.Success)&&ProductPromptProof.ClipboardMatches(proof))return true;
                } else if(current.Current.HelpText==ProductCopyResult.Success)return true;
            }
            if(kind=="set_text"&&current.TryGetCurrentPattern(ValuePattern.Pattern,out pattern)
                &&((ValuePattern)pattern).Current.Value==(string)expected)return true;
            if(kind=="toggle"&&current.TryGetCurrentPattern(TogglePattern.Pattern,out pattern)
                &&((TogglePattern)pattern).Current.ToggleState==((bool)expected?ToggleState.On:ToggleState.Off))return true;
            if(kind=="select"&&current.TryGetCurrentPattern(SelectionItemPattern.Pattern,out pattern)
                &&((SelectionItemPattern)pattern).Current.IsSelected)return true;
            if(kind=="select"&&current.Current.ControlType==ControlType.ComboBox) {
                uint pid;Native.GetWindowThreadProcessId(hwnd,out pid);
                if(DropdownSelection.Selected(current,pid)==(string)expected)return true;
            }
            if(kind=="expand"&&current.TryGetCurrentPattern(ExpandCollapsePattern.Pattern,out pattern)
                &&((ExpandCollapsePattern)pattern).Current.ExpandCollapseState==((bool)expected?ExpandCollapseState.Expanded:ExpandCollapseState.Collapsed))return true;
            if(kind=="scroll"){
                var desired=(Dictionary<string,object>)expected;
                double horizontal=Convert.ToDouble(desired["horizontal"]),vertical=Convert.ToDouble(desired["vertical"]);
                uint pid;Native.GetWindowThreadProcessId(hwnd,out pid);
                var binding=ScrollAccess.Bind(current,pid,horizontal!=-1,vertical!=-1);
                if(binding!=null){lastHorizontal=binding.Horizontal;lastVertical=binding.Vertical;lastVerticalView=binding.VerticalView;lastScrollMethod=binding.Method;}
                if(binding!=null&&binding.MatchesViewport(desired)&&binding.At(horizontal,vertical)) {
                    if(appliedScroll!=null)send("diagnostic",new {kind="scroll_result_same_container",step=currentStep,
                        name_became_nonempty=current.Current.Name.Length!=0,scope_verified=true,
                        observed_horizontal=lastHorizontal,observed_vertical=lastVertical,observed_vertical_view=lastVerticalView});
                    return true;
                }
            }
            }catch(ElementNotAvailableException) {
                // Only observe a fresh, exactly scoped replacement after a
                // rerender. The effect has already been sent; never repeat it.
                appliedScroll=null;
            }catch(ControlNotReadyException) {
                // Ambiguity, protection failures and focus changes still stop.
            }
            if(cancelled.WaitOne(50))Check();
        }
        if(kind=="scroll")send("diagnostic",new {kind="scroll_result_unverified",step=currentStep,expected=expected,
            observed_horizontal=lastHorizontal,observed_vertical=lastVertical,observed_vertical_view=lastVerticalView,method=lastScrollMethod});
        return false;
    }
    double ActionElapsedMs(){return (Stopwatch.GetTimestamp()-Interlocked.Read(ref started))*1000.0/Stopwatch.Frequency;}
    bool VerifyPicker(IntPtr hwnd,AutomationElement document) {
        uint pid;Native.GetWindowThreadProcessId(hwnd,out pid);
        var wait=Stopwatch.StartNew();
        while(wait.ElapsedMilliseconds<2000) {
            Check();
            if(Native.Root(Native.GetForegroundWindow())!=hwnd)throw new Exception("Focus changed while opening the PSD picker.");
            if(ProductPickerResult.Open(document,hwnd,pid))return true;
            if(cancelled.WaitOne(25))Check();
        }
        return false;
    }
    bool VerifyDialogClosed(IntPtr hwnd,Dictionary<string,object> button) {
        var target=DialogResult.Target(button);var wait=Stopwatch.StartNew();
        while(wait.ElapsedMilliseconds<2000) {
            Check();if(Native.Root(Native.GetForegroundWindow())!=hwnd)throw new Exception("Focus left the containing dialog's window.");
            var root=AutomationElement.FromHandle(hwnd);
            var dialogs=root.FindAll(TreeScope.Descendants,new AndCondition(
                new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Window),
                new PropertyCondition(AutomationElement.AutomationIdProperty,target["automation_id"]),
                new PropertyCondition(AutomationElement.NameProperty,target["name"])));
            int visible=0;foreach(AutomationElement dialog in dialogs)if(!dialog.Current.IsOffscreen&&ScopeMatches(dialog,hwnd,target))visible++;
            if(visible==0)return true;
            if(visible>1)throw new Exception("Dialog result is ambiguous. Action was not repeated.");
            if(cancelled.WaitOne(25))Check();
        }
        return false;
    }
    ProductGenerationResult.Witness GenerationWitness(IntPtr hwnd,Dictionary<string,object> target,bool observing=false) {
        uint pid;Native.GetWindowThreadProcessId(hwnd,out pid);
        // The application scrolls to previews after generation. Only this
        // observation may re-resolve an offscreen control; mutation still
        // requires the normal visible/enabled target immediately beforehand.
        return ProductGenerationResult.Read(Resolve(hwnd,target,"invoke",true,observing),hwnd,pid);
    }
    bool VerifyGeneration(IntPtr hwnd,Dictionary<string,object> target,ProductGenerationResult.Witness before) {
        bool workingObserved=false;
        while((Stopwatch.GetTimestamp()-Interlocked.Read(ref started))*1000.0/Stopwatch.Frequency<timeout) {
            Check();
            if(Native.Root(Native.GetForegroundWindow())!=hwnd)
                throw new Exception("Focus changed while verifying generation. Generate was not repeated.");
            ProductGenerationResult.Witness after=null;
            try{after=GenerationWitness(hwnd,target,true);}
            catch(ElementNotAvailableException){} // A normal Streamlit rerender can replace the button.
            catch(Exception ex){if(ex.Message!="Recorded control is not ready.")throw;}
            if(after!=null&&after.Receipt!=before.Receipt&&after.State=="working")workingObserved=true;
            if(ProductGenerationResult.Completed(before,after)){
                send("diagnostic",new {kind="generation_result_verified",fresh_working_state_observed=workingObserved,
                    fresh_application_acknowledgement=true,applied_result_verified=true});return true;}
            if(after!=null&&after.Receipt!=before.Receipt&&(after.State=="failed"||after.State=="changed"))
                throw new Exception("Generation failed or its product context changed. Generate was not repeated.");
            if(cancelled.WaitOne(100))Check();
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
                if(kind!="window_state")Focus(hwnd);
                Check();
                if(kind!="window_state"&&Native.Root(Native.GetForegroundWindow())!=hwnd)throw new Exception("Window focus changed. No input sent.");
                e=Resolve(hwnd,target,kind);object pattern;
                Check();
                if(kind!="window_state"&&Native.Root(Native.GetForegroundWindow())!=hwnd)throw new Exception("Window focus changed during target validation. No input sent.");
                switch(kind){
                    case "browser_tab":
                        string sourcePage,sourceProfile;
                        if(target.ContainsKey("source_browser")) {
                            if(!BrowserIdentity.SamePage(BrowserIdentity.Current(hwnd),(Dictionary<string,object>)target["source_browser"]))
                                throw new Exception("The starting browser profile or page changed. No tab selected.");
                        } else if(!WindowIdentity.EdgeTitle((string)target["window_key"],out sourcePage,out sourceProfile)||
                            !BrowserTabs.Document(hwnd,sourcePage))throw new Exception("The starting browser page could not be verified. No tab selected.");
                        if(!e.TryGetCurrentPattern(SelectionItemPattern.Pattern,out pattern))throw new Exception("Browser tab selection is unavailable.");
                        effectStarted=true;((SelectionItemPattern)pattern).Select();
                        while(true) {
                            Check();
                            if((Stopwatch.GetTimestamp()-Interlocked.Read(ref started))*1000.0/Stopwatch.Frequency>=timeout)
                                throw new Exception("Browser tab document did not become ready. Selection was not repeated.");
                            if(Native.Root(Native.GetForegroundWindow())!=hwnd)throw new Exception("Browser focus changed while verifying its tab.");
                            BrowserTabs.Find(hwnd,(string)target["name"],true);
                            if(BrowserTabs.Document(hwnd,(string)target["name"])&&(!target.ContainsKey("browser")||
                                BrowserIdentity.SamePage(BrowserIdentity.Current(hwnd),(Dictionary<string,object>)target["browser"]))){verified=true;break;}
                            if(cancelled.WaitOne(100))Check();
                        }
                        break;
                    case "browser_navigation":
                        if(!e.TryGetCurrentPattern(InvokePattern.Pattern,out pattern))throw new Exception("Navigation button cannot be invoked.");
                        var destination=(Dictionary<string,object>)action["value"];
                        effectStarted=true;((InvokePattern)pattern).Invoke();
                        var navigationWait=Stopwatch.StartNew();
                        while(navigationWait.ElapsedMilliseconds<timeout) {
                            Check();if(Native.Root(Native.GetForegroundWindow())!=hwnd)throw new Exception("Navigation lost its owning browser window.");
                            if(BrowserIdentity.SamePage(BrowserIdentity.Current(hwnd),destination)){verified=true;break;}
                            if(cancelled.WaitOne(50))Check();
                        }
                        if(!verified)reason="Expected browser destination was not observed. Navigation was not repeated.";
                        break;
                    case "focus_window": verified=true;break;
                    case "window_state":
                        effectStarted=DesktopWindowState.Read(hwnd)!=(string)action["value"];
                        DesktopWindowState.Apply(hwnd,(string)action["value"],Check);
                        verified=DesktopWindowState.Read(hwnd)==(string)action["value"];break;
                    case "wait_ready":verified=true;break;
                    case "browser_download":
                        var downloadSource=BrowserDownload.Read(e);
                        if(downloadSource==null||!BrowserDownload.SameSource((Dictionary<string,object>)target["download"],downloadSource))
                            throw new Exception("Download source changed. No input sent.");
                        var downloadSession=new BrowserDownload.Session();
                        if(!e.TryGetCurrentPattern(InvokePattern.Pattern,out pattern))throw new Exception("Download control cannot be invoked.");
                        var downloadStarted=DateTime.UtcNow;
                        Check();effectStarted=true;((InvokePattern)pattern).Invoke();
                        var downloadResult=downloadSession.Wait(downloadSource,downloadStarted,Check);
                        BrowserDownload.Persist(downloadResult);verified=true;break;
                    case "transfer_copy":
                        transfer.Clear();
                        string sourceText=RunTransfer.ReadEditor(e,false);
                        Check();effectStarted=true;
                        transfer.Copy(Convert.ToInt32(((Dictionary<string,object>)action["value"])["slot"]),sourceText,()=>{
                            if(cancelled.WaitOne(0)||!ready.WaitOne(0)||Native.Root(Native.GetForegroundWindow())!=hwnd)
                                throw new OperationCanceledException("Copy stopped before clipboard replacement.");
                        });
                        if(RunTransfer.ReadEditor(Resolve(hwnd,target,kind),false)!=sourceText){transfer.Clear();throw new Exception("Copy source changed during verification.");}
                        verified=true;break;
                    case "transfer_copy_button":
                        transfer.Clear();
                        if(!ProductCopyResult.Supports(target)||!e.Current.HelpText.Split('\n').Contains(ProductCopyResult.Ready))
                            throw new Exception("Application Copy source is not ready. No transfer retained.");
                        var dynamicProof=ProductPromptProof.Parse(e.Current.HelpText);
                        if(dynamicProof==null||!e.TryGetCurrentPattern(InvokePattern.Pattern,out pattern))
                            throw new Exception("Application Copy proof or invoke pattern is unavailable.");
                        Check();effectStarted=true;((InvokePattern)pattern).Invoke();
                        var dynamicTarget=new Dictionary<string,object>(target);dynamicTarget["prompt_proof"]=dynamicProof;
                        if(!VerifyResult(hwnd,dynamicTarget,"invoke",null))throw new Exception("Application Copy result was not confirmed. No transfer retained.");
                        string dynamicText=RunTransfer.ClipboardText();
                        if(!ProductPromptProof.Matches(dynamicText,dynamicProof))throw new Exception("Clipboard changed during Copy verification.");
                        transfer.Observe(Convert.ToInt32(((Dictionary<string,object>)action["value"])["slot"]),dynamicText);
                        verified=true;break;
                    case "transfer_paste":
                        string pasteText=transfer.Get(Convert.ToInt32(((Dictionary<string,object>)action["value"])["slot"]));
                        if(!e.TryGetCurrentPattern(ValuePattern.Pattern,out pattern)||((ValuePattern)pattern).Current.IsReadOnly)
                            throw new Exception("Paste destination does not support verified whole-field replacement.");
                        Check();effectStarted=true;((ValuePattern)pattern).SetValue(pasteText);
                        verified=VerifyResult(hwnd,target,"set_text",pasteText);break;
                    case "copy_text":
                        var copied=(Dictionary<string,object>)action["value"];
                        CopyText.ValidateSource(e,copied);
                        Check();
                        if(Native.Root(Native.GetForegroundWindow())!=hwnd)
                            throw new Exception("Focus changed before Copy. Clipboard was not replaced.");
                        effectStarted=true;verified=CopyText.Apply(copied,()=>{
                            // Never wait for Resume while occupying the UI dispatcher.
                            if(cancelled.WaitOne(0)||!ready.WaitOne(0))throw new OperationCanceledException("Copy paused or stopped before clipboard replacement.");
                            if(Native.Root(Native.GetForegroundWindow())!=hwnd)throw new Exception("Copy window lost focus.");
                        });break;
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
                        if(e.Current.ControlType==ControlType.ComboBox) {
                            uint selectedPid;Native.GetWindowThreadProcessId(hwnd,out selectedPid);
                            string value=(string)action["value"];
                            if(DropdownSelection.Selected(e,selectedPid)==value){verified=true;break;}
                            if(!e.TryGetCurrentPattern(ExpandCollapsePattern.Pattern,out pattern))throw new Exception("Dropdown does not expose supported semantic opening. No input sent.");
                            effectStarted=true;((ExpandCollapsePattern)pattern).Expand();
                            AutomationElement option=null;var search=Stopwatch.StartNew();int traversals=0;
                            while(search.ElapsedMilliseconds<Math.Min(timeout,4000)) {
                                Check();if(Native.Root(Native.GetForegroundWindow())!=hwnd)throw new Exception("Focus left the dropdown's owning window.");
                                e=Resolve(hwnd,target,kind);option=DropdownSelection.FindOption(e,selectedPid,value);
                                if(option!=null&&!option.Current.IsOffscreen)break;
                                if(option!=null&&option.TryGetCurrentPattern(ScrollItemPattern.Pattern,out pattern)) {
                                    ((ScrollItemPattern)pattern).ScrollIntoView();Check();
                                }else {
                                    var lists=DropdownSelection.Lists(e,selectedPid);
                                    if(lists.Count>1)throw new Exception("Dropdown scrolling has more than one owned list. No target guessed.");
                                    if(lists.Count==1&&lists[0].TryGetCurrentPattern(ScrollPattern.Pattern,out pattern)) {
                                        var listScroll=(ScrollPattern)pattern;
                                        if(!listScroll.Current.VerticallyScrollable)throw new Exception("Chosen option is unavailable in the bounded dropdown list.");
                                        if(++traversals>32)throw new Exception("Dropdown traversal reached its bounded limit.");
                                        double before=listScroll.Current.VerticalScrollPercent;
                                        listScroll.Scroll(ScrollAmount.NoAmount,ScrollAmount.LargeIncrement);
                                        Check();
                                        if(cancelled.WaitOne(50))Check();
                                        if(Math.Abs(listScroll.Current.VerticalScrollPercent-before)<0.01)
                                            throw new Exception("Dropdown reached its scroll boundary without exposing the chosen option.");
                                    }
                                }
                                if(cancelled.WaitOne(50))Check();
                            }
                            if(option==null||option.Current.IsOffscreen) {
                                try{send("diagnostic",new {kind="dropdown_replay_unavailable",step=step,option_found=option!=null,controls=DropdownSelection.Inspect(hwnd)});}catch{}
                                throw new Exception("Chosen option is not exposed by the owning dropdown. Selection was not guessed.");
                            }
                            if(option.Current.IsOffscreen) {
                                if(!option.TryGetCurrentPattern(ScrollItemPattern.Pattern,out pattern))throw new Exception("Dropdown option cannot be brought into view safely.");
                                ((ScrollItemPattern)pattern).ScrollIntoView();Check();
                            }
                            if(!option.TryGetCurrentPattern(SelectionItemPattern.Pattern,out pattern))throw new Exception("Owned dropdown option is no longer selectable.");
                            ((SelectionItemPattern)pattern).Select();verified=VerifyResult(hwnd,target,kind,value);break;
                        }
                        if(!e.TryGetCurrentPattern(SelectionItemPattern.Pattern,out pattern))throw new Exception("Selection pattern unavailable.");
                        effectStarted=true;((SelectionItemPattern)pattern).Select();verified=VerifyResult(hwnd,target,kind,null);break;
                    case "expand":
                        if(!e.TryGetCurrentPattern(ExpandCollapsePattern.Pattern,out pattern))throw new Exception("Menu expansion pattern unavailable.");
                        var expandable=(ExpandCollapsePattern)pattern;
                        var expansion=(bool)action["value"]?ExpandCollapseState.Expanded:ExpandCollapseState.Collapsed;
                        if(expandable.Current.ExpandCollapseState!=expansion){effectStarted=true;if((bool)action["value"])expandable.Expand();else expandable.Collapse();}
                        verified=VerifyResult(hwnd,target,kind,action["value"]);break;
                    case "scroll":
                        var position=(Dictionary<string,object>)action["value"];
                        double horizontal=Convert.ToDouble(position["horizontal"]),vertical=Convert.ToDouble(position["vertical"]);
                        uint scrollPid;Native.GetWindowThreadProcessId(hwnd,out scrollPid);
                        ScrollAccess scroll=null;var capabilityWait=Stopwatch.StartNew();bool reportedCapabilities=false;
                        while(true) {
                            Check();if(Native.Root(Native.GetForegroundWindow())!=hwnd)throw new Exception("Focus left the verified scroll window. No scrolling sent.");
                            e=Resolve(hwnd,target,kind);scroll=ScrollAccess.Bind(e,scrollPid,horizontal!=-1,vertical!=-1);
                            if(scroll!=null&&scroll.MatchesViewport(position))break;
                            if(!reportedCapabilities) {
                                reportedCapabilities=true;
                                var supported=new List<string>();foreach(var available in e.GetSupportedPatterns())supported.Add(available.ProgrammaticName);
                                send("diagnostic",new {kind="scroll_replay_waiting_for_capability",step=step,
                                    control_type=e.Current.ControlType.ProgrammaticName,automation_id=e.Current.AutomationId,
                                    target_scope_verified=true,process_matches=e.Current.ProcessId==scrollPid,supported_patterns=supported,
                                    viewport_matches=scroll!=null&&scroll.MatchesViewport(position),
                                    observed_vertical_view=scroll==null?null:scroll.VerticalView,
                                    expected_vertical_view=position.ContainsKey("vertical_view_size")?position["vertical_view_size"]:null});
                            }
                            if((Stopwatch.GetTimestamp()-Interlocked.Read(ref started))*1000.0/Stopwatch.Frequency>=timeout)throw new Exception("The recorded scroll container or viewport is not ready. No scrolling sent.");
                            if(cancelled.WaitOne(75))Check();
                        }
                        send("diagnostic",new {kind="scroll_replay_binding",step=step,method=scroll.Method,
                            readiness_wait_ms=capabilityWait.ElapsedMilliseconds,already_at_position=scroll.At(horizontal,vertical),
                            before_horizontal=scroll.Horizontal,before_vertical=scroll.Vertical,before_vertical_view=scroll.VerticalView,
                            desired_horizontal=horizontal,desired_vertical=vertical});
                        if(!scroll.At(horizontal,vertical)){Check();effectStarted=true;scroll.Set(horizontal,vertical);}
                        verified=VerifyResult(hwnd,target,kind,position,target.ContainsKey("selector")?e:null);break;
                    case "invoke":
                        if(!e.TryGetCurrentPattern(InvokePattern.Pattern,out pattern))throw new Exception("Invoke pattern unavailable.");
                        bool productCopy=ProductCopyResult.Supports(target);
                        if(productCopy&&target.ContainsKey("prompt_proof")&&
                            !ProductPromptProof.Same((Dictionary<string,object>)target["prompt_proof"],ProductPromptProof.Parse(e.Current.HelpText)))
                            throw new Exception("The complete prompt differs from the saved workflow. No input sent.");
                        if(productCopy&&!e.Current.HelpText.Split('\n').Contains(ProductCopyResult.Ready))
                            throw new Exception("Copy prompt readiness changed. No input sent.");
                        bool productGenerate=ProductGenerationResult.Supports(target);
                        bool productPicker=ProductPickerResult.Supports(target);
                        bool modalButton=DialogResult.Supports(target);
                        if(modalButton&&!DialogResult.IsModal(Resolve(hwnd,DialogResult.Target(target),"wait_ready")))
                            throw new Exception("The recorded modal dialog is not ready. No input sent.");
                        uint pickerPid;Native.GetWindowThreadProcessId(hwnd,out pickerPid);
                        var pickerDocument=productPicker?ProductPickerResult.Document(e,hwnd,pickerPid):null;
                        if(productPicker&&(pickerDocument==null||ProductPickerResult.Open(pickerDocument,hwnd,pickerPid)))
                            throw new Exception("Close the PSD picker before Play. No input sent.");
                        var generationBefore=productGenerate?GenerationWitness(hwnd,target):null;
                        if(productGenerate&&generationBefore==null)
                            throw new Exception("Prepare Product Uploads generation before Play. No input sent.");
                        if(productGenerate&&generationBefore.State!="idle")
                            throw new Exception("Generation is already "+generationBefore.State+". Inspect or restore the supported starting state; Generate was not invoked.");
                        effectStarted=true;((InvokePattern)pattern).Invoke();
                        // Provider return is not application result verification.
                        if(productCopy)verified=VerifyResult(hwnd,target,kind,null);
                        else if(productPicker){verified=VerifyPicker(hwnd,pickerDocument);if(!verified)reason="PSD picker did not open. Choose PSD was not repeated.";}
                        else if(modalButton){verified=VerifyDialogClosed(hwnd,target);if(!verified)reason="The containing dialog did not close. Action was not repeated.";}
                        else if(productGenerate){verified=VerifyGeneration(hwnd,target,generationBefore);
                            if(!verified)reason="Generation acknowledgement was not observed within the action timeout. Generate was not repeated.";}
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
