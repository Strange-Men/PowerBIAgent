/* AST audit of explicit user-facing boundaries; no scan of tests/logs/schema. */
const fs=require('fs'),path=require('path'),ts=require('typescript')
const root=path.join(__dirname,'../src'),errors=[]
function scan(dir){for(const item of fs.readdirSync(dir,{withFileTypes:true})){
 const file=path.join(dir,item.name)
 if(item.isDirectory()){if(!['i18n','test'].includes(item.name))scan(file);continue}
 if(!/\.tsx?$/.test(file)||/\.test\./.test(file))continue
 const source=fs.readFileSync(file,'utf8'),sf=ts.createSourceFile(file,source,ts.ScriptTarget.Latest,true,file.endsWith('.tsx')?ts.ScriptKind.TSX:ts.ScriptKind.TS)
 function walk(node){
  const cjk=/[\u3400-\u9fff]/
  const visible=ts.isJsxText(node)&&/[a-zA-Z\u3400-\u9fff]/.test(node.text)&&node.text.trim()!=='PowerBIAgent'
  const hardcoded=(ts.isStringLiteralLike(node)||ts.isTemplateExpression(node))&&cjk.test(node.getText(sf))
  const attribute=node.parent&&ts.isJsxAttribute(node.parent)&&['title','aria-label','placeholder','alt'].includes(node.parent.name.getText(sf))
    && ts.isStringLiteralLike(node)&&/[a-zA-Z]/.test(node.text)&&!['PowerBIAgent','Power BI','Microsoft','Fabric IQ','DeepSeek'].includes(node.text)
  if(visible||hardcoded||attribute)errors.push(`${path.relative(root,file)}:${sf.getLineAndCharacterOfPosition(node.getStart(sf)).line+1}: hardcoded display string`)
  ts.forEachChild(node,walk)
 }
 walk(sf)
}}
scan(root)
if(errors.length){process.stderr.write(errors.join('\n')+'\n');process.exit(1)}
process.stdout.write('Frontend hardcoded display string audit: PASS\n')
