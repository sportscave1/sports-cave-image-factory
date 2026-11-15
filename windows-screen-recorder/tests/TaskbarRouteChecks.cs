using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Windows;
class TaskbarRouteChecks {
    static int n;
    static void Require(bool value){n++;if(!value)throw new Exception("Check "+n);}
    static Dictionary<string,object> Selector(string name="Sports Cave OS",string id="Appid:test",string surface="Shell_TrayWnd") {
        return new Dictionary<string,object>{{"name",name},{"automation_id",id},{"surface",surface},{"class_name","ButtonPeer"},{"control_type","Button"}};
    }
    static void Reject(Action action){try{action();}catch{n++;return;}throw new Exception("Expected refusal");}
    public static void Main() {
        using(var image=new System.Drawing.Bitmap(10,10))using(var clone=(System.Drawing.Bitmap)image.Clone()) {
            clone.SetResolution(144,144);
            Require(ThumbnailCaption.SamePixels(ThumbnailCaption.ReadPixels(image),ThumbnailCaption.ReadPixels(clone)));
            clone.SetPixel(4,4,System.Drawing.Color.Red);
            Require(!ThumbnailCaption.SamePixels(ThumbnailCaption.ReadPixels(image),ThumbnailCaption.ReadPixels(clone)));
        }
        var original=new byte[30000];var noise=new byte[30000];
        for(int i=0;i<5;i++)noise[i*3]=1;
        Require(ThumbnailCaption.SamePixels(original,noise));
        noise[0]=2;Require(!ThumbnailCaption.SamePixels(original,noise));noise[0]=1;
        for(int i=0;i<11;i++)noise[i*3]=1;
        Require(!ThumbnailCaption.SamePixels(original,noise));
        Require(!ThumbnailCaption.SamePixels(original,new byte[3]));
        var visual=Selector(surface:"XamlExplorerHostIslandWindow");visual["control_type"]="ListItem";
        visual["class_name"]=ThumbnailCaption.Marker;visual["automation_id"]="exact-caption";
        ThumbnailCaption.ValidateSelector(visual);
        foreach(var key in new[]{"surface","control_type","automation_id"}){
            var invalid=new Dictionary<string,object>(visual);invalid[key]="wrong";
            Reject(()=>ThumbnailCaption.ValidateSelector(invalid));
        }
        var scope=new Dictionary<string,object>{{"profile","test-profile"},{"page","test-page"},{"product",new string('a',64)}};
        TaskbarRoute.ValidateCaptureScope(scope,new Dictionary<string,object>(scope));
        Reject(()=>TaskbarRoute.ValidateCaptureScope(scope,null));
        var weakened=new Dictionary<string,object>(scope);weakened.Remove("product");
        Reject(()=>TaskbarRoute.ValidateCaptureScope(scope,weakened));
        var changed=new Dictionary<string,object>(scope);changed["product"]=new string('b',64);
        Reject(()=>TaskbarRoute.ValidateCaptureScope(scope,changed));
        changed=new Dictionary<string,object>(scope);changed["profile"]="other";
        Reject(()=>TaskbarRoute.ValidateCaptureScope(scope,changed));
        var running=Selector("Sports Cave OS - 1 running window");running["class_name"]="Taskbar.TaskListButtonAutomationPeer";
        Require(TaskbarRoute.RunningButton(running));
        var stopped=new Dictionary<string,object>(running);stopped["name"]="Sports Cave OS";
        Require(TaskbarRoute.Matches(running,stopped)); // AppID alone stays stable when the app closes.
        Reject(()=>TaskbarRoute.ValidateLiveSelector(running,stopped));
        TaskbarRoute.ValidateLiveSelector(running,running);
        var route=new Dictionary<string,object>{{"button",running},{"thumbnail",Selector(surface:"TaskListThumbnailWnd")}};
        TaskbarRoute.ValidateThumbnailDestination(route,"Sports Cave OS");
        Reject(()=>TaskbarRoute.ValidateThumbnailDestination(route,"Other window"));
        running["name"]="Sports Cave OS pinned";Require(!TaskbarRoute.RunningButton(running));
        running["name"]="Sports Cave OS - 0 running windows";Require(!TaskbarRoute.RunningButton(running));
        running["name"]="Sports Cave OS - 2 running windows";running["automation_id"]="StartButton";Require(!TaskbarRoute.RunningButton(running));
        running["automation_id"]="Appid:test";running["surface"]="XamlExplorerHostIslandWindow";Require(!TaskbarRoute.RunningButton(running));
        var a=Selector();Require(TaskbarRoute.Matches(a,Selector("Sports Cave OS - 2 running windows")));
        Require(!TaskbarRoute.Matches(a,Selector(id:"Appid:other")));
        Require(!TaskbarRoute.Matches(a,Selector(surface:"Shell_SecondaryTrayWnd")));
        Require(!TaskbarRoute.Matches(Selector(id:""),Selector("Other",id:"")));
        Require(!TaskbarRoute.Matches(Selector(surface:"TaskListThumbnailWnd"),Selector("Other",surface:"TaskListThumbnailWnd")));
        var item=new TaskbarRoute.Item{Window=new IntPtr(1),Selector=a,Bounds=new Rect(10,10,20,20),At=Stopwatch.GetTimestamp()};
        Require(TaskbarRoute.Unique(new[]{item},a)==item);
        Reject(()=>TaskbarRoute.Unique(new TaskbarRoute.Item[0],a));Reject(()=>TaskbarRoute.Unique(new[]{item,item},a));
        Require(TaskbarRoute.Hit(new[]{item},new IntPtr(1),new Native.Point{X=15,Y=15})==item);
        Require(TaskbarRoute.Hit(new[]{item},new IntPtr(2),new Native.Point{X=15,Y=15})==null);
        Require(TaskbarRoute.Hit(new[]{item,item},new IntPtr(1),new Native.Point{X=15,Y=15})==null);
        item.At=Stopwatch.GetTimestamp()-Stopwatch.Frequency*2;
        Require(TaskbarRoute.Hit(new[]{item},new IntPtr(1),new Native.Point{X=15,Y=15})==null);
        // Cancellation must occur before any Win32/UIA call or effect.
        bool verified=false,invoked=false;
        Reject(()=>TaskbarRoute.Play(new Dictionary<string,object>(),IntPtr.Zero,()=>{throw new OperationCanceledException();},()=>verified=true,()=>invoked=true));
        Require(!verified&&!invoked);
        // A verified caption refresh extends only its own physically opened group.
        var capture=new Capture(IntPtr.Zero,(kind,payload)=>{},reason=>{},false);
        var flags=System.Reflection.BindingFlags.Instance|System.Reflection.BindingFlags.NonPublic;
        Action<string,object> field=(name,value)=>typeof(Capture).GetField(name,flags).SetValue(capture,value);
        Func<long> lease=()=> (long)typeof(Capture).GetField("pendingShellAt",flags).GetValue(capture);
        var refresh=typeof(Capture).GetMethod("RefreshPendingCaption",flags);
        field("pendingShellPopup",new IntPtr(12));field("preparedCaptionTitle","Extensions - Google Chrome");
        visual["name"]="Extensions - Google Chrome";
        var caption=new TaskbarRoute.Item{Window=new IntPtr(12),Selector=visual};
        refresh.Invoke(capture,new object[]{caption});Require(lease()==0); // No physical opener.
        field("pendingShellButton",item);caption.Window=new IntPtr(13);
        refresh.Invoke(capture,new object[]{caption});Require(lease()==0); // Different popup.
        caption.Window=new IntPtr(12);visual["name"]="New Tab - Google Chrome";
        refresh.Invoke(capture,new object[]{caption});Require(lease()==0); // Different destination.
        visual["name"]="Extensions - Google Chrome";
        refresh.Invoke(capture,new object[]{caption});Require(lease()>0);
        Console.WriteLine(n+" taskbar policy checks passed (no desktop input).");
    }
}
