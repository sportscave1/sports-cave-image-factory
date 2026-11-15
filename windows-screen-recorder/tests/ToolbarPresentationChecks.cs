using System;
class ToolbarPresentationChecks {
    static int count;
    static void Check(bool value){count++;if(!value)throw new Exception("Popup policy failed at "+count);}
    static int Main(){
        foreach(string state in new[]{"recording","paused","playing"}){
            Check(ToolbarPresentation.CanControl(state,"Stop",true,true));
            Check(!ToolbarPresentation.CanControl(state,"Resume",true,true));
            Check(!ToolbarPresentation.CanStart(state,false,true));
        }
        Check(ToolbarPresentation.CanStart("idle",false,true));
        Check(!ToolbarPresentation.CanStart("idle",true,true));
        Check(!ToolbarPresentation.CanStart("idle",false,false));
        Check(!ToolbarPresentation.CanControl("recording","Stop",false,false));
        Check(ToolbarPresentation.Label("draft",false,false,"save",true)=="Saving…");
        Check(ToolbarPresentation.Label("playing",true,false,"",true)=="Ready to play");
        Check(ToolbarPresentation.Label("playing",false,true,"",true)=="Paused");
        Check(ToolbarPresentation.Label("interrupted",false,false,"",true)=="Recording interrupted");
        Check(ToolbarPresentation.Label("recording",false,false,"",false)=="Disconnected");
        Console.WriteLine("PASS "+count+" popup control policies; no Windows input or inspection.");return 0;
    }
}
