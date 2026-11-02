using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Web.Script.Serialization;
using System.Windows.Automation;

// Experimental, explicitly selected local caption route. Existing UIA recordings
// never opt in automatically. No dependency download, remote service or focus fallback.
static class ThumbnailCaption {
    internal const string Marker="SC.LocalCaption.v1";
    internal static bool Configured {get{return !String.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("SC_RECORDER_OCR_WORKER"));}}
    internal static void VerifyRuntime() {
        if(!File.Exists(Setting("SC_RECORDER_OCR_PYTHON"))||!File.Exists(Setting("SC_RECORDER_OCR_WORKER"))||!Directory.Exists(Setting("SC_RECORDER_OCR_LIBRARY")))
            throw new Exception("Local caption runtime is unavailable. No taskbar input sent.");
        Setting("SC_RECORDER_OCR_DATA");
    }
    internal sealed class Observation {
        internal IntPtr Shell;
        internal string Title;
        internal Rectangle Caption,Proof,SourceRegion;
        internal byte[] Pixels;
        internal string Failure;
        internal byte[] LastPixels;
        internal bool Current() {
            Failure=null;LastPixels=null;
            if(Native.GetForegroundWindow()!=Shell||TaskbarRoute.Class(Shell)!="XamlExplorerHostIslandWindow"){Failure="shell focus changed";return false;}
            TaskbarRoute.Shell(Shell);
            var point=new Native.Point{X=Caption.Left+Caption.Width/2,Y=Caption.Top+Caption.Height/2};
            if(Native.GetAncestor(WindowFromPhysicalPoint(point),2)!=Shell){Failure="caption hit surface changed";return false;}
            // Use the same desktop blit geometry as recognition. Capturing the
            // small proof separately can change compositor rounding at text edges.
            var relative=new Rectangle(Proof.Left-SourceRegion.Left,Proof.Top-SourceRegion.Top,Proof.Width,Proof.Height);
            if(!new Rectangle(0,0,SourceRegion.Width,SourceRegion.Height).Contains(relative)){Failure="proof geometry changed";return false;}
            using(var image=Capture(SourceRegion)){LastPixels=ReadPixels(image,relative);bool same=SamePixels(Pixels,LastPixels);if(!same)Failure="caption pixels changed";return same;}
        }
        internal TaskbarRoute.Item Item() {
            return new TaskbarRoute.Item{Window=Shell,Bounds=new System.Windows.Rect(Caption.Left,Caption.Top,Caption.Width,Caption.Height),At=Stopwatch.GetTimestamp(),
                Selector=new Dictionary<string,object>{{"surface","XamlExplorerHostIslandWindow"},{"control_type","ListItem"},{"class_name",Marker},{"automation_id","exact-caption"},{"name",Title}}};
        }
    }
    internal static byte[] ReadPixels(Bitmap image) {
        return ReadPixels(image,new Rectangle(0,0,image.Width,image.Height));
    }
    static byte[] ReadPixels(Bitmap image,Rectangle region) {
        // Compare displayed RGB, not PNG metadata or non-displayed alpha.
        byte[] pixels=new byte[region.Width*region.Height*3];int at=0;
        for(int y=region.Top;y<region.Bottom;y++)for(int x=region.Left;x<region.Right;x++) {
            int color=image.GetPixel(x,y).ToArgb();
            // The desktop is composited; backing bitmap alpha is not displayed.
            pixels[at++]=(byte)color;pixels[at++]=(byte)(color>>8);pixels[at++]=(byte)(color>>16);
        }
        return pixels;
    }
    internal static bool SamePixels(byte[] expected,byte[] current) {
        if(expected==null||current==null||expected.Length!=current.Length||expected.Length==0||expected.Length%3!=0)return false;
        int changed=0,limit=Math.Min(16,expected.Length/3/1000);
        for(int i=0;i<expected.Length;i+=3){bool differs=false;
            for(int channel=0;channel<3;channel++){int delta=Math.Abs(expected[i+channel]-current[i+channel]);if(delta>1)return false;if(delta!=0)differs=true;}
            if(differs&&++changed>limit)return false;
        }
        return true;
    }
    internal static void ValidateSelector(Dictionary<string,object> selector) {
        if(!Equals(selector["surface"],"XamlExplorerHostIslandWindow")||!Equals(selector["control_type"],"ListItem")||
           !Equals(selector["class_name"],Marker)||!Equals(selector["automation_id"],"exact-caption"))
            throw new Exception("Invalid local thumbnail caption selector.");
    }
    static string Setting(string name) {
        string value=Environment.GetEnvironmentVariable(name);
        if(String.IsNullOrWhiteSpace(value)||!Path.IsPathRooted(value)||value.Contains("\""))
            throw new Exception("Local thumbnail caption runtime is not configured.");
        return Path.GetFullPath(value);
    }
    static Bitmap Capture(Rectangle region) {
        var bitmap=new Bitmap(region.Width,region.Height);
        try{using(var graphics=Graphics.FromImage(bitmap))graphics.CopyFromScreen(region.Left,region.Top,0,0,region.Size);return bitmap;}
        catch{bitmap.Dispose();throw;}
    }
    internal static void Activate(string title,Action check,Action verifyIdentity,Action<System.Windows.Point> click,Action<object> trace,int observations=2,Action<Observation> observe=null) {
        string python=Setting("SC_RECORDER_OCR_PYTHON"),worker=Setting("SC_RECORDER_OCR_WORKER"),library=Setting("SC_RECORDER_OCR_LIBRARY"),directory=Setting("SC_RECORDER_OCR_DATA");
        if(!File.Exists(python)||!File.Exists(worker)||!Directory.Exists(library))throw new Exception("Local caption dependencies are unavailable.");
        check();verifyIdentity();var shell=Native.GetForegroundWindow();var opening=Stopwatch.StartNew();
        while(TaskbarRoute.Class(shell)!="XamlExplorerHostIslandWindow"&&opening.ElapsedMilliseconds<1500){check();System.Threading.Thread.Sleep(50);shell=Native.GetForegroundWindow();}
        TaskbarRoute.Shell(shell);
        if(TaskbarRoute.Class(shell)!="XamlExplorerHostIslandWindow")throw new Exception("Local caption route requires the actual grouped popup.");
        var bounds=AutomationElement.FromHandle(shell).Current.BoundingRectangle;
        // Initial supported layout is a bottom taskbar. An unavailable caption
        // outside this bounded observation is a refusal, never a guessed position.
        var region=new Rectangle((int)bounds.Left,(int)Math.Max(bounds.Top,bounds.Bottom-600),(int)bounds.Width,(int)Math.Min(600,bounds.Height));
        if(region.Width<1||region.Width>4096||region.Height<1)throw new Exception("Unsupported shell observation geometry.");
        Directory.CreateDirectory(directory);string stem=Path.Combine(directory,Guid.NewGuid().ToString("N"));
        string image=stem+".png",request=stem+"-request.json",result=stem+"-result.json";
        var json=new JavaScriptSerializer();
        using(var before=Capture(region)) {
            before.Save(image,System.Drawing.Imaging.ImageFormat.Png);
            File.WriteAllText(request,json.Serialize(new {image=image,title=title,library=library}));
            using(var process=new Process{StartInfo=new ProcessStartInfo{FileName=python,
                Arguments="-I -B -X utf8 \""+worker+"\" \""+request+"\" \""+result+"\"",UseShellExecute=false,CreateNoWindow=true}}) {
                process.Start();var deadline=Stopwatch.StartNew();
                try{while(!process.WaitForExit(50)){check();if(deadline.ElapsedMilliseconds>10000)throw new Exception("Local caption recognition timed out.");}}
                finally{if(!process.HasExited)process.Kill();}
                if(process.ExitCode!=0||!File.Exists(result)||new FileInfo(result).Length>4096)throw new Exception("Local caption recognition did not return a bounded result.");
            }
            var answer=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(result));
            if(!answer.ContainsKey("ok")||!Equals(answer["ok"],true)) {
                string error=answer.ContainsKey("error")?Convert.ToString(answer["error"]):"unavailable";
                if(error=="Thumbnail caption is missing."&&observations>1){Activate(title,check,verifyIdentity,click,trace,observations-1,observe);return;}
                throw new Exception("Local caption refused: "+error);
            }
            if(!Equals(answer["title"],title))throw new Exception("Local caption returned a different destination.");
            double score=Convert.ToDouble(answer["score"]);
            if(Double.IsNaN(score)||score<.97||score>1)throw new Exception("Local caption confidence is insufficient.");
            var values=((System.Collections.IEnumerable)answer["rect"]).Cast<object>().Select(Convert.ToInt32).ToArray();
            if(values.Length!=4)throw new Exception("Invalid caption geometry.");
            var caption=Rectangle.FromLTRB(values[0],values[1],values[2],values[3]);
            if(caption.Width<20||caption.Height<8||caption.Height>80||!new Rectangle(0,0,region.Width,region.Height).Contains(caption))throw new Exception("Invalid caption bounds.");
            check();verifyIdentity();
            if(Native.GetForegroundWindow()!=shell||AutomationElement.FromHandle(shell).Current.BoundingRectangle!=bounds)throw new Exception("Grouped popup moved during recognition.");
            // Re-check the rendered caption and adjacent preview pixels immediately
            // before input. A moved, replaced or obscured preview is not clicked.
            var proof=Rectangle.Intersect(new Rectangle(caption.Left-4,caption.Top-4,caption.Width+8,caption.Height+32),new Rectangle(0,0,region.Width,region.Height));
            bool same;
            using(var fresh=Capture(region)) {
                same=SamePixels(ReadPixels(before,proof),ReadPixels(fresh,proof));
                if(!same)fresh.Save(stem+"-changed.png",System.Drawing.Imaging.ImageFormat.Png);
            }
            if(!same) {
                // One bounded read-only reacquisition permits opening animations.
                // The taskbar button and thumbnail are not activated again.
                if(observations>1){Activate(title,check,verifyIdentity,click,trace,observations-1,observe);return;}
                throw new Exception("Thumbnail pixels changed during recognition. No input sent.");
            }
            var point=new System.Windows.Point(region.Left+caption.Left+caption.Width/2.0,region.Top+caption.Top+caption.Height/2.0);
            if(Native.GetAncestor(WindowFromPhysicalPoint(new Native.Point{X=(int)point.X,Y=(int)point.Y}),2)!=shell)
                throw new Exception("Thumbnail caption is not on the verified shell surface. No input sent.");
            check();verifyIdentity();if(Native.GetForegroundWindow()!=shell)throw new Exception("Grouped popup lost focus before input.");
                var observation=new Observation{Shell=shell,Title=title,SourceRegion=region,Caption=new Rectangle(region.Left+caption.Left,region.Top+caption.Top,caption.Width,caption.Height),
                    Proof=new Rectangle(region.Left+proof.Left,region.Top+proof.Top,proof.Width,proof.Height),Pixels=ReadPixels(before,proof)};
                if(!observation.Current()){
                    using(var crop=before.Clone(proof,System.Drawing.Imaging.PixelFormat.Format32bppArgb))crop.Save(stem+"-proof-expected.png",System.Drawing.Imaging.ImageFormat.Png);
                    // Save the exact failed comparison, not a later screenshot that
                    // may have changed again. Local evidence only; never serialized in a route.
                    if(observation.LastPixels!=null)File.WriteAllBytes(stem+"-proof-current.rgb",observation.LastPixels);
                    File.WriteAllText(stem+"-proof-failure.json",json.Serialize(new {reason=observation.Failure,width=proof.Width,height=proof.Height}));
                    throw new Exception("Thumbnail proof expired: "+observation.Failure+". No input sent.");
                }
                check();verifyIdentity();
                if(observe!=null)observe(observation);else click(point);
                if(trace!=null)trace(new {route=Marker,title=title,score=score,pixels_revalidated=true});
        }
    }
    [System.Runtime.InteropServices.DllImport("user32.dll")] static extern IntPtr WindowFromPhysicalPoint(Native.Point point);
}
