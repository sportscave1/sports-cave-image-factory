using System;
class WindowIdentityChecks {
    static int checks;
    static void Require(bool condition,string name){checks++;if(!condition)throw new Exception(name);}
    static void Main(){
        var edge=new IntPtr(100);var childRoot=new IntPtr(200);var otherApp=new IntPtr(300);
        Require(WindowIdentity.InitialMatches(edge,WindowIdentity.Root(childRoot,edge,7,7)),"same-process owned popup must resolve to selected root");
        Require(!WindowIdentity.InitialMatches(edge,WindowIdentity.Root(childRoot,edge,8,7)),"different-process owner must not defeat window validation");
        Require(!WindowIdentity.InitialMatches(edge,otherApp),"another window must still be rejected");
        Require(WindowIdentity.IsToolbar(42,42),"toolbar hit is excluded regardless of foreground state");
        Require(!WindowIdentity.IsToolbar(7,42),"application hit is not excluded because toolbar was previously foreground");
        Require(WindowIdentity.InitialMatches(IntPtr.Zero,otherApp),"supported cross-window capture after initial context is accepted");
        string app=@"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe";
        string suffix=" - Personal - Microsoft\u200b Edge";
        string recorded="Recorder controls acceptance and 2 more pages"+suffix;
        Require(WindowIdentity.PlaybackTitleMatches(app,recorded,"Recorder controls acceptance and 3 more pages"+suffix,
            page=>page=="Recorder controls acceptance"),"changed tab count requires independent exact page identity");
        Require(WindowIdentity.PlaybackTitleMatches(app,recorded,"Recorder controls acceptance"+suffix,page=>true),"a single tab can match the same independently identified page");
        Require(WindowIdentity.PlaybackTitleMatches(app,"Recorder controls acceptance and 1 more page"+suffix,recorded,page=>true),"singular tab decoration is supported");
        Require(WindowIdentity.PlaybackTitleMatches(app,recorded,recorded,page=>{throw new Exception("Exact match must retain the existing path");}),"exact identity retains existing behavior");
        Require(!WindowIdentity.PlaybackTitleMatches(app,recorded,"Recorder controls acceptance and 3 more pages"+suffix,page=>false),"title normalization never substitutes for document validation");
        Require(!WindowIdentity.PlaybackTitleMatches(app,recorded,"Other page and 3 more pages"+suffix,page=>{throw new Exception("Wrong page must not be probed");}),"another page is rejected before document lookup");
        Require(!WindowIdentity.PlaybackTitleMatches(app,recorded,"Recorder controls acceptance and 3 more pages - Work - Microsoft\u200b Edge",page=>true),"another browser profile is rejected");
        Require(!WindowIdentity.PlaybackTitleMatches(@"C:\Other\notepad.exe",recorded,"Recorder controls acceptance and 3 more pages"+suffix,page=>true),"other applications retain exact title matching");
        Require(!WindowIdentity.PlaybackTitleMatches(app,recorded,"Recorder controls acceptance and 0 more pages"+suffix,page=>true),"unsupported tab decoration is not removed");
        Require(!WindowIdentity.PlaybackTitleMatches(app,recorded,"Recorder controls acceptance and 03 more pages"+suffix,page=>true),"leading-zero decorations are not guessed");
        Require(!WindowIdentity.PlaybackTitleMatches(app,recorded,"Recorder controls acceptance and 3 more pages - Personal - Microsoft Edge",page=>true),"other title decorations remain exact");
        Require(!WindowIdentity.PlaybackTitleMatches(app,recorded,"Recorder controls acceptance and 3 more pages"+suffix+"\n",page=>true),"unclassified titles remain rejected");
        Console.WriteLine("PASS "+checks+" native window-identity policy checks (no desktop input)");
    }
}
