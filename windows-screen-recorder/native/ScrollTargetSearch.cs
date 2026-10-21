using System;
using System.Collections.Generic;
using System.Diagnostics;

// Metadata-only traversal. Every visited child counts toward the budget,
// including rejected branches; multiple eligible targets never select one.
sealed class ScrollTargetSearch<T> where T:class {
    readonly Func<T,bool> contains,scrollable;
    readonly Func<T,IEnumerable<T>> children;
    readonly int maxNodes,maxDepth,maxMilliseconds;
    readonly string purpose;
    readonly Stopwatch elapsed=Stopwatch.StartNew();
    int nodes;
    T found;
    public ScrollTargetSearch(Func<T,bool> contains,Func<T,bool> scrollable,
        Func<T,IEnumerable<T>> children,int maxNodes=256,int maxDepth=16,string purpose="Scroll",int maxMilliseconds=200) {
        this.contains=contains;this.scrollable=scrollable;this.children=children;
        this.maxNodes=maxNodes;this.maxDepth=maxDepth;this.purpose=purpose;this.maxMilliseconds=maxMilliseconds;
    }
    public T Find(T root){Visit(root,0);return found;}
    void Visit(T node,int depth) {
        if(++nodes>maxNodes||elapsed.ElapsedMilliseconds>maxMilliseconds)
            throw new InvalidOperationException(purpose+" target search exceeded its bounded budget. Draft preserved.");
        if(!contains(node))return;
        if(depth>maxDepth)
            throw new InvalidOperationException(purpose+" target ancestry exceeds the supported bound. Draft preserved.");
        if(scrollable(node)) {
            if(found!=null)throw new InvalidOperationException("More than one "+purpose.ToLowerInvariant()+" target contains the pointer. Draft preserved; no target guessed.");
            found=node;
        }
        foreach(var child in children(node))Visit(child,depth+1);
    }
}
