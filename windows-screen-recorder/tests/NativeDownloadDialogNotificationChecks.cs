using System;
class NativeDownloadDialogNotificationChecks {
    static int count;
    static void Check(bool value){count++;if(!value)throw new Exception("Owned download notification guard failed");}
    static int Main(){
        var n=new DownloadDialogNotifications();var modal=new IntPtr(20);var owner=new IntPtr(10);
        Check(!n.Matches(modal,owner,1,1000));
        n.Observe(modal,owner,1,2000);
        Check(n.Matches(modal,owner,1,1500)); // early foreground before final dialog title
        Check(!n.Matches(modal,owner,1,499));
        Check(!n.Matches(new IntPtr(30),owner,1,1500));
        Check(!n.Matches(modal,new IntPtr(30),1,1500));
        Check(!n.Matches(modal,owner,2,1500));
        Check(n.IsObserved(modal,owner,1));
        n.Complete(100000);
        Check(n.Matches(modal,owner,1,2000)); // receipt wait may outlast ordinary input deadline
        Check(!n.Matches(modal,owner,1,100001)); // handle reuse/later event is not covered
        Check(!n.IsObserved(modal,owner,1));
        n.Clear();Check(!n.Matches(modal,owner,1,2000));
        bool rejected=false;try{n.Observe(owner,owner,2,2000);}catch(ArgumentException){rejected=true;}Check(rejected);
        Console.WriteLine("PASS "+count+" owned-dialog notification guards; no input automation.");return 0;
    }
}
