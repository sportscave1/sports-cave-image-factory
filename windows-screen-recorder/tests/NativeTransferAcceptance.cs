using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Web.Script.Serialization;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Interop;
using System.Windows.Threading;

// Exercises the real executor against this disposable application's own UI.
// No user applications are targeted; source content never enters flow.json.
class NativeTransferAcceptance {
    static JavaScriptSerializer json=new JavaScriptSerializer();
    static DesktopPlayback playback;static Window window;static TextBox source,destination;
    static ArrayList actions;static string expected,folder;static int step;static bool finished;
    static Dictionary<string,object> Action(string kind,string id,string name) {
        return new Dictionary<string,object>{{"version",3},{"kind",kind},{"requires",new[]{kind=="transfer_copy"?"transfer.editor-copy.v3":"transfer.paste.v3"}},
            {"target",new Dictionary<string,object>{{"app",System.Diagnostics.Process.GetCurrentProcess().MainModule.FileName},
                {"window_key","Disposable transfer acceptance"},{"control_type","Edit"},{"automation_id",id},{"name",name},{"scope",new object[0]}}},
            {"timeout_ms",8000},{"value",new Dictionary<string,object>{{"slot",0},{"mode",kind=="transfer_copy"?"whole_text":"replace_all"}}}};
    }
    static void Finish(bool ok,string message) {
        if(finished)return;finished=true;if(playback!=null)playback.Disarm();
        File.WriteAllText(Path.Combine(folder,"result.json"),json.Serialize(new {passed=ok,message=message,
            source_units=expected.Length,source_sha256=CopyText.Hash(expected),steps=step}));
        Console.WriteLine(ok?"Native dynamic transfer passed":"Native dynamic transfer FAILED: "+message);
        Application.Current.Shutdown(ok?0:1);
    }
    [STAThread] static int Main(string[] args) {
        folder=args[0];Directory.CreateDirectory(folder);expected=File.ReadAllText(args[1]);
        var app=new Application();var panel=new StackPanel{Margin=new Thickness(20)};
        panel.Children.Add(new TextBlock{Text="Disposable local transfer acceptance"});
        source=new TextBox{Text=expected,AcceptsReturn=true,Height=110};destination=new TextBox{Text="",AcceptsReturn=true,Height=110};
        AutomationProperties.SetAutomationId(source,"source");AutomationProperties.SetName(source,"Harmless source");
        AutomationProperties.SetAutomationId(destination,"destination");AutomationProperties.SetName(destination,"Harmless destination");
        panel.Children.Add(source);panel.Children.Add(destination);
        window=new Window{Title="Disposable transfer acceptance",Width=600,Height=340,Content=panel};
        string flow=Path.Combine(folder,"flow.json");
        if(!File.Exists(flow))File.WriteAllText(flow,json.Serialize(new Dictionary<string,object>{{"format","sports-cave.desktop"},{"version",1},{"id",Guid.NewGuid().ToString()},
            {"name","Automatic run-local text transfer"},{"starting_context",new {mode="prepared",binding=(object)null}},
            {"actions",new[]{Action("transfer_copy","source","Harmless source"),Action("transfer_paste","destination","Harmless destination")}}}));
        actions=(ArrayList)json.Deserialize<Dictionary<string,object>>(File.ReadAllText(flow))["actions"];
        window.ContentRendered+=(s,e)=>{
            window.Activate();source.Focus();Clipboard.SetText("Disposable stale clipboard sentinel");
            playback=new DesktopPlayback(new WindowInteropHelper(window).Handle,(kind,payload)=>{
                if(kind!="play_result")return;
                var result=json.Deserialize<Dictionary<string,object>>(json.Serialize(payload));
                app.Dispatcher.BeginInvoke(new System.Action(()=>{
                    if(!(bool)result["verified"]){
                        if(args.Length>2&&args[2]=="stale"&&step==1&&destination.Text==""&&(bool)result["no_effect"])
                            Finish(true,"Stale clipboard rejected before destination input.");
                        else Finish(false,(string)result["message"]);
                        return;
                    }
                    step++;
                    if(step==1&&args.Length>2&&args[2]=="stale")Clipboard.SetText("Unrelated replacement clipboard value");
                    if(step<actions.Count)playback.Execute(step,(Dictionary<string,object>)actions[step]);
                    else Finish(destination.Text==expected&&Clipboard.GetText()==expected,"Actual destination and complete clipboard independently compared.");
                }));
            });
            try{playback.Arm();playback.Execute(0,(Dictionary<string,object>)actions[0]);}catch(Exception ex){Finish(false,ex.Message);}
        };
        var watchdog=new DispatcherTimer{Interval=TimeSpan.FromSeconds(20)};watchdog.Tick+=(s,e)=>Finish(false,"Acceptance deadline exceeded");watchdog.Start();
        app.Run(window);return Environment.ExitCode;
    }
}
