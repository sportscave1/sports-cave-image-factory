const test=require('node:test'),assert=require('node:assert/strict');
const {prodigiShippingQuotes,prodigiCheapestShipping}=require('../windows-upload-companion/prodigi-dashboard-qa.js');
const select=rows=>({options:rows.map(([value,label,disabled=false])=>({value,textContent:label,disabled}))});
test('quoted shipping prices use cents, including ties and Express intent',()=>{
 const quotes=prodigiShippingQuotes(select([['budget','Budget: $10.07'],['standard','Standard: $10.07'],['express','Express: $23.04']]));
 assert.deepEqual(quotes.map(q=>q.cents),[1007,1007,2304]);
 assert.equal(prodigiCheapestShipping(quotes,'standard','standard'),'standard');
 quotes[0].cents=900;assert.equal(prodigiCheapestShipping(quotes,'standard','standard'),'budget');
 assert.equal(prodigiCheapestShipping(quotes,'express','budget'),'express');
});
test('unpriced, ambiguous and missing Express quotes stop instead of guessing',()=>{
 assert.throws(()=>prodigiShippingQuotes(select([['standard','Standard: calculated later']])));
 assert.throws(()=>prodigiCheapestShipping([{service:'budget',cents:100,currency:'$'}],'express','budget'));
 assert.throws(()=>prodigiCheapestShipping([{service:'budget',cents:100,currency:'$'},{service:'budget',cents:200,currency:'$'}],'standard','budget'));
});
