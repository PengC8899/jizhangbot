import re
import ast
import operator
from telegram import Update
from telegram.ext import ContextTypes
import logging

logger = logging.getLogger(__name__)

# Supported operators for safe_eval
operators = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

def evaluate_expr(node):
    if isinstance(node, ast.Num): # Python < 3.8
        return node.n
    elif isinstance(node, ast.Constant): # Python 3.8+
        return node.value
    elif isinstance(node, ast.BinOp):
        return operators[type(node.op)](evaluate_expr(node.left), evaluate_expr(node.right))
    elif isinstance(node, ast.UnaryOp):
        return operators[type(node.op)](evaluate_expr(node.operand))
    else:
        raise TypeError(f"Unsupported operation: {type(node)}")

def safe_eval(expr: str):
    if len(expr) > 100:
        raise ValueError("算式过长")
        
    # Replace alternative math symbols
    expr = expr.replace('x', '*').replace('X', '*').replace('÷', '/').replace('=', '')
    
    # Strip leading zeros to avoid SyntaxError in ast.parse (e.g., 05 -> 5)
    # This regex removes leading zeros that are followed by a digit, and not preceded by a dot
    expr = re.sub(r'(?<!\.)\b0+(?=\d)', '', expr)
    
    # Parse the expression into an AST
    tree = ast.parse(expr, mode='eval').body
    return evaluate_expr(tree)

async def calculator_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle pure math expressions like 100+200, 50*4
    """
    raw_text = update.message.text or update.message.caption
    if not raw_text:
        return
        
    text = raw_text.strip()
    
    try:
        # Calculate
        result = safe_eval(text)
        
        # Format result to drop trailing zeros if integer
        if isinstance(result, float):
            if result.is_integer():
                result = int(result)
            else:
                result = round(result, 4)
                
        # Reply with the formula and result
        await update.message.reply_text(f"{text} = {result}")
    except ZeroDivisionError:
        await update.message.reply_text("计算错误：除数不能为 0")
    except Exception as e:
        logger.debug(f"Calculator failed to parse '{text}': {e}")
        # Silently ignore if it's not a valid expression to avoid spamming the group
        pass
