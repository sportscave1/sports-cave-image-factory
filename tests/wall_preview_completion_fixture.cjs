// Real theme markup/CSS/JS with Liquid product data replaced by a fixed test product.
const fs=require('fs');
function fixture(){
 let s=fs.readFileSync('shopify_theme/snippets/sc-wall-visualizer-v1.liquid','utf8').replace(/\r\n/g,'\n');
 s=s.slice(s.indexOf('<div\nid='));
 s=s.replace(/{%- assign sc_wall_rendered_sizes = false -%}[\s\S]*?{%- unless sc_wall_rendered_sizes -%}/,'');
 s=s.replace(/<script type="application\/json" data-sc-wall-product-data>[\s\S]*?<\/script>/,'<script type="application/json" data-sc-wall-product-data>'+JSON.stringify({options:['Size','Frame'],variants:[{id:456,available:true,options:['S - 21 × 30 cm (8.3 × 11.8 in)','Black Frame'],option1:'S - 21 × 30 cm (8.3 × 11.8 in)',option2:'Black Frame',price:12000}],formatted:{456:{price:'$120'}}})+'</script>');
 s=s.replace(/{% javascript %}/,'<script>').replace(/{% endjavascript %}/,'</script>');
 s=s.replace(/\{\{([^}]+)\}\}/g,(_,v)=>v.includes('sc_wall_id')?'fixture-wall':v.includes('_url')?'/art.png':v.includes('product.id')?'123':v.includes('product.handle')?'test-art':v.includes('product.title')?'Test artwork':v.includes('sc_wall_unit')?'cm':v.includes('edition_total')?'100':v.includes('edition_next')?'1':'');
 s=s.replace(/{%[\s\S]*?%}/g,'').replace('data-customer-logged-in="10"','data-customer-logged-in="0"').replace('data-edition-expired="10"','data-edition-expired="0"');
 return '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"><style>body{margin:0} .before{height:700px}</style><div class="before"></div>'+s+'<div style="height:1000px"></div>';
}
module.exports=fixture;

