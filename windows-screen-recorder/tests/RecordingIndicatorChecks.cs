using System;
using System.Runtime.InteropServices;
using System.Web.Script.Serialization;
using System.Collections;
class RecordingIndicatorChecks {
    [DllImport("user32.dll")] static extern bool SetProcessDpiAwarenessContext(IntPtr value);
    [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    static void Check(bool value,string reason){if(!value)throw new Exception(reason);}
    [STAThread] static int Main(){
        SetProcessDpiAwarenessContext(new IntPtr(-4));
        var json=new JavaScriptSerializer();
        Check(RecordingIndicator.Mode("idle",false,false,true,false)=="","Idle must have no border");
        Check(RecordingIndicator.Mode("playing",true,false,true,false)=="","Unarmed playback must have no border");
        Check(RecordingIndicator.Mode("recording",false,false,false,false)=="","Disconnected must have no border");
        Check(RecordingIndicator.Mode("recording",false,false,true,true)=="Stopping","Flush must be distinct");
        Check(RecordingIndicator.Mode("paused",false,false,true,false)=="Paused","Pause indication");
        Check(RecordingIndicator.Mode("playing",false,true,true,false)=="Playback paused","Playback pause indication");
        var before=GetForegroundWindow();
        using(var indicator=new RecordingIndicator()){
            foreach(var mode in new[]{"Recording","Paused","Recording","Stopping","Playback","Playback paused"}){
                indicator.Update(mode,"00:00:02");
                Check(GetForegroundWindow()==before,"Indicator stole focus");
                var snapshot=indicator.Snapshot();Check(snapshot.Length>0,"No displays found");
                foreach(var item in snapshot){
                    var row=json.DeserializeObject(json.Serialize(item)) as System.Collections.Generic.Dictionary<string,object>;
                    Check((bool)row["click_through"]&&(bool)row["no_activate"]&&(bool)row["visible"],"Unsafe indicator window styles");
                    Check((bool)row["capture_excluded"],"Indicator not excluded from capture");
                    Check(Convert.ToDouble(row["content_width"])>100&&Convert.ToDouble(row["content_height"])>100,"Border content did not fill the display");
                    var rect=(object[])row["rect"];Check(Convert.ToInt32(rect[2])>Convert.ToInt32(rect[0])&&Convert.ToInt32(rect[3])>Convert.ToInt32(rect[1]),"Bad display bounds");
                    Check(((string)row["label"]).StartsWith(mode),"Wrong lifecycle label");
                }
                Console.WriteLine(json.Serialize(snapshot));
            }
            indicator.Update("","");Check(indicator.Snapshot().Length==0,"Idle retained indicator windows");
        }
        Console.WriteLine("PASS: native indicator lifecycle, focus, display bounds, window styles, and screen capture exclusion");return 0;
    }
}
