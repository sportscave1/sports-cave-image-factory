using System;
using System.Collections;
using System.Collections.Generic;
class ProductImageResultChecks {
 static void Require(bool value){if(!value)throw new Exception("Image policy assertion failed");}
 static void Main(){
  Require(ProductImageResult.Fresh(1,2,2,"Image copied"));
  Require(ProductImageResult.Fresh(1,2,2,"Sports Cave browser v2: metadata\nImage copied"));
  Require(!ProductImageResult.Fresh(1,2,2,"Metadata contains Image copied"));
  Require(!ProductImageResult.HasStatus("Image copied\nImage copied",ProductImageResult.Success));
  Require(ProductImageResult.HasStatus("Sports Cave browser v2: metadata\nCopy black frame to clipboard",ProductImageResult.Ready));
  Require(!ProductImageResult.Fresh(2,2,2,"Image copied"));
  Require(!ProductImageResult.Fresh(1,2,3,"Image copied"));
  Require(!ProductImageResult.Fresh(1,2,2,"Copying…"));
  Require(ProductImageResult.PixelBytes(1920,1080)==8294400);
  foreach(var size in new[]{0,-1,16385,int.MaxValue}) {bool rejected=false;try{ProductImageResult.PixelBytes(size,100);}catch{rejected=true;}Require(rejected);}
  bool oversized=false;try{ProductImageResult.PixelBytes(16384,16384);}catch{oversized=true;}Require(oversized);
  Require(ProductImageResult.KnownButton("chrome.exe","Button","copyImage","Copy black frame"));
  Require(!ProductImageResult.KnownButton("chrome.exe","Button","copyPrompt","Copy black frame"));
  Require(!ProductImageResult.KnownButton("other.exe","Button","copyImage","Copy black frame"));
  var expected=new ArrayList();var actual=new List<ProductCopyResult.ScopeAnchor>();
  foreach(var row in new[]{new[]{"Group","root",""},new[]{"Document","RootWebArea",""},new[]{"Document","sc-product-upload-copy",ProductCopyResult.Component}}) {
   var current=row;expected.Add(new Dictionary<string,object>{{"control_type",row[0]},{"automation_id",row[1]},{"name",row[2]}});
   actual.Add(new ProductCopyResult.ScopeAnchor(row[0],row[1],()=>current[2]));
  }
  for(int i=0;i<20;i++)actual.Add(new ProductCopyResult.ScopeAnchor("Group","",()=>"",()=>true));
  Require(ProductCopyResult.ScopeMatches(expected,actual));
  actual.Add(new ProductCopyResult.ScopeAnchor("Group","wrong",()=>"unrelated"));
  Require(!ProductCopyResult.ScopeMatches(expected,actual));
  var lease=new RunImageTransfer();
  bool missing=false;try{lease.Verify(()=>7,()=>"pixels");}catch{missing=true;}Require(missing);
  lease.Retain(7,"pixels");Require(lease.Verify(()=>7,()=>"pixels")=="pixels");
  bool changed=false;try{lease.Verify(()=>8,()=>"pixels");}catch{changed=true;}Require(changed&&!lease.Present);
  lease.Retain(7,"pixels");changed=false;try{lease.Verify(()=>7,()=>"other");}catch{changed=true;}Require(changed&&!lease.Present);
  lease.Retain(7,"pixels");int reads=0;changed=false;try{lease.Verify(()=>++reads==1?7u:8u,()=>"pixels");}catch{changed=true;}Require(changed&&!lease.Present);
  lease.Retain(7,"pixels");lease.Clear();Require(!lease.Present);
  lease.Retain(7,"pixels");changed=false;try{lease.Verify(()=>7,()=>{lease.Clear();return "pixels";});}catch{changed=true;}Require(changed&&!lease.Present);
  Require(ChatImageAttachment.Completed("image(20261029-034551).png",1,1,0));
  Require(!ChatImageAttachment.Completed("image.png",1,1,0));
  Require(!ChatImageAttachment.Completed("image(20261029-034551).png",1,1,1));
  Require(!ChatImageAttachment.Completed("image(20261029-034551).png",2,2,0));
  Require(!ChatImageAttachment.Completed("image(20261029-034551).png",1,0,0));
  foreach(uint vk in new uint[]{17,162,163,86}) Require(ChatImageAttachment.OwnPasteKey(16,ChatImageAttachment.InputTag,vk));
  Require(!ChatImageAttachment.OwnPasteKey(0,ChatImageAttachment.InputTag,162));
  Require(!ChatImageAttachment.OwnPasteKey(16,UIntPtr.Zero,162));
  Require(!ChatImageAttachment.OwnPasteKey(16,ChatImageAttachment.InputTag,65));
  Console.WriteLine("38 image-copy, ownership, attachment, input and ancestry policy checks passed");
 }
}
