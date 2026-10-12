"""Explicit bounded chat commands; no model-generated authority or free code."""
import ast,hashlib,re,unicodedata
from pathlib import Path
from assistant_foundation.tasks import Tasks
from assistant_foundation.exact_tools import calculate

def normalized(text):return ''.join(c for c in unicodedata.normalize('NFKD',text.casefold()) if not unicodedata.combining(c)).replace('ı','i')

def expression(text):
 if len(text)>300 or not re.fullmatch(r'[0-9.,+*/()\s-]+',text):raise ValueError('INVALID_EXPRESSION')
 text=text.replace(',','.')
 tree=ast.parse(text,mode='eval')
 if len(list(ast.walk(tree)))>100:raise ValueError('EXPRESSION_TOO_COMPLEX')
 def visit(node):
  if isinstance(node,ast.Constant) and type(node.value) in (int,float):return ast.get_source_segment(text,node)
  if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.USub,ast.UAdd)):
   v=visit(node.operand);return calculate('multiply',['-1',v])['result'] if isinstance(node.op,ast.USub) else v
  if isinstance(node,ast.BinOp):
   ops={ast.Add:'add',ast.Sub:'subtract',ast.Mult:'multiply',ast.Div:'divide'}
   if type(node.op) not in ops:raise ValueError('UNKNOWN_OPERATOR')
   return calculate(ops[type(node.op)],[visit(node.left),visit(node.right)])['result']
  raise ValueError('INVALID_EXPRESSION')
 return visit(tree.body)

def handle(base,session,question):
 q=question.strip();n=normalized(q)
 if n.startswith('hesapla:') or n.startswith('hesapla '):
  text=q[len('hesapla'):].lstrip(' :')
  try:result=expression(text)
  except (ValueError,SyntaxError,ArithmeticError):
   return dict(route='TOOL_INPUT_ERROR',source='EXACT_TOOLS',grounded=True,answer='Hesaplayamadım. “Hesapla: 12 * 7 - 9” biçimini kullan. Yalnız +, -, *, / ve parantez desteklenir; sıfıra bölme yapılamaz.',tool_status='INVALID_INPUT')
  tool,args='calculate',dict(operation='add',operands=[result,'0'])
 elif n.startswith('json dogrula:'):
  tool,args='validate_json',dict(text=q.split(':',1)[1].strip())
 else:return None
 workspace=Path(base)/'assistant_tasks'/hashlib.sha256(session.encode()).hexdigest()
 tasks=Tasks(workspace);identity=tasks.submit(tool,args);record=tasks.execute(identity)
 ok=record['state']=='SUCCEEDED'
 answer=('Sonuç: '+record['result']['result']) if ok and tool=='calculate' else 'JSON geçerli.' if ok else 'JSON doğrulanamadı; biçim hatası, yinelenen anahtar veya desteklenmeyen değer olabilir.'
 return dict(route='LOCAL_TOOL',source='EXACT_TOOLS',grounded=True,answer=answer,tool_status=record['state'],tool_job_id=identity,tool_result=record['result'])
