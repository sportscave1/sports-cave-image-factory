using System;
using System.Collections.Generic;
using System.Windows;
class NativeDownloadWitnessChecks {
    static int checks;
    static void Require(bool ok){checks++;if(!ok)throw new Exception("Witness guard failed");}
    static void Reject(Action action){checks++;try{action();}catch{return;}throw new Exception("Unsafe witness accepted");}
    static Dictionary<string,object> Raw(){return new Dictionary<string,object>{
        {"identity",new object()},{"time",123456L},{"name","Save disposable file as"},
        {"download",new Dictionary<string,object>{{"url","http://127.0.0.1:18963/sample.txt?sc_download=49c3a012-8dfc-426f-8f35-7b2aca074aff"},{"filename","sample.txt"},{"save_as",true}}},
        {"pointer",new Dictionary<string,object>{{"x",140.0},{"y",130.0},{"width",700.0},{"height",800.0},{"scale",1.4}}}};}
    static Dictionary<string,object> Read(Dictionary<string,object> raw,int left=1000){return BrowserDownload.WitnessDownload(raw,
        new Dictionary<string,object>{{"page","http://127.0.0.1:18963/recorder-acceptance/tab-a"}},
        new Native.Point{X=left+140,Y=230},new Rect(left,100,700,800),134);}
    static int Main(){
        Require(Read(Raw())!=null);Require(Read(Raw(),-1000)!=null);
        var raw=Raw();((Dictionary<string,object>)raw["pointer"])["x"]=180.0;Reject(()=>Read(raw));
        raw=Raw();((Dictionary<string,object>)raw["pointer"])["scale"]=1.0;Reject(()=>Read(raw));
        raw=Raw();((Dictionary<string,object>)raw["pointer"])["width"]=750.0;Reject(()=>Read(raw));
        raw=Raw();((Dictionary<string,object>)raw["pointer"])["x"]=Double.NaN;Reject(()=>Read(raw));
        raw=Raw();raw["extra"]="unexpected";Reject(()=>Read(raw));
        raw=Raw();((Dictionary<string,object>)raw["download"])["save_as"]=false;Reject(()=>Read(raw));
        raw=Raw();((Dictionary<string,object>)raw["download"])["url"]="http://127.0.0.1:18962/sample.txt?sc_download=49c3a012-8dfc-426f-8f35-7b2aca074aff";Reject(()=>Read(raw));
        raw=Raw();((Dictionary<string,object>)raw["download"])["url"]="http://127.0.0.1:18963/sample.txt?sc_download=invalid";Reject(()=>Read(raw));
        raw=Raw();((Dictionary<string,object>)raw["download"])["filename"]="../sample.txt";Reject(()=>Read(raw));
        raw=Raw();raw.Remove("download");Require(Read(raw)==null);
        Console.WriteLine("PASS "+checks+" trusted download witness checks; no desktop input.");return 0;
    }
}
