using System;using System.IO;using System.Reflection;using System.Collections.Generic;using System.Security.Cryptography;using System.Drawing;
class ChatDownloadChecks {
 static Type policy;static int count;
 static object Call(string name,params object[] args){try{return policy.GetMethod(name).Invoke(null,args);}catch(TargetInvocationException e){throw e.InnerException;}}
 static void Require(bool v){count++;if(!v)throw new Exception("Check "+count);}
 static void Reject(Action fn){bool rejected=false;try{fn();}catch{rejected=true;}Require(rejected);}
 static void Main(string[] args){policy=Assembly.LoadFrom(args[0]).GetType("ChatDownloads");
 Require((bool)Call("CollisionName","Random Name.png","Random Name (2).png"));Require(!(bool)Call("CollisionName","Random Name.png","Random Name-old.png"));Require(!(bool)Call("CollisionName","Random Name.png","Random Name.png.crdownload"));Require(!(bool)Call("CollisionName","../bad.png","bad.png"));
 string dir=Path.Combine(Path.GetTempPath(),"sc-download-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(dir);string old=Path.Combine(dir,"Random Name.png");
 using(var bitmap=new Bitmap(2,2)){bitmap.SetPixel(0,0,Color.Red);bitmap.Save(old,System.Drawing.Imaging.ImageFormat.Png);}
 string hash;using(var h=SHA256.Create())hash=BitConverter.ToString(h.ComputeHash(File.ReadAllBytes(old))).Replace("-","").ToLowerInvariant();var before=new HashSet<string>(Directory.GetFiles(dir),StringComparer.OrdinalIgnoreCase);
 Require(Call("NewCompleted",dir,"Random Name.png",hash,before)==null);
 string fresh=Path.Combine(dir,"Random Name (2).png");File.Copy(old,fresh);Require(Equals(Call("NewCompleted",dir,"Random Name.png",hash,before),fresh));
 Reject(()=>Call("NewCompleted",dir,"Random Name.png",new string('a',64),before));
 string duplicate=Path.Combine(dir,"Random Name (3).png");File.Copy(old,duplicate);Reject(()=>Call("NewCompleted",dir,"Random Name.png",hash,before));
 File.Delete(duplicate);File.WriteAllText(fresh+".crdownload","pending");Require(Call("NewCompleted",dir,"Random Name.png",hash,before)==null);
 File.Delete(fresh+".crdownload");File.Delete(fresh);File.Delete(old);Directory.Delete(dir);Console.WriteLine("PASS "+count+" native retained-download checks");}
}
