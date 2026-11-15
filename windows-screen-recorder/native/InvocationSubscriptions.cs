using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Threading;

// UIA registration/removal share one MTA thread. In particular, removing a
// provider's handler must never block capture ordering, Stop, or the UI thread.
internal sealed class InvocationSubscriptions {
    readonly BlockingCollection<Action> work=new BlockingCollection<Action>(32);
    readonly Dictionary<IntPtr,Action> subscriptions=new Dictionary<IntPtr,Action>();
    volatile bool failed;
    public InvocationSubscriptions() {
        var worker=new Thread(()=>{foreach(var action in work.GetConsumingEnumerable())action();})
            {IsBackground=true,Name="recorder-invocation-observers"};
        worker.SetApartmentState(ApartmentState.MTA);worker.Start();
    }
    public void Ensure(IntPtr window,Func<Action> subscribe,int deadlineMs=1000) {
        if(failed)throw new Exception("Accessibility event subscription did not finish. Restart the candidate; the draft is preserved.");
        var done=new ManualResetEventSlim(false);Exception error=null;
        if(!work.TryAdd(()=>{
            try {
                if(!subscriptions.ContainsKey(window)) {
                    if(subscriptions.Count>=16)throw new Exception("Recording reached the limit of sixteen observed windows. Stop and save the draft.");
                    subscriptions.Add(window,subscribe());
                }
            }catch(Exception ex){error=ex;}
            finally{done.Set();}
        }))throw new Exception("Accessibility event subscription queue is full. Stop and save the draft.");
        if(!done.Wait(deadlineMs)) {
            failed=true;
            throw new Exception("Accessibility event subscription did not finish within its deadline. Restart the candidate; the draft is preserved.");
        }
        done.Dispose();
        if(error!=null)throw new Exception("Accessibility event subscription failed. Draft preserved.",error);
    }
    public void Reset() {
        // Callers invalidate callbacks immediately. Provider cleanup can then
        // finish asynchronously, in registration order and on the same thread.
        if(!work.TryAdd(()=>{
            foreach(var remove in subscriptions.Values) {
                try{remove();}catch{ /* A closed provider no longer needs cleanup. */ }
            }
            subscriptions.Clear();
        }))failed=true;
    }
}
