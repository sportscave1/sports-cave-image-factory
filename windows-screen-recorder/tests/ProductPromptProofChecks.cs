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
        Require(!ProductPromptProof.Matches(prompt.Replace("\n","\r\n"),parsed),"line-ending change rejected");
        var page=new Dictionary<string,object>{{"profile","test"},{"page","local"},{"product","a"}};
        var wrong=new Dictionary<string,object>(page);wrong["product"]="b";
        Require(!BrowserIdentity.SamePage(page,wrong),"wrong prepared product rejected");
        Require(!BrowserIdentity.SamePage(page,new Dictionary<string,object>{{"profile","test"},{"page","local"}}),"missing product rejected");
        Console.WriteLine("8 full-prompt and product-binding checks passed; UTF16="+prompt.Length+", UTF8="+Encoding.UTF8.GetByteCount(prompt));
    }
}
