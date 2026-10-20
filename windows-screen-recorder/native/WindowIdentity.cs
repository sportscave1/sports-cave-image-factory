using System;

static class WindowIdentity {
    // Child windows resolve to their top-level root. Owned popups may resolve
    // to the same-process owner, but never cross an application boundary.
    public static IntPtr Root(IntPtr root,IntPtr owner,uint rootPid,uint ownerPid) {
        return owner!=IntPtr.Zero&&ownerPid==rootPid?owner:root;
    }
    public static bool InitialMatches(IntPtr prepared,IntPtr actual) {
        return prepared==IntPtr.Zero||prepared==actual;
    }
    public static bool IsToolbar(uint inputPid,uint hostPid) {return inputPid==hostPid;}
}
