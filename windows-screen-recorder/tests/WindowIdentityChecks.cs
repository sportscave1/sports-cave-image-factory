using System;
class WindowIdentityChecks {
    static void Require(bool condition,string name){if(!condition)throw new Exception(name);}
    static void Main(){
        var edge=new IntPtr(100);var childRoot=new IntPtr(200);var otherApp=new IntPtr(300);
        Require(WindowIdentity.InitialMatches(edge,WindowIdentity.Root(childRoot,edge,7,7)),"same-process owned popup must resolve to selected root");
        Require(!WindowIdentity.InitialMatches(edge,WindowIdentity.Root(childRoot,edge,8,7)),"different-process owner must not defeat window validation");
        Require(!WindowIdentity.InitialMatches(edge,otherApp),"another window must still be rejected");
        Require(WindowIdentity.IsToolbar(42,42),"toolbar hit is excluded regardless of foreground state");
        Require(!WindowIdentity.IsToolbar(7,42),"application hit is not excluded because toolbar was previously foreground");
        Require(WindowIdentity.InitialMatches(IntPtr.Zero,otherApp),"supported cross-window capture after initial context is accepted");
        Console.WriteLine("PASS 6 native window-identity policy checks (no desktop input)");
    }
}
