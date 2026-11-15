using System;
using System.Windows;

static class EditorClickTarget {
    // Both rectangles and hook points are physical screen coordinates. Never
    // scale, enlarge, or accept a nearby unrelated label to manufacture a hit.
    public static bool Matches(Point point,Rect editor,Rect label,bool labelValidated) {
        return (!editor.IsEmpty&&editor.Contains(point))||
            (labelValidated&&!label.IsEmpty&&label.Contains(point));
    }
}

// A click is never discarded merely because Chromium publishes focus late.
// It must resolve in its original window/generation, or capture must interrupt.
sealed class PendingEditorClick {
    public bool Active {get;private set;}
    public IntPtr Window {get;private set;}
    public int X {get;private set;}
    public int Y {get;private set;}
    int generation;
    long observed;
    public void Begin(IntPtr window,int x,int y,int epoch,long now) {
        if(Active)throw new InvalidOperationException("The previous click has not been classified.");
        Window=window;X=x;Y=y;generation=epoch;observed=now;Active=true;
    }
    public bool CanResolve(IntPtr window,int epoch,long now) {
        return Active&&Window==window&&generation==epoch&&now>=observed&&now-observed<=2000;
    }
    public void Clear(){Active=false;}
}
