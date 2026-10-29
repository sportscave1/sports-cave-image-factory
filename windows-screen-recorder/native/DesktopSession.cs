using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Automation;

static class DesktopWindowState {
    public delegate void EventCallback(IntPtr hook,uint kind,IntPtr window,int objectId,int childId,uint thread,uint time);
    [DllImport("user32.dll")] public static extern IntPtr SetWinEventHook(uint min,uint max,IntPtr module,EventCallback callback,uint process,uint thread,uint flags);
    [DllImport("user32.dll")] public static extern bool UnhookWinEvent(IntPtr hook);
    [DllImport("user32.dll")] static extern bool IsIconic(IntPtr window);
    [DllImport("user32.dll")] static extern bool IsZoomed(IntPtr window);
    [DllImport("user32.dll")] static extern bool ShowWindowAsync(IntPtr window,int command);
    public static string Read(IntPtr window){return IsIconic(window)?"minimized":IsZoomed(window)?"maximized":"normal";}
    public static bool InGesture(uint observed,uint physical) {return unchecked(observed-physical)<=1500;}
    public static void Restore(IntPtr window,Action check) {
        check();Native.CheckProcess(window);
        if(Read(window)!="minimized")return;
        if(!ShowWindowAsync(window,9))throw new Exception("Windows refused to restore the recorded window.");
        var watch=Stopwatch.StartNew();
        while(watch.ElapsedMilliseconds<1500){check();if(Read(window)!="minimized")return;Thread.Sleep(20);}
        throw new Exception("The recorded window remained minimized.");
    }
    public static void Apply(IntPtr window,string desired,Action check) {
        if(desired!="normal"&&desired!="minimized"&&desired!="maximized")throw new Exception("Unsupported window state.");
        check();Native.CheckProcess(window);
        if(Read(window)==desired)return;
        if(!ShowWindowAsync(window,desired=="minimized"?6:desired=="maximized"?3:9))
            throw new Exception("Windows refused the recorded window transition.");
        var watch=Stopwatch.StartNew();
        while(watch.ElapsedMilliseconds<1500){check();if(Read(window)==desired)return;Thread.Sleep(20);}
        throw new Exception("The recorded window state was not reached.");
    }
}

// Foreground notifications can be queued before the Save As window has its
// final title. Retain the later, independently verified owned-dialog identity
// until its receipt wait ends. This applies only to metadata notifications;
// physical mouse/key work never uses this exemption.
sealed class DownloadDialogNotifications {
    IntPtr dialog,owner;int epoch;long observed,completed;bool active;
    public void Clear(){dialog=owner=IntPtr.Zero;active=false;}
    public void Observe(IntPtr modal,IntPtr browser,int generation,long at) {
        if(modal==IntPtr.Zero||browser==IntPtr.Zero||modal==browser)throw new ArgumentException("Invalid owned dialog observation.");
        dialog=modal;owner=browser;epoch=generation;observed=at;completed=0;active=true;
    }
    public bool IsObserved(IntPtr modal,IntPtr browser,int generation){return active&&dialog==modal&&owner==browser&&epoch==generation;}
    public void Complete(long at){if(active){completed=at;active=false;}}
    public bool Matches(IntPtr modal,IntPtr browser,int generation,long queuedAt) {
        return dialog!=IntPtr.Zero&&dialog==modal&&owner==browser&&epoch==generation&&
            queuedAt>=observed-1500&&(active||queuedAt<=completed);
    }
}

