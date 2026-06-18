import sys
import os
import re

try:
    from flask import Flask, render_template, request, jsonify
except ImportError:
    print("\n[ERRO] O Flask nao esta instalado! Digite 'pip install Flask' no terminal.\n")
    input("Pressione Enter para fechar...")
    sys.exit(1)

app = Flask(__name__)

# ==============================================================================
# INTERPRETADOR STUCK 0.4 (Mecanismo Web)
# ==============================================================================
class StuckInterpreterWeb:
    def __init__(self):
        self.global_vars = {}
        self.functions = {}
        self.output_buffer = []
        self.error = None
        self.current_line = 0

    def log(self, text):
        self.output_buffer.append(str(text))

    def raise_error(self, message):
        if not self.error:
            self.error = f"Erro linha {self.current_line}:\n{message}"
        raise Exception(message)

    def evaluate_term(self, term, scope_vars):
        term = term.strip()
        if not term: return None
        if term.startswith('"') and term.endswith('"'): return term[1:-1]
        if term in ("true", "verdadeiro"): return True
        if term in ("false", "falso"): return False
        if term.startswith('[') and term.endswith(']'):
            elements_raw = term[1:-1].split(',')
            return [self.evaluate_term(el, scope_vars) for el in elements_raw if el.strip()]
        if term in scope_vars: return scope_vars[term]
        if term in self.global_vars: return self.global_vars[term]
        if term.isdigit(): return int(term)
        try: return float(term)
        except ValueError: pass
        return term

    def evaluate_expression(self, expr, scope_vars):
        expr = expr.strip()
        if expr.startswith("len(") and expr.endswith(")"):
            lista = self.evaluate_expression(expr[4:-1].strip(), scope_vars)
            if isinstance(lista, list): return len(lista)
            self.raise_error("O argumento de len() precisa ser uma lista.")

        func_match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*)\)$', expr)
        if func_match and not expr.startswith("len("):
            f_name, f_args_raw = func_match.groups()
            if f_name in self.functions:
                args_tokens = [a.strip() for a in f_args_raw.split(",")] if f_args_raw.strip() else []
                evaluated_args = [self.evaluate_expression(a, scope_vars) for a in args_tokens]
                return self.call_function(f_name, evaluated_args)

        match = re.match(r'^([a-zA-Z0-9_\s"\'\.\[\],\-]+)\s*([\+\-\*/]|[<>]=?|==|!=)\s*\(\s*(.+)\s*\)$', expr)
        if match:
            t1_raw, op, t2_raw = match.groups()
            v1 = self.evaluate_expression(t1_raw, scope_vars)
            v2 = self.evaluate_expression(t2_raw, scope_vars)
            try:
                if op == '+': return v1 + v2
                if op == '-': return v1 - v2
                if op == '*': return v1 * v2
                if op == '/': return v1 // v2 if isinstance(v1, int) and isinstance(v2, int) else v1 / v2
                if op == '<': return "verdadeiro" if v1 < v2 else "falso"
                if op == '>': return "verdadeiro" if v1 > v2 else "falso"
                if op == '<=': return "verdadeiro" if v1 <= v2 else "falso"
                if op == '>=': return "verdadeiro" if v1 >= v2 else "falso"
                if op == '==': return "verdadeiro" if v1 == v2 else "falso"
                if op == '!=': return "verdadeiro" if v1 != v2 else "falso"
            except Exception as e:
                self.raise_error(f"Erro na operacao '{expr}': {str(e)}")
        return self.evaluate_term(expr, scope_vars)

    def call_function(self, func_name, args):
        func_data = self.functions[func_name]
        local_scope = {name: val for name, val in zip(func_data["params"], args)}
        _, returned_val = self.execute_block(func_data["body"], local_scope)
        return returned_val

    def execute_block(self, lines, scope_vars):
        idx = 0
        while idx < len(lines):
            raw_line, line_num = lines[idx]
            self.current_line = line_num
            line = raw_line.strip()
            if not line or line.startswith("//"):
                idx += 1
                continue
            if line.startswith("return "):
                return "return", self.evaluate_expression(line[7:].strip(), scope_vars)
            if line == "return":
                return "return", None
            if line.startswith("cot "):
                content = line[4:].strip()
                if "=" in content:
                    var_name, var_val = content.split("=", 1)
                    scope_vars[var_name.strip()] = self.evaluate_expression(var_val.strip(), scope_vars)
                idx += 1
                continue
            if line.startswith("aparec(") and line.endswith(")"):
                res = self.evaluate_expression(line[7:-1].strip(), scope_vars)
                if res is True: res = "verdadeiro"
                if res is False: res = "falso"
                self.log(res)
                idx += 1
                continue
            if line.startswith("push(") and line.endswith(")"):
                args_raw = line[5:-1].split(",", 1)
                if len(args_raw) == 2:
                    l_name = args_raw[0].strip()
                    item_val = self.evaluate_expression(args_raw[1].strip(), scope_vars)
                    lista = scope_vars.get(l_name, self.global_vars.get(l_name))
                    if isinstance(lista, list): lista.append(item_val)
                idx += 1
                continue

            if line.startswith(("if(", "repet(", "while(", "for(")) and line.endswith("){"):
                type_block = line.split("(")[0]
                body_tokens = []
                start_line = line
                idx += 1
                depth = 1
                while idx < len(lines) and depth > 0:
                    l_raw, l_num = lines[idx]
                    l_sub = l_raw.strip()
                    if "{" in l_sub: depth += l_sub.count("{")
                    if "}" in l_sub: depth -= l_sub.count("}")
                    if depth > 0: body_tokens.append((l_raw, l_num))
                    idx += 1
                else_body = []
                if type_block == "if" and idx < len(lines) and lines[idx][0].strip().startswith("else{"):
                    idx += 1
                    depth = 1
                    while idx < len(lines) and depth > 0:
                        l_raw, l_num = lines[idx]
                        l_sub = l_raw.strip()
                        if "{" in l_sub: depth += l_sub.count("{")
                        if "}" in l_sub: depth -= l_sub.count("}")
                        if depth > 0: else_body.append((l_raw, l_num))
                        idx += 1

                if type_block == "if":
                    cond_res = self.evaluate_expression(start_line[3:-2].strip(), scope_vars)
                    if cond_res in ("verdadeiro", True):
                        status, val = self.execute_block(body_tokens, scope_vars)
                    elif else_body:
                        status, val = self.execute_block(else_body, scope_vars)
                elif type_block == "repet":
                    loops = int(self.evaluate_expression(start_line[6:-2].strip(), scope_vars))
                    for _ in range(loops): self.execute_block(body_tokens, scope_vars)
                elif type_block == "while":
                    cond_str = start_line[6:-2].strip()
                    while self.evaluate_expression(cond_str, scope_vars) in ("verdadeiro", True):
                        self.execute_block(body_tokens, scope_vars)
                elif type_block == "for":
                    parts = start_line[4:-2].strip().split(";")
                    init_raw, cond_str, step_raw = parts
                    if "=" in init_raw:
                        i_name, i_val = init_raw.split("=", 1)
                        scope_vars[i_name.strip()] = self.evaluate_expression(i_val.strip(), scope_vars)
                    while self.evaluate_expression(cond_str, scope_vars) in ("verdadeiro", True):
                        self.execute_block(body_tokens, scope_vars)
                        scope_vars[i_name.strip()] = self.evaluate_expression(step_raw, scope_vars)
                continue
            idx += 1
        return "normal", None

    def run(self, source_code):
        self.global_vars, self.functions, self.output_buffer, self.error = {}, {}, [], None
        numbered_lines = [(line, index + 1) for index, line in enumerate(source_code.split("\n"))]
        filtered_lines = []
        idx = 0
        while idx < len(numbered_lines):
            line_str, line_num = numbered_lines[idx]
            line_strip = line_str.strip()
            if line_strip.startswith("func ") and line_strip.endswith("){"):
                header = line_strip[5:-2].strip()
                f_name, params_raw = header.split("(", 1)
                params = [p.strip() for p in params_raw.split(",") if p.strip()]
                f_body = []
                idx += 1
                depth = 1
                while idx < len(numbered_lines) and depth > 0:
                    l_raw, l_num = numbered_lines[idx]
                    l_sub = l_raw.strip()
                    if "{" in l_sub: depth += l_sub.count("{")
                    if "}" in l_sub: depth -= l_sub.count("}")
                    if depth > 0: f_body.append((l_raw, l_num))
                    idx += 1
                self.functions[f_name.strip()] = {"params": params, "body": f_body}
                continue
            filtered_lines.append((line_str, line_num))
            idx += 1

        clean_code = "".join([l[0].strip() for l in filtered_lines if l[0].strip() and not l[0].strip().startswith("//")])
        if not (clean_code.startswith("logical{") and clean_code.endswith("}")):
            return [], "Erro de Escopo:\nO programa deve estar dentro de 'logical{ ... }'."

        main_body = []
        inside = False
        for line_str, line_num in filtered_lines:
            if "logical{" in line_str.replace(" ", ""):
                inside = True
                continue
            if inside:
                if "}" in line_str: break
                main_body.append((line_str, line_num))

        try: self.execute_block(main_body, self.global_vars)
        except Exception: return self.output_buffer, self.error
        return self.output_buffer, None

# ==============================================================================
# ROTAS FLASK
# ==============================================================================
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/run', methods=['POST'])
def run_code():
    data = request.get_json()
    code = data.get('code', '')
    interpreter = StuckInterpreterWeb()
    output, error = interpreter.run(code)
    return jsonify({
        'output': "\n".join(output) if output else "",
        'error': error if error else ""
    })

if __name__ == '__main__':
    print("\n[SUCESSO] Servidor STUCK inciado com sucesso!")
    print("Abra o navegador e aceda a: http://127.0.0.1:5000\n")
    app.run(debug=True, host='0.0.0.0', port=5000)