using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Interop;
using System.Windows.Media;

// These windows never activate and return HTTRANSPARENT. Physical placement uses
// each monitor's full pixel rectangle, including negative origins and mixed DPI.
sealed class RecordingIndicator : IDisposable {
    [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left,Top,Right,Bottom; }
    delegate bool MonitorCallback(IntPtr monitor,IntPtr dc,ref Rect bounds,IntPtr data);
    [DllImport("user32.dll")] static extern bool EnumDisplayMonitors(IntPtr dc,IntPtr clip,MonitorCallback callback,IntPtr data);
    [DllImport("user32.dll",EntryPoint="GetWindowLongPtrW")] static extern IntPtr GetStyle(IntPtr hwnd,int index);
    [DllImport("user32.dll",EntryPoint="SetWindowLongPtrW")] static extern IntPtr SetStyle(IntPtr hwnd,int index,IntPtr value);
    [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr hwnd,IntPtr after,int x,int y,int width,int height,uint flags);
    [DllImport("user32.dll")] static extern bool SetWindowDisplayAffinity(IntPtr hwnd,uint affinity);
    [DllImport("user32.dll")] static extern bool GetWindowDisplayAffinity(IntPtr hwnd,out uint affinity);
    [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr hwnd,out Rect rect);
    [DllImport("user32.dll")] static extern uint GetDpiForWindow(IntPtr hwnd);
    const long ExTransparent=0x20,ExToolWindow=0x80,ExNoActivate=0x08000000;
    readonly List<Window> windows=new List<Window>();
    readonly List<TextBlock> labels=new List<TextBlock>();
    readonly List<Border> borders=new List<Border>();
    string topology="",mode="";
    public object[] Snapshot() {
        var result=new List<object>();
        foreach(var window in windows){
            var hwnd=new WindowInteropHelper(window).Handle;Rect rect;uint affinity;
            GetWindowRect(hwnd,out rect);GetWindowDisplayAffinity(hwnd,out affinity);
            long style=GetStyle(hwnd,-20).ToInt64();
            result.Add(new {mode=mode,rect=new[]{rect.Left,rect.Top,rect.Right,rect.Bottom},dpi=GetDpiForWindow(hwnd),
                click_through=(style&ExTransparent)!=0,no_activate=(style&ExNoActivate)!=0,
                capture_excluded=affinity==0x11,visible=window.IsVisible,content_width=borders[windows.IndexOf(window)].ActualWidth,
                content_height=borders[windows.IndexOf(window)].ActualHeight,label=labels[windows.IndexOf(window)].Text});
        }
        return result.ToArray();
    }
    public static string Mode(string state,bool awaiting,bool paused,bool connected,bool stopping) {
        if(!connected)return "";
        if(state=="recording")return stopping?"Stopping":"Recording";
        if(state=="paused")return "Paused";
        if(state=="playing"&&!awaiting)return paused?"Playback paused":"Playback";
        return "";
    }
    public static Color ColorFor(string mode) {
        if(mode=="Paused"||mode=="Stopping"||mode=="Playback paused")return Color.FromRgb(224,151,32);
        return mode=="Playback"?Color.FromRgb(149,90,232):Color.FromRgb(35,137,245);
    }
    public void Update(string next,string progress) {
        if(next.Length==0){Dispose();return;}
        var monitors=new List<Rect>();
        EnumDisplayMonitors(IntPtr.Zero,IntPtr.Zero,(IntPtr h,IntPtr dc,ref Rect r,IntPtr d)=>{monitors.Add(r);return true;},IntPtr.Zero);
        string key=String.Join(";",monitors.ConvertAll(r=>r.Left+","+r.Top+","+r.Right+","+r.Bottom));
        if(key!=topology){Dispose();topology=key;foreach(var rect in monitors)Create(rect);}
        var brush=new SolidColorBrush(ColorFor(next));
        for(int i=0;i<windows.Count;i++){
            if(mode!=next){borders[i].BorderBrush=brush;labels[i].Background=brush;}
            labels[i].Text=next+"  "+progress;
        }
        mode=next;
    }
    void Create(Rect rect) {
        var label=new TextBlock {Foreground=Brushes.White,FontWeight=FontWeights.SemiBold,FontSize=13,
            Padding=new Thickness(10,3,10,3),HorizontalAlignment=HorizontalAlignment.Center,VerticalAlignment=VerticalAlignment.Top};
        var border=new Border {BorderThickness=new Thickness(3),Child=label,Background=Brushes.Transparent};
        var window=new Window {Title="Sports Cave recording indicator",WindowStyle=WindowStyle.None,ResizeMode=ResizeMode.NoResize,
            AllowsTransparency=true,Background=Brushes.Transparent,ShowInTaskbar=false,ShowActivated=false,Topmost=true,
            Focusable=false,IsHitTestVisible=false,Content=border,Width=1,Height=1,Left=rect.Left,Top=rect.Top};
        window.SourceInitialized+=(s,e)=>{
            var hwnd=new WindowInteropHelper(window).Handle;
            SetStyle(hwnd,-20,new IntPtr(GetStyle(hwnd,-20).ToInt64()|ExTransparent|ExToolWindow|ExNoActivate));
            SetWindowDisplayAffinity(hwnd,0x11); // WDA_EXCLUDEFROMCAPTURE on supported Windows.
            HwndSource.FromHwnd(hwnd).AddHook((IntPtr h,int msg,IntPtr w,IntPtr l,ref bool handled)=>{
                if(msg==0x84){handled=true;return new IntPtr(-1);} // WM_NCHITTEST: HTTRANSPARENT
                if(msg==0x21){handled=true;return new IntPtr(3);} // WM_MOUSEACTIVATE: MA_NOACTIVATE
                return IntPtr.Zero;
            });
            SetWindowPos(hwnd,new IntPtr(-1),rect.Left,rect.Top,rect.Right-rect.Left,rect.Bottom-rect.Top,0x10|0x40);
        };
        windows.Add(window);labels.Add(label);borders.Add(border);window.Show();
        // WPF's initial Show may apply logical sizing after SourceInitialized.
        SetWindowPos(new WindowInteropHelper(window).Handle,new IntPtr(-1),rect.Left,rect.Top,rect.Right-rect.Left,rect.Bottom-rect.Top,0x10|0x40);
        window.UpdateLayout();
    }
    public void Dispose(){foreach(var window in windows)window.Close();windows.Clear();labels.Clear();borders.Clear();topology="";mode="";}
}
