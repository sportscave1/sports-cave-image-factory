using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Web.Script.Serialization;
class ProductPromptProofChecks {
    static void Require(bool value,string message){if(!value)throw new Exception(message);}
    static void Main(string[] args) {
        string prompt=File.ReadAllText(args[0]);
        var proof=new Dictionary<string,object>{{"sha256",CopyText.Hash(prompt)},{"utf16_length",prompt.Length},{"utf8_length",Encoding.UTF8.GetByteCount(prompt)}};
        var parsed=ProductPromptProof.Parse(ProductPromptProof.Prefix+new JavaScriptSerializer().Serialize(proof));
        Require(prompt.Length>2000,"real master prompt exceeds editor limit");
        Require(ProductPromptProof.Matches(prompt,parsed),"complete prompt");
        Require(!ProductPromptProof.Matches(prompt.Substring(0,2000),parsed),"truncation rejected");
        Require(!ProductPromptProof.Matches(prompt+"x",parsed),"suffix rejected");
        Require(!ProductPromptProof.Matches("x"+prompt.Substring(1),parsed),"same-length change rejected");
        string lf="Long Unicode 🖼 café\n"+new string('x',3000)+"\nEND";
        var lfProof=new Dictionary<string,object>{{"sha256",CopyText.Hash(lf)},{"utf16_length",lf.Length},{"utf8_length",Encoding.UTF8.GetByteCount(lf)}};
        Require(ProductPromptProof.Matches(lf.Replace("\n","\r\n"),lfProof),"Windows clipboard CRLF transport accepted");
        Require(!ProductPromptProof.Matches(lf.Replace("\n","\r"),lfProof),"lone CR rejected");
        Require(!ProductPromptProof.Matches(lf.Replace("\n","\r\n")+" ",lfProof),"transport does not trim suffix");
        var page=new Dictionary<string,object>{{"profile","test"},{"page","local"},{"product","a"}};
        var wrong=new Dictionary<string,object>(page);wrong["product"]="b";
        Require(!BrowserIdentity.SamePage(page,wrong),"wrong prepared product rejected");
        Require(!BrowserIdentity.SamePage(page,new Dictionary<string,object>{{"profile","test"},{"page","local"}}),"missing product rejected");
        Console.WriteLine("10 full-prompt and product-binding checks passed; UTF16="+prompt.Length+", UTF8="+Encoding.UTF8.GetByteCount(prompt));
    }
}
