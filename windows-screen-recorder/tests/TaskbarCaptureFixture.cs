using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Interop;
using System.Web.Script.Serialization;

// Local test-only UI: production executor drives real shell gestures while
// production capture hooks observe them. Never copies seed actions into output.
class TaskbarCaptureFixture : Window {
    readonly JavaScriptSerializer json=new JavaScriptSerializer();
    readonly List<object> events=new List<object>();
    readonly string output;readonly object[] actions;
    readonly TextBlock status=new TextBlock{Text="Idle — injected-input capture test",Margin=new Thickness(12)};
    readonly AutoResetEvent captured=new AutoResetEvent(false);
    Capture capture;volatile bool stopped;int observed;
    TaskbarCaptureFixture(string seed,string output) {
        this.output=output;
        var task=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(seed));
        actions=((ArrayList)task["actions"]).Cast<object>().ToArray();
        if(actions.Length!=3||actions.Cast<Dictionary<string,object>>().Any(a=>(string)a["kind"]!="taskbar_activate"))throw new Exception("Expected three reviewed taskbar actions.");
        Title="Recorder taskbar capture fixture — local test";Width=520;Height=200;Topmost=true;
        var panel=new StackPanel();panel.Children.Add(status);
        var start=new Button{Content="Capture reviewed shell sequence",Margin=new Thickness(12)};
        start.Click+=(s,e)=>{start.IsEnabled=false;capture.PrepareRecord(IntPtr.Zero,true);};panel.Children.Add(start);
        var stop=new Button{Content="Stop test",Margin=new Thickness(12)};
        stop.Click+=(s,e)=>{stopped=true;capture.Barrier("fixture_done");};panel.Children.Add(stop);Content=panel;
        SourceInitialized+=(s,e)=>capture=new Capture(new WindowInteropHelper(this).Handle,Event,reason=>{stopped=true;Event("failure",new {reason=reason});Dispatcher.BeginInvoke(new Action(()=>capture.Barrier("fixture_done")));},true);
        Closed+=(s,e)=>{stopped=true;if(capture!=null)capture.Detach();};
    }
    void Event(string kind,object value) {
        lock(events){events.Add(new {kind=kind,value=value});}
        if(kind=="record")Dispatcher.BeginInvoke(new Action(()=>{
            capture.Start(1);status.Text="Capturing actual injected shell gestures…";
            var worker=new Thread(Run){IsBackground=true};worker.SetApartmentState(ApartmentState.MTA);worker.Start();
        }));
        if(kind=="event"){Interlocked.Increment(ref observed);captured.Set();}
        if(kind=="fixture_done"){
            lock(events)File.WriteAllText(output,json.Serialize(new {injected_test_input=true,observed_actions=observed,events=events}));
            Dispatcher.BeginInvoke(new Action(()=>status.Text="Stopped. Captured actions: "+observed+". Evidence saved."));
        }
    }
    void Check(){if(stopped||capture.Broken)throw new OperationCanceledException();}
    void Run() {
        try {
            // Give the asynchronous production shell preflight its normal budget.
            Thread.Sleep(750);
            foreach(Dictionary<string,object> action in actions) {
                Check();var target=(Dictionary<string,object>)action["target"];
                var matches=new List<IntPtr>();
                Native.EnumWindows((h,l)=>{
                    if(Native.IsWindowVisible(h)&&Native.Title(h)==(string)target["window_key"])
                        try{if(String.Equals(Native.ProcessFor(h).MainModule.FileName,(string)target["app"],StringComparison.OrdinalIgnoreCase))matches.Add(h);}catch{}
                    return true;
                },IntPtr.Zero);
                if(matches.Count!=1)throw new Exception("Fixture destination is absent or ambiguous.");
                var destination=matches[0];
                Action verify=()=>{Check();if(Native.Title(destination)!=(string)target["window_key"])throw new Exception("Fixture destination changed.");
                    if(target.ContainsKey("browser")&&!BrowserIdentity.SamePage(BrowserIdentity.Current(destination),(Dictionary<string,object>)target["browser"]))throw new Exception("Fixture browser scope changed.");};
                int before=observed;
                TaskbarRoute.Play((Dictionary<string,object>)action["value"],destination,Check,verify,()=>{});
                if(!captured.WaitOne(5000)||observed!=before+1)throw new Exception("Actual hook capture did not produce exactly one action.");
            }
        }catch(Exception error){Event("driver_failure",new {reason=error.Message});}
        finally{Dispatcher.BeginInvoke(new Action(()=>capture.Barrier("fixture_done")));}
    }
    [STAThread] public static void Main(string[] args) {
        if(args.Length!=2)throw new Exception("Seed and isolated evidence path required.");
        new Application().Run(new TaskbarCaptureFixture(args[0],args[1]));
    }
}

