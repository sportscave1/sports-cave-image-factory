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

partial class Capture {
    public bool DesktopSession {get;private set;}
    DesktopWindowState.EventCallback sessionCallback;
    IntPtr sessionHook;
    long physicalTransitionTick=-1;
    IntPtr mouseDownWindow;
    string mouseDownState;
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
        if(!Armed||Broken||!DesktopSession||window==IntPtr.Zero||objectId!=0||childId!=0||(kind!=3&&kind!=0x16&&kind!=0x17))return;
        long physical=Interlocked.Read(ref physicalTransitionTick);
        // OS foreground events alone cannot establish physical input. Injected
        // input never grants this ticket. No input values are read here.
        if(physical<0||!DesktopWindowState.InGesture(time,(uint)physical))return;
        window=Native.Root(window);
        if(Mine(window)||Native.IsTaskbar(window)||!Native.IsWindow(window))return;
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
        });
    }
    void FlushForTransition() {
        if(dropdown!=null)PollDropdown(true,true);
        Flush();editorAnchor=null;editorAnchorTarget=null;
    }
    Dictionary<string,object> WindowTarget(IntPtr window) {
        Native.CheckProcess(window);
        string title=Safe(Native.Title(window));
        if(title.Length==0)throw new Exception("Desktop transition has no durable window identity.");
        return new Dictionary<string,object>{{"app",Native.ProcessFor(window).MainModule.FileName},{"window_key",title},
            {"control_type","Window"},{"automation_id","window"},{"name",title},{"scope",new List<object>()}};
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
        if(after==before)return false;
        FlushForTransition();RecordWindowState(down,after,epoch);return true;
    }
}
