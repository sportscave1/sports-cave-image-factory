using System;
using System.Diagnostics;
using System.Threading;

// Process-only operation measurements. No desktop inspection, values or input.
sealed class NativeMetrics {
    readonly string phase;
    readonly Stopwatch elapsed=Stopwatch.StartNew();
    readonly double cpu;
    readonly long memory,working;
    int finished;
    NativeMetrics(string phase) {
        this.phase=phase;
        using(var process=Process.GetCurrentProcess()){
            cpu=process.TotalProcessorTime.TotalMilliseconds;
            memory=process.PrivateMemorySize64;working=process.WorkingSet64;
        }
    }
    public static NativeMetrics Begin(string phase){try{return new NativeMetrics(phase);}catch{return null;}}
    public void Finish(Action<string,object> send) {
        if(Interlocked.Exchange(ref finished,1)!=0)return;
        object result;
        try {
            using(var process=Process.GetCurrentProcess())result=new {kind="native_operation_metrics",phase=phase,
                elapsed_ms=Math.Round(elapsed.Elapsed.TotalMilliseconds,2),
                cpu_ms=Math.Round(process.TotalProcessorTime.TotalMilliseconds-cpu,2),
                private_bytes_before=memory,private_bytes_after=process.PrivateMemorySize64,
                working_set_before=working,working_set_after=process.WorkingSet64};
        }catch{return;} // Measurement failure cannot change the operation's result.
        send("diagnostic",result);
    }
}
