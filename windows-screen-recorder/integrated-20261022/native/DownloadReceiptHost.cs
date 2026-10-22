using System;
using System.IO;
using System.Text;
using System.Linq;
using System.Collections.Generic;
using System.Web.Script.Serialization;

// Edge native-messaging entry point. Only the registered local adapter may call
// this executable. Receipts contain metadata, never downloaded file contents.
class DownloadReceiptHost {
    static bool ReadExact(Stream input,byte[] bytes) {
        int read=0;
        while(read<bytes.Length){int n=input.Read(bytes,read,bytes.Length-read);if(n==0)return false;read+=n;}
        return true;
    }
    static void Main() {
        try {
            var input=Console.OpenStandardInput();var header=new byte[4];
            if(!ReadExact(input,header))return;
            int size=BitConverter.ToInt32(header,0);if(size<2||size>16384)return;
            var bytes=new byte[size];if(!ReadExact(input,bytes))return;
            var json=new JavaScriptSerializer();
            var value=json.Deserialize<Dictionary<string,object>>(Encoding.UTF8.GetString(bytes));
            var fields=new[]{"v","event","id","url","final_url","filename","state","bytes","started","ended","error","observed"};
            if(value==null||value.Count!=fields.Length||fields.Any(key=>!value.ContainsKey(key)))return;
            foreach(string key in new[]{"event","id","url","final_url","filename","state","started","ended","error"})
                if(!(value[key] is string)||((string)value[key]).Length>4096)return;
            if(!new[]{"in_progress","complete","interrupted"}.Contains((string)value["state"]))return;
            DateTime started;if(!DateTime.TryParse((string)value["started"],out started))return;
            Uri url;Guid nonce;
            if(!Uri.TryCreate((string)value["url"],UriKind.Absolute,out url)||url.Scheme!="http"||url.Host!="127.0.0.1"||
               (url.Port!=18962&&url.Port!=18963)||url.UserInfo!=""||url.Fragment!="")return;
            var query=System.Web.HttpUtility.ParseQueryString(url.Query);
            if(!Guid.TryParse(query["sc_download"],out nonce))return;
            int id;if(!Int32.TryParse((string)value["id"],out id)||id<0)return;
            if(Convert.ToInt32(value["v"])!=1||!new[]{"created","changed"}.Contains((string)value["event"]))return;
            var configPath=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"active.json");
            if(!File.Exists(configPath))return;
            var config=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(configPath));
            var root=Path.GetFullPath((string)config["events"]);
            if(!Directory.Exists(root)||DateTime.UtcNow> DateTime.Parse((string)config["expires"]).ToUniversalTime())return;
            value["session"]=(string)config["session"];
            value["received"]=DateTime.UtcNow.ToString("o");
            string path=Path.Combine(root,Guid.NewGuid().ToString()+".json");
            File.WriteAllText(path+".tmp",json.Serialize(value),new UTF8Encoding(false));
            File.Move(path+".tmp",path);
            var response=Encoding.UTF8.GetBytes("{\"accepted\":true}");
            var output=Console.OpenStandardOutput();output.Write(BitConverter.GetBytes(response.Length),0,4);output.Write(response,0,response.Length);output.Flush();
        } catch { /* Invalid or inactive sessions receive no actionable receipt. */ }
    }
}
