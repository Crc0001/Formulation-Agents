const assert=require('node:assert/strict');
const {directoryCoverage}=require('../apps/web/src/directoryCoverage.ts');
const result=directoryCoverage({batches:[{batch:1,rows:3},{batch:2,rows:9}],sources:[
 {title:'第一批',status:'failed'},
 {title:'第二批',status:'failed'},
 {document_batch:2,sha256:'original',rows:20,status:'downloaded'},
 {title:'第三批',row_count:10,status:'rows_extracted_pending_review'},
 {title:'第四批征求意见稿',status:'draft'},
]});
assert.equal(result.length,3);
assert.equal(result[0].status,'missing'); // old entries do not establish coverage
assert.equal(result[1].status,'original'); // failed official URL does not hide alternate original
assert.equal(result[2].status,'table');
assert.equal(directoryCoverage({sources:[{title:'第一百零九批',status:'failed'}]}).length,109);
console.log('Directory coverage checks passed');
