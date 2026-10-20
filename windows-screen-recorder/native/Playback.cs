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
    }
    IntPtr Intervention(int code,IntPtr message,IntPtr data) {
        if(code>=0&&Active) {
            uint pid; Native.GetWindowThreadProcessId(Native.GetForegroundWindow(),out pid);
            // Movement does not cancel, but clicks, wheel and keyboard intervention do.
            if(pid!=Process.GetCurrentProcess().Id&&message.ToInt32()!=0x200){
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
        var parent=TreeWalker.ControlViewWalker.GetParent(e);
        for(int depth=0;parent!=null&&depth<16;depth++){
            if(parent.Current.NativeWindowHandle==hwnd.ToInt32())return index==expected.Count;
            if(parent.Current.AutomationId.Length>0||parent.Current.Name.Length>0){
                if(index>=expected.Count||!Match(parent,(Dictionary<string,object>)expected[index]))return false;
                index++;
            }
            parent=TreeWalker.ControlViewWalker.GetParent(parent);
        }
        return false;
    }
    IntPtr Window(Dictionary<string,object> target) {
        var matches=new List<IntPtr>();
        Native.EnumWindows((h,l)=>{
            if(Native.IsWindowVisible(h)&&Native.Title(h)==(string)target["window_key"]){
                try{Native.CheckProcess(h);if(String.Equals(Native.ProcessFor(h).MainModule.FileName,(string)target["app"],StringComparison.OrdinalIgnoreCase))matches.Add(h);}catch{}
            }return true;
        },IntPtr.Zero);
        if(matches.Count!=1)throw new Exception(matches.Count==0?"Prepare the recorded window before Play.":"More than one matching window is open. Close the ambiguity before Play.");
        return matches[0];
    }
    static void Privacy(AutomationElement e) {
        object value=e.GetCurrentPropertyValue(AutomationElement.IsPasswordProperty,true);
        if(!(value is bool)||(bool)value)throw new Exception("Protected or unclassified target. Playback refused.");
        if(!e.Current.IsEnabled||e.Current.IsOffscreen)throw new Exception("Target is not ready.");
    }
    AutomationElement Resolve(IntPtr hwnd,Dictionary<string,object> target,string kind) {
        var root=AutomationElement.FromHandle(hwnd);
        if(kind=="focus_window")return root;
        var condition=new AndCondition(
            new PropertyCondition(AutomationElement.AutomationIdProperty,(string)target["automation_id"]),
            new PropertyCondition(AutomationElement.NameProperty,(string)target["name"]));
        var matches=root.FindAll(TreeScope.Descendants,condition);
        AutomationElement found=null;int count=0;
        for(int i=0;i<matches.Count;i++)if(Match(matches[i],target)&&ScopeMatches(matches[i],hwnd,target)){found=matches[i];count++;}
        if(count!=1)throw new Exception(count==0?"Recorded control is not ready.":"Recorded control is ambiguous. No input sent.");
        Privacy(found);return found;
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
            var current=Resolve(hwnd,target,kind);object pattern;
            if(kind=="set_text"&&current.TryGetCurrentPattern(ValuePattern.Pattern,out pattern)
                &&((ValuePattern)pattern).Current.Value==(string)expected)return true;
            if(kind=="toggle"&&current.TryGetCurrentPattern(TogglePattern.Pattern,out pattern)
                &&((TogglePattern)pattern).Current.ToggleState==((bool)expected?ToggleState.On:ToggleState.Off))return true;
            if(kind=="select"&&current.TryGetCurrentPattern(SelectionItemPattern.Pattern,out pattern)
                &&((SelectionItemPattern)pattern).Current.IsSelected)return true;
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
            try {
                Check();
                var target=(Dictionary<string,object>)action["target"];
                string kind=(string)action["kind"];
                AutomationElement e=null;IntPtr hwnd=IntPtr.Zero;
                while(true){
                    Check();
                    try {hwnd=Window(target);e=Resolve(hwnd,target,kind);break;}
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
                    case "invoke":
                        if(!e.TryGetCurrentPattern(InvokePattern.Pattern,out pattern))throw new Exception("Invoke pattern unavailable.");
                        effectStarted=true;((InvokePattern)pattern).Invoke();
                        // Provider return is not application result verification.
                        reason="Button invoked; its application result needs verification before continuing.";break;
                    default:throw new Exception("Unsupported desktop action.");
                }
                if(!verified&&reason.Length==0)reason="The expected control result was not observed within 2 seconds. Action was not repeated.";
                Check();
            }catch(Exception ex){reason=ex.Message;verified=false;}
            finally{busy=false;if(Interlocked.Exchange(ref resultSent,1)==0)send("play_result",new {step=step,verified=verified,no_effect=!effectStarted,message=reason});}
        }){IsBackground=true};
        worker.SetApartmentState(ApartmentState.MTA);worker.Start();
    }
}