partial class Capture {
    readonly DownloadDialogNotifications downloadDialogNotifications=new DownloadDialogNotifications();
    public bool DesktopSession {get;private set;}
    DesktopWindowState.EventCallback sessionCallback;
    IntPtr sessionHook;
    long physicalTransitionTick=-1;
    IntPtr mouseDownWindow;
    string mouseDownState;
    readonly WindowMoveGesture moveGesture=new WindowMoveGesture();
    readonly Dictionary<IntPtr,string> sessionStates=new Dictionary<IntPtr,string>();
    void ArmSession() {
        if(!DesktopSession)return;
        Interlocked.Exchange(ref physicalTransitionTick,-1);
        sessionStates.Clear();
        sessionCallback=SessionEvent;
        sessionHook=DesktopWindowState.SetWinEventHook(3,0x17,IntPtr.Zero,sessionCallback,0,0,2); // out-of-context, skip own process
        if(sessionHook==IntPtr.Zero)throw new Exception("Desktop-session transition observation is unavailable.");
    }
    void DisarmSession() {
        if(sessionHook!=IntPtr.Zero)DesktopWindowState.UnhookWinEvent(sessionHook);
        sessionHook=IntPtr.Zero;
        Interlocked.Exchange(ref physicalTransitionTick,-1);
    }
    void PhysicalTransition(uint tick) {if(DesktopSession)Interlocked.Exchange(ref physicalTransitionTick,tick);}
    void SessionEvent(IntPtr hook,uint kind,IntPtr window,int objectId,int childId,uint thread,uint time) {
        if(!Armed||Broken||!DesktopSession||window==IntPtr.Zero||objectId!=0||childId!=0||(kind!=3&&kind!=0xA&&kind!=0x16&&kind!=0x17))return;
        long physical=Interlocked.Read(ref physicalTransitionTick);
        // OS foreground events alone cannot establish physical input. Injected
        // input never grants this ticket. No input values are read here.
        if(physical<0||!DesktopWindowState.InGesture(time,(uint)physical))return;
        var eventWindow=window;var eventOwner=Native.GetAncestor(window,3);long queuedAt=MonotonicMs();
        window=Native.Root(window);
        if(shellGesture||Mine(window)||TaskbarRoute.Surface(window)||!Native.IsWindow(window))return;
        if(kind==0xA){moveGesture.Observe(window,generation,time);return;}
        // Preserve the event-time owned-modal relationship before the dialog closes.
        // Only a foreground notification for the already captured browser or its
        // verified Save As modal can be redundant after the receipt wait.
        var owner=Native.GetAncestor(window,3);
        bool saveDialog=kind==3&&BrowserDownload.OwnedSaveDialog(window,owner);
        string state=kind==0x16?"minimized":DesktopWindowState.Read(window);int epoch=generation;
        Put(()=>{
            if(Broken||epoch!=generation)return;
            observedWindow=window;captureOperation="desktop window transition";
            Native.CheckProcess(window);
            if(kind==0x16||kind==0x17) {
                FlushForTransition();RecordWindowState(window,state,epoch);
            } else if(window!=lastWindow) {
                FlushForTransition();
                // A minimize event can arrive after the foreground notification.
                // Preserve its observed effect before activating the next app.
                if(lastWindow!=IntPtr.Zero&&Native.IsWindow(lastWindow)&&DesktopWindowState.Read(lastWindow)=="minimized")
                    RecordWindowState(lastWindow,"minimized",epoch);
                WindowAction(window,epoch);AnchorFocusedEditor(window);
            }
        },()=>epoch==generation&&kind==3&&(window==lastWindow||(saveDialog&&owner==lastWindow)||
            downloadDialogNotifications.Matches(eventWindow,eventOwner,epoch,queuedAt)));
    }
    void FlushForTransition() {
        if(dropdown!=null)PollDropdown(true,true);
        Flush();editorAnchor=null;editorAnchorTarget=null;
    }
    Dictionary<string,object> WindowTarget(IntPtr window) {
        Native.CheckProcess(window);
        string title=Safe(Native.Title(window));
        Dictionary<string,object> browser=null;
        if(BrowserTabs.Chromium(window)) {
            // Caption updates (including Streamlit's temporary title) are not
            // a page identity. Reuse only a page witnessed in this capture and
            // this exact window/process; replay validates it independently.
            if(window==lastWindow&&lastBrowser!=null) {
                browser=lastBrowser;title=lastTitle;
            } else {
                BrowserWindowContext previous;uint pid;Native.GetWindowThreadProcessId(window,out pid);
                if(browserWindowContexts.TryGetValue(window,out previous)&&previous.Pid==pid) {
                    browser=previous.Browser;title=previous.Title;
                }
            }
            if(browser==null)throw new Exception("Record an action on the browser page before changing its window state. Draft preserved.");
        }
        if(title.Length==0)throw new Exception("Desktop transition has no durable window identity.");
        var target=new Dictionary<string,object>{{"app",Native.ProcessFor(window).MainModule.FileName},{"window_key",title},
            {"control_type","Window"},{"automation_id","window"},{"name",title},{"scope",new List<object>()}};
        if(browser!=null) {
            var identity=new Dictionary<string,object>(browser);identity["control"]="document";identity["frame"]="top";
            target["browser"]=identity;
        }
        return target;
    }
    void RecordWindowState(IntPtr window,string state,int epoch) {
        string previous;if(sessionStates.TryGetValue(window,out previous)&&previous==state)return;
        Emit("window_state",WindowTarget(window),state,epoch);sessionStates[window]=state;
        send("diagnostic",new {kind="desktop_window_state",state=state,physical_transition=true});
    }
    bool CompleteWindowGesture(int epoch) {
        var down=mouseDownWindow;var before=mouseDownState;mouseDownWindow=IntPtr.Zero;mouseDownState=null;
        if(!DesktopSession||down==IntPtr.Zero||before==null||!Native.IsWindow(down)||Native.IsTaskbar(down))return false;
        string after=DesktopWindowState.Read(down);
        if(before==after)return false;
        Put(()=>{if(epoch==generation&&!Broken){FlushForTransition();RecordWindowState(down,after,epoch);}});
        return true;
    }
    // Windows may apply a caption-button transition after the low-level mouse-up
    // hook returns. Reconcile the same gesture on the capture worker before
    // resolving its old screen point against the newly exposed application.
    bool CompleteObservedWindowGesture(IntPtr down,string before,int epoch) {
        if(!DesktopSession||Broken||epoch!=generation||down==IntPtr.Zero||before==null||!Native.IsWindow(down)||Native.IsTaskbar(down))return false;
        string after=DesktopWindowState.Read(down);
        if(after==before&&moveGesture.Matches(down,epoch)) {
            if(Native.Root(Native.GetForegroundWindow())!=down)
                throw new Exception("Window focus changed during move or resize. Draft preserved.");
            Native.CheckProcess(down);FlushForTransition();WindowAction(down,epoch);
            send("diagnostic",new {kind="window_move_resize",physical_transition=true,resolution="Windows move/resize-start matched the input window and recording generation"});
            return true;
        }
        if(after==before)return false;
        FlushForTransition();RecordWindowState(down,after,epoch);return true;
    }
}
