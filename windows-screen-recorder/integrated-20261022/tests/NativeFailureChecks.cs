using System;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.Serialization;
using System.Threading;
using System.Windows.Automation;

// Exercises real queues and worker failure paths. Never constructs a Window,
// arms hooks, accesses a desktop target, or sends application input.
class NativeFailureChecks {
    static int checks;
    static void Require(bool ok,string reason){checks++;if(!ok)throw new Exception(reason);}
    static void Until(Func<bool> done){var wait=Stopwatch.StartNew();while(!done()){if(wait.ElapsedMilliseconds>3000)throw new Exception("Worker did not settle");Thread.Sleep(5);}}
    static readonly MethodInfo Put=typeof(Capture).GetMethod("Put",BindingFlags.Instance|BindingFlags.NonPublic);
    static void Enqueue(Capture capture,Action action){Put.Invoke(capture,new object[]{action});}
    [STAThread] static int Main(string[] args) {
        if(args.Length==2&&args[0]=="--overflow-child") {
            var capture=new Capture(IntPtr.Zero,(kind,payload)=>{},reason=>{},false);capture.Armed=true;
            var host=(Host)FormatterServices.GetUninitializedObject(typeof(Host));
            var queue=new BlockingCollection<string>(128);
            for(int i=0;i<128;i++)queue.Add("synthetic frame");
            typeof(Host).GetField("outbound",BindingFlags.Instance|BindingFlags.NonPublic).SetValue(host,queue);
            typeof(Host).GetField("capture",BindingFlags.Instance|BindingFlags.NonPublic).SetValue(host,capture);
            AppDomain.CurrentDomain.ProcessExit+=(s,e)=>File.WriteAllText(args[1],capture.Broken&&!capture.Armed?"capture suspended":"unsafe");
            typeof(Host).GetMethod("Send",BindingFlags.Instance|BindingFlags.NonPublic).Invoke(host,new object[]{"diagnostic",new {kind="synthetic overflow"}});
            return 17; // A full connection must never return to normal operation.
        }
        int failures=0,queuedWork=0;string problem="";
        var entered=new ManualResetEvent(false);var release=new ManualResetEvent(false);
        var flooded=new Capture(IntPtr.Zero,(kind,payload)=>{},reason=>{problem=reason;Interlocked.Increment(ref failures);},false);
        Enqueue(flooded,()=>{entered.Set();release.WaitOne();});Require(entered.WaitOne(1000),"synthetic worker is held");
        for(int i=0;i<129;i++)Enqueue(flooded,()=>Interlocked.Increment(ref queuedWork));
        Require(flooded.Broken&&!flooded.Armed&&failures==1&&problem.Contains("queue is full"),"capture overflow interrupts once");
        release.Set();Until(()=>Interlocked.Read(ref flooded.BusySince)==0);
        Thread.Sleep(30);Require(queuedWork==0,"queued targets are not inspected after overflow");
        var delayedEntered=new ManualResetEvent(false);var delayedRelease=new ManualResetEvent(false);
        string delayedProblem="";int staleReads=0,cleanups=0;
        var delayed=new Capture(IntPtr.Zero,(kind,payload)=>{},reason=>delayedProblem=reason,false);
        Enqueue(delayed,()=>{delayedEntered.Set();delayedRelease.WaitOne();});Require(delayedEntered.WaitOne(1000),"delayed provider entered");
        Enqueue(delayed,()=>staleReads++);Thread.Sleep(600);delayedRelease.Set();Until(()=>delayed.Broken);
        Require(staleReads==0&&delayedProblem.Contains("fell behind"),"stale queued observations fail before reading a changed target");
        typeof(Capture).GetMethod("Enqueue",BindingFlags.Instance|BindingFlags.NonPublic).Invoke(delayed,new object[]{new Action(()=>Interlocked.Increment(ref cleanups)),true});
        Until(()=>cleanups==1);Require(cleanups==1,"accessibility cleanup survives interrupted capture");
        int providerFailures=0;string providerMessage="";
        var provider=new Capture(IntPtr.Zero,(kind,payload)=>{},reason=>{providerMessage=reason;Interlocked.Increment(ref providerFailures);},false);
        Enqueue(provider,()=>{throw new ElementNotAvailableException();});Until(()=>provider.Broken);
        Require(providerFailures==1&&providerMessage=="The target window disappeared.","provider disappearance interrupts capture");
        int watchdogFailures=0;
        var watchdog=new Capture(IntPtr.Zero,(kind,payload)=>{},reason=>Interlocked.Increment(ref watchdogFailures),false);
        watchdog.BusySince=Stopwatch.GetTimestamp()-4*Stopwatch.Frequency;watchdog.Watchdog();watchdog.Watchdog();
        Require(watchdog.Broken&&!watchdog.Armed&&watchdogFailures==1,"provider stall watchdog interrupts once");
        string result=Path.Combine(Path.GetTempPath(),"recorder-failure-"+Guid.NewGuid().ToString("N")+".txt");
        try {
            var info=new ProcessStartInfo(Assembly.GetExecutingAssembly().Location,"--overflow-child \""+result+"\""){UseShellExecute=false,CreateNoWindow=true};
            using(var child=Process.Start(info)){
                if(!child.WaitForExit(5000)){child.Kill();throw new Exception("Overflow child did not stop");}
                Require(child.ExitCode==78&&File.ReadAllText(result)=="capture suspended","real full outbound queue closes only its candidate process");
            }
        }finally{if(File.Exists(result))File.Delete(result);}
        Console.WriteLine("PASS "+checks+" native provider/overflow checks (no desktop input or inspection)");return 0;
    }
}
