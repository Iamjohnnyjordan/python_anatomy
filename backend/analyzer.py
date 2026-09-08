"""Interpret a deliberately small Python subset without executing user code."""
import ast
import io
import math
import tokenize

from .models import Anatomy, AnatomyNode, SourceSpan, Connection


class AnalysisError(ValueError):
    pass


def analyze(source: str) -> Anatomy:
    if not source.strip() or len(source) > 10000:
        raise AnalysisError('Enter Python source using at most 10,000 characters.')
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise AnalysisError(f'Python could not parse this code: {exc}') from exc
    if sum(1 for _ in ast.walk(tree)) > 700:
        raise AnalysisError('Try a smaller program with fewer than 700 parts.')
    try:
        compile(tree, '<anatomy>', 'exec')  # Validate syntax only; never run the compiled code.
    except SyntaxError as exc:
        raise AnalysisError(str(exc)) from exc
    lines = source.splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))

    def offset(position):
        line, column = position
        return starts[line - 1] + column

    def ast_position(line, byte_column):
        # AST columns count UTF-8 bytes; the API counts Unicode characters.
        return line, len(lines[line - 1].encode('utf-8')[:byte_column].decode('utf-8'))

    def bounds(node):
        return (ast_position(node.lineno, node.col_offset),
                ast_position(node.end_lineno, node.end_col_offset))

    serial = 0

    def make(kind, label, explanation, relationship, start, end, children=None, value=None):
        nonlocal serial
        serial += 1
        return AnatomyNode(id=f'n{serial}', kind=kind, label=label,
                           explanation=explanation, relationship=relationship,
                           span=SourceSpan(start=offset(start), end=offset(end),
                                           start_line=start[0], start_column=start[1],
                                           end_line=end[0], end_column=end[1]),
                           children=children or [], value=value)

    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError) as exc:
        raise AnalysisError(str(exc)) from exc
    used = set()
    bindings = {}
    uses = []
    scope = ['module']
    scope_parent = {'module': None}
    scope_kind = {'module': 'module'}
    scope_receivers = {}
    scope_class = {}
    class_members = {}
    member_uses = []
    assignments_by_name = {}
    for instruction in tree.body:
        if isinstance(instruction, ast.Assign) and len(instruction.targets) == 1 and isinstance(instruction.targets[0], ast.Name):
            assignments_by_name.setdefault(instruction.targets[0].id, []).append(instruction.value)
    simple_instances = {name: values[0].func.id for name, values in assignments_by_name.items()
                        if len(values) == 1 and isinstance(values[0], ast.Call) and isinstance(values[0].func, ast.Name)}

    declared_classes = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}

    def enter_scope(name, kind, line):
        key = f'{scope[-1]}/{name}@{line}'
        parent = scope[-1]
        # A method resolves bare names in enclosing function/module scopes, not class attributes.
        if kind == 'function' and scope_kind[parent] == 'class':
            parent = scope_parent[parent]
        scope_parent[key] = parent
        scope_kind[key] = kind
        if kind == 'class':
            scope_class[key] = name
        elif kind == 'function' and scope_kind[scope[-1]] == 'class':
            scope_class[key] = scope_class[scope[-1]]
        scope.append(key)


    def bind(name, node):
        bindings.setdefault((scope[-1], name), []).append(node.id)


    def token_node(token, kind, explanation, relationship):
        used.add(token.start)
        return make(kind, token.string, explanation, relationship, token.start, token.end)

    def within(node):
        start, end = bounds(node)
        return [t for t in tokens if offset(start) <= offset(t.start) < offset(end)
                and t.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.ENDMARKER, tokenize.INDENT, tokenize.DEDENT, tokenize.COMMENT)]

    def build(node, relationship='assigned value', depth=0):
        if depth > 12:
            raise AnalysisError('This example is nested too deeply. Try fewer collections inside collections.')
        start, end = bounds(node)
        raw = source[offset(start):offset(end)]
        if isinstance(node, ast.BoolOp) or isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            is_not = isinstance(node, ast.UnaryOp)
            operator = 'not' if is_not else ('and' if isinstance(node.op, ast.And) else 'or')
            explanations = {
                'and': 'and checks values from left to right. It stops at the first falsy value and returns that value; if none is falsy, it returns the last value. In a condition, all parts must be truthy. Later parts may never run.',
                'or': 'or checks values from left to right. It stops at the first truthy value and returns that value; if none is truthy, it returns the last value. In a condition, one truthy part is enough. Later parts may never run.',
                'not': 'not reverses a truth test. It returns True for a falsy value and False for a truthy value. Unlike and and or, its result is always a Boolean.'}
            children = [build(value, 'value tested by ' + operator, depth + 1) for value in ([node.operand] if is_not else node.values)]
            for token in within(node):
                if token.start not in used and token.string == operator:
                    children.append(token_node(token, 'boolean_operator', explanations[operator], 'combines or reverses truth tests'))
            children.sort(key=lambda child: child.span.start)
            return make('boolean_logic', operator + ' logic', explanations[operator] + ' Falsy means treated as false: for example False, None, zero, or an empty collection. Other supported nonempty values are truthy.', relationship, start, end, children)
        if isinstance(node, ast.Name):
            is_target = isinstance(node.ctx, ast.Store)
            text = ('This variable name is chosen by the programmer. Here it receives a value.' if is_target else
                    'This name asks Python for the value currently associated with it. Connections show possible definitions in its scope, not a record of execution.')
            if node.id == scope_receivers.get(scope[-1]):
                text += ' In this instance method, this parameter refers to the object receiving the method call. The conventional name self is not a Python keyword.'
            if not is_target and node.id in ('print', 'input', 'open', 'len', 'range', 'str', 'int', 'float', 'bool', 'set', 'ValueError', 'OSError'):
                text += ' Python provides a built-in with this name, unless your code replaces it.'
            result = token_node(within(node)[0], 'name', text, relationship)
            if is_target:
                bind(node.id, result)
            else:
                uses.append((scope[-1], node.id, result.id))
            return result
        if isinstance(node, (ast.Call, ast.Attribute, ast.Subscript, ast.BinOp, ast.Compare)):
            children = []
            if isinstance(node, ast.Call):
                if any(k.arg is None for k in node.keywords) or any(isinstance(a, ast.Starred) for a in node.args):
                    raise AnalysisError('Argument unpacking with * or ** is not supported yet.')
                kind, label = 'call', 'Call ' + ast.unparse(node.func)
                explanation = 'A call asks a function or other callable to do its work. Arguments supply input values. The call may return a value to its surrounding expression.'
                if isinstance(node.func, ast.Name) and node.func.id in declared_classes:
                    explanation += ' The called name matches a class defined in this file. If it has not been rebound, calling it creates an object (an instance); Python normally calls __init__ to initialize that object.'
                elif isinstance(node.func, ast.Attribute):
                    member_help = {'append': 'For a list, append adds its argument as one new final item and returns None.', 'read': 'For a file object, read obtains content from its current position; text mode returns a string.', 'write': 'For a text file object, write sends the supplied string to the file and returns the number of characters written.', 'close': 'For a file object, close releases the file resource.', 'items': 'For a dictionary, items provides a view of its key/value pairs.'}
                    if node.func.attr in member_help:
                        explanation += ' ' + member_help[node.func.attr] + ' This interpretation depends on the receiver type at runtime.'
                    explanation += ' This calls a member accessed through an object or module. An instance method receives its object automatically when called through that instance; module functions do not receive a self argument.'
                if isinstance(node.func, ast.Name):
                    builtins_help = {
                        'print': 'The built-in print writes text to an output stream (normally the screen) and returns None.',
                        'input': 'The built-in input displays an optional prompt, waits for a line of user input, and returns a string. This analyzer does not ask for input.',
                        'open': 'The built-in open returns a file object. Mode "r" reads, "w" writes and replaces existing contents, and "a" appends. Opening can raise an exception. No file is opened by this analyzer.'}
                    if node.func.id in builtins_help:
                        explanation += ' If this built-in name has not been replaced: ' + builtins_help[node.func.id]
                children.append(build(node.func, 'callable being used', depth + 1))
                for index, arg in enumerate(node.args):
                    child = build(arg, 'value supplied to the call', depth + 1)
                    children.append(make('argument', f'Argument {index + 1}', 'An argument is a value supplied at a call site. A parameter is the receiving name in a function definition.', 'input to this call', *bounds(arg), [child]))
                for keyword in node.keywords:
                    child = build(keyword.value, 'value supplied for a named parameter', depth + 1)
                    ts = within(keyword)
                    name_part = token_node(ts[0], 'keyword_argument_name', 'This names the parameter receiving this argument. It is not a new variable assignment in the caller.', 'parameter selected by name')
                    equals = next(t for t in ts if t.string == '=')
                    equals_part = token_node(equals, 'keyword_argument_separator', 'Here = connects a named argument to its value inside a call. It is not a standalone assignment statement.', 'supplies named input')
                    children.append(make('argument', 'Named argument ' + keyword.arg, 'A keyword argument sends this value to the parameter with this name.', 'input to this call', *bounds(keyword), [name_part, equals_part, child]))
                punctuation = {'(': 'These parentheses start the arguments for this call. They do not define a function.', ')': 'This parenthesis ends the arguments for this call.', ',': 'This comma separates arguments supplied to the call.'}
            elif isinstance(node, ast.Attribute):
                kind, label = 'attribute', 'Attribute ' + node.attr
                explanation = 'Attribute access asks the object or module on the left for the named member on the right. Whether that member is a method or another value depends on that object.'
                children.append(build(node.value, 'object or module being accessed', depth + 1))
                token = within(node)[-1]
                attr_text = 'This names a member on the object or module before the dot. It is not a separate variable lookup.'
                if isinstance(node.ctx, ast.Store):
                    attr_text += ' Here assignment stores a value in this attribute.'
                    explanation = 'This assignment target stores a value in an attribute of the object on the left. For self.name inside an instance method, it stores data on that instance.'
                member = token_node(token, 'attribute_name', attr_text, 'requested member')
                children.append(member)
                owner_class = None
                if isinstance(node.value, ast.Name):
                    if node.value.id == scope_receivers.get(scope[-1]):
                        owner_class = scope_class.get(scope[-1])
                    elif scope[-1] == 'module':
                        owner_class = simple_instances.get(node.value.id)
                if owner_class:
                    if isinstance(node.ctx, ast.Store):
                        class_members.setdefault((owner_class, node.attr), []).append(member.id)
                    else:
                        member_uses.append((owner_class, node.attr, member.id))
                punctuation = {'.': 'This dot connects the object or module to the attribute name requested from it.'}
            elif isinstance(node, ast.Subscript):
                if isinstance(node.slice, ast.Slice):
                    raise AnalysisError('Slicing comes later. Use one key or index for now.')
                kind, label = 'lookup', 'Look up an item'
                explanation = 'This retrieves an item from the value on the left. A dictionary uses a key; a list or tuple uses an index. These brackets perform a lookup instead of creating a list.'
                children = [build(node.value, 'collection being read', depth + 1), build(node.slice, 'key or index to look up', depth + 1)]
                punctuation = {'[': 'This bracket starts the key or index for an item lookup.', ']': 'This bracket ends this item lookup.'}
            elif isinstance(node, ast.BinOp):
                if not isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.BitAnd, ast.BitOr, ast.BitXor, ast.LShift, ast.RShift, ast.MatMult)):
                    raise AnalysisError('This increment supports +, -, *, and / calculations.')
                kind, label = 'calculation', 'Calculation'
                explanation = 'Python combines the left and right values with this operator. The result can be used by the surrounding statement.'
                children = [build(node.left, 'left value', depth + 1), build(node.right, 'right value', depth + 1)]
                punctuation = {'+': 'Here + combines two values: addition for numbers, or concatenation for compatible sequences such as strings.', '-': 'Here - subtracts the right number from the left number.', '*': 'Here * multiplies numbers, or repeats a sequence when paired with an integer.', '/': 'Here / divides the left number by the right number.', '//': 'Floor division rounds the quotient down toward negative infinity.', '%': 'For numbers, % gives a remainder paired with floor division; strings also support a formatting operation with this symbol.', '**': 'This raises the left number to the power on the right.', '&': 'This is bitwise AND for integers; sets use it for intersection. It is different from Boolean and.', '|': 'This is bitwise OR for integers; sets use it for union. It is different from Boolean or.', '^': 'This is bitwise exclusive OR for integers; sets use it for symmetric difference, not exponentiation.', '<<': 'This shifts integer bits left.', '>>': 'This shifts integer bits right.', '@': 'This is the matrix multiplication operator for objects that support it. Ordinary Python lists do not implement matrix multiplication.'}
            else:
                if any(not isinstance(op, (ast.In, ast.NotIn, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Is, ast.IsNot)) for op in node.ops):
                    raise AnalysisError('This comparison is not supported yet.')
                kind, label = 'comparison', 'Comparison'
                explanation = 'This tests a relationship between values. The supported built-in values produce True or False. Chained comparisons test adjacent pairs.'
                children = [build(node.left, 'first compared value', depth + 1)] + [build(c, 'compared value', depth + 1) for c in node.comparators]
                punctuation = {'in': 'Here in tests membership. For a dictionary it checks keys, not values.', 'not': 'Here not negates the membership or identity comparison in not in or is not.', '==': 'This tests equality; it does not assign a value.', '!=': 'This tests whether two values are unequal.', '<': 'This tests whether the left value is smaller.', '<=': 'This tests whether the left value is smaller or equal.', '>': 'This tests whether the left value is greater.', '>=': 'This tests whether the left value is greater or equal.', 'is': 'is tests whether two expressions refer to the very same object, not merely equal values. Use == for value equality.'}
            remaining = [t for t in within(node) if t.start not in used]
            if isinstance(node, ast.Call) and (sum(t.string == '(' for t in remaining) != 1 or sum(t.string == ')' for t in remaining) != 1):
                raise AnalysisError('Extra grouping parentheses come later. Use a simple call for now.')
            for token in remaining:
                if any(c.span.start <= offset(token.start) < c.span.end for c in children):
                    continue
                if token.string in punctuation:
                    children.append(token_node(token, 'syntax', punctuation[token.string], 'syntax of ' + kind))
            children.sort(key=lambda child: child.span.start)
            return make(kind, label, explanation, relationship, start, end, children)
        if isinstance(node, ast.Constant):
            kind = {str: 'string', int: 'integer', float: 'float', bool: 'boolean', type(None): 'none'}.get(type(node.value))
            if kind is None:
                raise AnalysisError('This version supports text, whole numbers, decimal numbers, True, False, and None.')
            ts = within(node)
            if len(ts) != 1:
                raise AnalysisError('Use one quoted string at a time; adjacent string literals come later.')
            token = ts[0]
            used.add(token.start)
            children = []
            if kind == 'string':
                if raw[:1] not in ('"', "'") or raw.startswith(('"""', "\'\'\'")):
                    raise AnalysisError('Use ordinary single or double quotes for now, without prefixes or triple quotes.')
                children = [
                    make('quote', raw[0], 'This opening quote begins a string: a text value. The quote is syntax, not part of the stored text.', 'opens text', start, (start[0], start[1] + 1)),
                    make('quote', raw[-1], 'This closing quote ends the string and matches the opening quote. It is not part of the stored text.', 'closes text', (end[0], end[1] - 1), end)]
                explanation = f'This string is the text value {node.value!r}. Python calls its type str. Quotes distinguish text from a variable name.'
            elif kind == 'integer':
                explanation = f'This integer is the whole number {node.value}. Python calls its type int. Without quotes it is a number, not text.'
            elif kind == 'float':
                if not math.isfinite(node.value):
                    raise AnalysisError('This decimal number is too large to represent as a finite float. Try a smaller number.')
                explanation = f'This floating-point number has value {node.value}. Python calls its type float. It can represent fractional quantities, though many decimal values are stored approximately.'
            elif kind == 'boolean':
                explanation = f'{raw} is a Boolean value: one of True or False. Python calls this type bool. The spelling and capital letter are required; this is not a name you chose.'
            else:
                explanation = 'None is Python’s special value for no value being provided. It is different from zero, False, and an empty string. This spelling is required; it is not a name you chose.'
            return make(kind, raw, explanation, relationship, start, end, children, node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            if not isinstance(node.operand, ast.Constant) or type(node.operand.value) not in (int, float):
                raise AnalysisError('For now, a + or - sign must be directly before a number.')
            operand = build(node.operand, 'number affected by the sign', depth + 1)
            token = within(node)[0]
            sign = token_node(token, 'sign_operator',
                'Here - changes the sign of the following number; it is not subtraction between two values.' if isinstance(node.op, ast.USub)
                else 'Here + keeps the following number’s sign unchanged; it is not addition between two values.', 'sign applied to number')
            return make('signed_number', 'Signed number', 'The sign acts on the number beside it. Together they form one numeric expression.', relationship, start, end, [sign, operand])
        if not isinstance(node, (ast.List, ast.Tuple, ast.Dict, ast.Set)):
            raise AnalysisError(f'{type(node).__name__} expression syntax is not supported yet. Try a simpler expression using the supported values, collections, calls, or operators.')
        kind = {ast.List:'list', ast.Tuple:'tuple', ast.Dict:'dictionary', ast.Set:'set'}[type(node)]
        explanations = {
            'list': 'A list holds items in order. You can change, add, or remove items. Python indexes (positions) start at 0.',
            'tuple': 'A tuple holds items in order. Its item references cannot be replaced after creation. Commas form a nonempty tuple; a one-item tuple needs a comma. Empty parentheses create an empty tuple.',
            'dictionary': 'A dictionary connects keys to values. Use a key, such as "Milk", to look up its value. Empty braces {} create an empty dictionary. Repeating a key replaces its earlier value.',
            'set': 'A set holds unique items without numbered positions. Repeated equal values become one item. Braces containing values without key:value pairs create a set. Empty braces {} create a dictionary, not a set.'}
        children = []
        if kind == 'dictionary':
            for index, (key, value) in enumerate(zip(node.keys, node.values)):
                if key is None:
                    raise AnalysisError('Dictionary unpacking with ** comes later. Use key: value pairs for now.')
                if not hashable(key):
                    raise AnalysisError('Dictionary keys must be hashable: use a basic value or a tuple of hashable values, not a list, dictionary, or set.')
                k = build(key, 'key used to look up this value', depth + 1)
                v = build(value, 'value associated with this key', depth + 1)
                colon = next(t for t in tokens if t.string == ':' and k.span.end <= offset(t.start) < v.span.start)
                c = token_node(colon, 'key_value_separator', 'In this dictionary entry, : separates the lookup key on the left from its associated value on the right.', 'connects key to value')
                children.append(make('entry', f'Entry {index + 1}', 'This dictionary entry connects one key to one value. The entry number is a reading aid, not a dictionary index.', 'key and value pair', bounds(key)[0], bounds(value)[1], [k, c, v]))
        else:
            for index, element in enumerate(node.elts):
                if kind == 'set' and not hashable(element):
                    raise AnalysisError('Set items must be hashable: use basic values or tuples of hashable values, not lists, dictionaries, or sets.')
                child = build(element, 'item value', depth + 1)
                label = f'Written item {index + 1}' if kind == 'set' else f'Item at index {index}'
                explanation = ('This is an item written in the set display. This number only indicates its source order; sets have no indexes, and duplicate values collapse.' if kind == 'set' else
                               f'This item has index {index}, meaning position {index + 1}. Python counts positions from 0. An item is a value contained in this {kind}.')
                children.append(make('element', label, explanation, 'contained item', *bounds(element), [child]))
        for token in within(node):
            if token.start in used:
                continue
            if token.string == ',':
                explanation = ('This comma forms a tuple and separates its items. A single item needs a comma to be a tuple.' if kind == 'tuple' else f'This comma separates {"entries" if kind == "dictionary" else "items"} in this {kind}. A final comma is optional.')
                children.append(token_node(token, 'separator', explanation, 'separates entries' if kind == 'dictionary' else 'separates items'))
            elif (token.start == start or token.end == end) and token.string in {'list': ('[', ']'), 'tuple': ('(', ')'), 'dictionary': ('{', '}'), 'set': ('{', '}')}[kind]:
                explanation = f'This {"opening" if token.string in "[({" else "closing"} delimiter marks the boundary of this {kind}.'
                if kind == 'tuple':
                    explanation += ' These parentheses enclose a tuple here; they do not mean a function.'
                children.append(token_node(token, kind + '_delimiter', explanation, f'{kind} boundary'))
        children.sort(key=lambda child: child.span.start)
        return make(kind, kind.title(), explanations[kind], relationship, start, end, children)

    def hashable(node):
        # Recognize supported hashable shapes without evaluating user code.
        if isinstance(node, ast.Constant):
            return type(node.value) in (str, int, float, bool, type(None))
        if isinstance(node, ast.UnaryOp):
            return isinstance(node.op, (ast.USub, ast.UAdd)) and isinstance(node.operand, ast.Constant) and type(node.operand.value) in (int, float)
        return isinstance(node, ast.Tuple) and all(hashable(child) for child in node.elts)

    def describe_step(node):
        # Summarize the written instructions, without guessing business intent or running them.
        if isinstance(node, ast.Assign):
            return f'Set {ast.unparse(node.targets[0])} to the value of {ast.unparse(node.value)}.'
        if isinstance(node, ast.For):
            inside = ' '.join(describe_step(child) for child in node.body)
            return f'For each item in {ast.unparse(node.iter)}, use the variable name {ast.unparse(node.target)}. For that item: {inside}'
        if isinstance(node, ast.If):
            text = f'If {ast.unparse(node.test)} is true: ' + ' '.join(describe_step(child) for child in node.body)
            if node.orelse:
                text += ' Otherwise: ' + ' '.join(describe_step(child) for child in node.orelse)
            return text
        if isinstance(node, ast.While):
            return f'Before each repetition, test {ast.unparse(node.test)}. If truthy: ' + ' '.join(describe_step(child) for child in node.body)
        if isinstance(node, ast.Break):
            return 'Exit the nearest enclosing loop immediately.'
        if isinstance(node, ast.Continue):
            return 'Skip the rest of this repetition and continue with the nearest enclosing loop.'
        if isinstance(node, ast.Return):
            return f'Send {ast.unparse(node.value) if node.value else "None"} back to the code that called this function, ending this call.'
        if isinstance(node, ast.Expr):
            return f'Evaluate {ast.unparse(node.value)}.'
        return 'Follow this instruction in the block.'

    def statement(node, depth=0):
        if depth > 12:
            raise AnalysisError('Try fewer nested blocks.')
        children = []
        punctuation = {}
        start, end = bounds(node)
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], (ast.Name, ast.Attribute, ast.Subscript)):
                raise AnalysisError('For now, use one variable, attribute, or collection-item target on the left. Assignment unpacking and chained targets are not supported.')
            kind, label = 'assignment', 'Assign ' + ast.unparse(node.targets[0])
            explanation = 'Python works out the value on the right, then stores it in the target on the left. A target can be a variable name, object attribute, or collection item.'
            children = [build(node.targets[0], 'variable receiving the value'), build(node.value)]
            value_kind = children[1].kind
            descriptions = {'dictionary': 'a dictionary, which connects keys to values', 'list': 'a list, which holds items in order', 'tuple': 'a tuple, which holds items in order with fixed item references', 'set': 'a set, which holds unique items without indexes', 'string': 'a string (text)', 'integer': 'an integer (a whole number)', 'float': 'a float (a floating-point number)', 'boolean': 'a Boolean (True or False)', 'none': 'None (the special value for no value provided)'}
            if value_kind in descriptions:
                explanation += f' Here the right side creates or supplies {descriptions[value_kind]}. The target {ast.unparse(node.targets[0])} receives that value. Assignment is the action; {value_kind} describes the value, not a permanent type restriction on the variable.'
            elif value_kind == 'call':
                explanation += ' Here the right side is a call. Its returned value is assigned to the variable; this source analysis does not infer the returned type.'
            punctuation = {'=': 'Here = assigns the value on the right to the variable name on the left. It does not test equality.'}
        elif isinstance(node, ast.AugAssign):
            if not isinstance(node.target, (ast.Name, ast.Attribute, ast.Subscript)):
                raise AnalysisError('Use a variable, attribute, or item as the update target.')
            kind, label = 'augmented_assignment', 'Update ' + ast.unparse(node.target)
            explanation = 'This reads the target, combines it with the right-side value, and writes the result back. Some objects update in place. The target is evaluated once, so it is not always identical to rewriting an ordinary assignment.'
            children = [build(node.target, 'target read and updated', depth + 1), build(node.value, 'value used in the update', depth + 1)]
            punctuation = {symbol: 'This combines an operation with assignment. For example, += adds or extends and assigns the result back to the target.' for symbol in ('+=','-=','*=','/=','//=','%=','**=','&=','|=','^=','<<=','>>=','@=')}
        elif isinstance(node, ast.ClassDef):
            if node.decorator_list or node.keywords or getattr(node, 'type_params', []):
                raise AnalysisError('Class decorators, metaclass keywords, and type parameters are not supported yet.')
            kind, label = 'class', 'Class ' + node.name
            explanation = 'A class defines a type of object, grouping data and behavior. Its body runs when the definition is reached; method bodies run when called. Calling the class normally creates an instance (an individual object).'
            name = token_node(within(node)[1], 'class_name', 'This is the class name chosen by the programmer. Calling this class normally creates an instance.', 'name of this object type')
            bind(node.name, name)
            children = [name] + [build(base, 'base class inherited from', depth + 1) for base in node.bases]
            enter_scope(node.name, 'class', node.lineno)
            children.extend(statement(child, depth + 1) for child in node.body)
            scope.pop()
            punctuation = {'class': 'The keyword class begins a class definition.', ':': 'This colon introduces the indented class body.', '(': 'These parentheses enclose base classes to inherit from, not function arguments.', ')': 'This parenthesis ends the base-class list.', ',': 'This comma separates base classes.'}
        elif isinstance(node, ast.FunctionDef):
            args = node.args
            if node.decorator_list or node.returns or args.posonlyargs or args.kwonlyargs or args.vararg or args.kwarg or any(a.annotation for a in args.args) or getattr(node, 'type_params', []):
                raise AnalysisError('Annotations, decorators, positional-only/keyword-only and variadic parameter forms are not supported yet. Plain parameters and defaults are supported.')
            is_method = scope_kind[scope[-1]] == 'class'
            kind, label = ('method', 'Method ' + node.name) if is_method else ('function', 'Function ' + node.name)
            explanation = 'This defines reusable instructions. Defining the function does not run its body; calling it does. Parameters are local names that receive argument values for each call.'
            if is_method:
                explanation += ' A function defined in a class is available as a method. When called through an instance, its first parameter receives that instance automatically.'
            if is_method and node.name == '__init__':
                explanation += ' __init__ is a special method Python normally calls to initialize a newly created instance. It sets up the object; it does not itself create the instance and must return None.'
            name = token_node(within(node)[1], 'function_name', 'This names the method Python normally calls to initialize a new instance.' if is_method and node.name == '__init__' else 'This is a callable name chosen by the programmer.', 'name of this callable')
            bind(node.name, name)
            if is_method:
                class_members.setdefault((scope_class[scope[-1]], node.name), []).append(name.id)
            children.append(name)
            # Default expressions belong to the enclosing scope and run at definition time.
            defaults = []
            for default in args.defaults:
                value = build(default, 'default input evaluated when the definition runs', depth + 1)
                defaults.append(make('default_value', 'Default input', 'This default is evaluated once when the function is defined, not each time it is called. It is used when the caller omits this argument. Mutable defaults are shared across calls.', 'optional argument fallback', *bounds(default), [value]))
            children.extend(defaults)
            enter_scope(node.name, 'function', node.lineno)
            if is_method and args.args:
                scope_receivers[scope[-1]] = args.args[0].arg
            for index, arg in enumerate(args.args):
                description = 'This parameter is a local variable name. It receives an argument value when this function is called.'
                if is_method and index == 0:
                    description += ' When the method is called through an instance, Python supplies that instance here automatically. self is the conventional name, not a keyword; another valid name would work.'
                param = token_node(within(arg)[0], 'parameter', description, 'input received by callable')
                bind(arg.arg, param)
                children.append(param)
            children.extend(statement(child, depth + 1) for child in node.body)
            scope.pop()
            punctuation = {'def': 'The keyword def begins a function or method definition.', '(': 'These parentheses start the parameter list in this definition, not a function call.', ')': 'This parenthesis ends the parameter list.', ',': 'This comma separates parameters.', ':': 'This colon introduces the indented callable body.', '=': 'Here = supplies a default parameter value, used if the caller omits that argument.'}
        elif isinstance(node, (ast.For, ast.While, ast.If)):
            if isinstance(node, ast.For):
                if not isinstance(node.target, ast.Name) or node.orelse:
                    raise AnalysisError('For now, use a for loop with one variable name and no loop else block.')
                kind, label = 'for_loop', 'For each ' + node.target.id
                explanation = 'This loop visits the iterable one item at a time. Each item is assigned to the loop variable, then the indented body runs. A dictionary iterates over its keys.'
                children = [build(node.target, 'variable receiving each item'), build(node.iter, 'values being visited')]
                punctuation = {'for': 'The keyword for starts this loop.', 'in': 'Here in separates the loop variable from the iterable supplying items; it is not a membership test.', ':': 'This colon introduces the indented loop body.'}
            elif isinstance(node, ast.While):
                if node.orelse:
                    raise AnalysisError('Loop else blocks come later. Use while without else for now.')
                kind, label = 'while_loop', 'While condition'
                explanation = 'A while loop checks its condition before each repetition. When the condition is truthy, its indented body runs and Python checks again. It can run zero times. A changing condition or break is needed to stop a loop whose condition stays true.'
                children = [build(node.test, 'condition checked before each repetition')]
                punctuation = {'while': 'The keyword while repeats this block while its condition is truthy (treated as true).', ':': 'This colon introduces the indented while-loop body.'}
            else:
                kind, label = 'if_statement', 'If condition'
                explanation = 'Python tests the condition. It runs the indented body only when the condition is truthy; otherwise it can run an else branch.'
                children = [build(node.test, 'condition deciding whether to enter')]
                punctuation = {'if': 'The keyword if starts a conditional branch.', 'elif': 'The keyword elif tests another condition if earlier branches did not match.', 'else': 'The keyword else introduces the alternative when earlier conditions do not match.', ':': 'This colon introduces an indented branch body.'}
            children.extend(statement(child, depth + 1) for child in node.body)
            if node.orelse:
                children.extend(statement(child, depth + 1) for child in node.orelse)
        elif isinstance(node, (ast.Break, ast.Continue)):
            kind = 'break' if isinstance(node, ast.Break) else 'continue'
            label = 'Stop this loop' if kind == 'break' else 'Skip to the next repetition'
            explanation = ('break exits the nearest enclosing loop immediately. Python resumes after that loop, not necessarily after the function.' if kind == 'break' else 'continue skips the remaining statements in the nearest enclosing loop body. A while loop checks its condition again; a for loop asks for the next item. It does not exit the loop.')
            punctuation = {kind: explanation}
        elif isinstance(node, ast.Return):
            kind, label = 'return', 'Return a result'
            explanation = 'Return ends this function call and sends a value back to the caller. Without a value, it returns None.'
            if node.value:
                children.append(build(node.value, 'value sent back to caller'))
            punctuation = {'return': 'This keyword ends the current function call and returns its result.'}
        elif isinstance(node, ast.Expr):
            kind, label = 'expression_statement', 'Use an expression'
            explanation = 'This evaluates an expression as a statement. A call such as print can have an effect even when its returned value is not saved.'
            children = [build(node.value, 'expression being evaluated')]
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            if any(alias.name == '*' for alias in node.names):
                raise AnalysisError('Wildcard imports obscure individual bindings; use explicit imported names here.')
            kind, label = 'import', ast.unparse(node)
            explanation = ('from selects a module, then import makes particular members available by name. An alias after as chooses a local name. This analyzer does not load the module.' if isinstance(node, ast.ImportFrom) else 'import loads a module when this code runs. An alias after as chooses the local name. Importing a dotted path without an alias binds its first component. This analyzer does not perform the import.')
            for alias in node.names:
                ts = within(alias)
                alias_children = []
                as_seen = False
                for token in ts:
                    if token.string == 'as':
                        as_seen = True
                        alias_children.append(token_node(token, 'syntax', 'Here as introduces the local name chosen for this import.', 'import alias syntax'))
                    elif token.string == '.':
                        alias_children.append(token_node(token, 'syntax', 'This dot separates parts of a module path, not an object attribute expression.', 'module path separator'))
                    else:
                        alias_children.append(token_node(token, 'import_alias' if as_seen else 'import_name', 'This is the local name chosen for the import.' if as_seen else 'This names the module or member being imported.', 'imported name'))
                binding = alias_children[-1] if alias.asname else alias_children[0]
                bind(alias.asname or (alias.name if isinstance(node, ast.ImportFrom) else alias.name.split('.')[0]), binding)
                children.append(make('import_item', alias.asname or alias.name, 'This part identifies one imported module or member and its optional local alias.', 'name introduced by import', *bounds(alias), alias_children))
            for token in within(node):
                if token.start in used:
                    continue
                text = {'from': 'from identifies the module that supplies the following imported members.', 'import': 'import requests modules or selected members.', ',': 'This comma separates imported names.', '.': 'This dot belongs to the module path; leading dots mean a relative import.', '(': 'These parentheses group a multiline import list.', ')': 'This parenthesis ends the grouped import list.'}.get(token.string, 'This names a module in the import source path.')
                children.append(token_node(token, 'syntax' if token.type == tokenize.OP or token.string in ('from','import') else 'module_name', text, 'import source syntax'))
        elif isinstance(node, ast.With):
            kind, label = 'with_statement', 'Managed resource (with)'
            explanation = 'with enters a context manager and arranges its exit when the block finishes, including when an exception happens. For a file opened with open, this ensures the file is closed. Other context managers may have different entry/exit behavior.'
            for item in node.items:
                context = build(item.context_expr, 'resource or context manager to enter', depth + 1)
                children.append(context)
                if item.optional_vars:
                    children.append(build(item.optional_vars, 'name receiving the entered resource', depth + 1))
            children.extend(statement(child, depth + 1) for child in node.body)
            punctuation = {'with': 'with begins managed use of a resource or context manager.', 'as': 'Here as binds the value returned by entering the context manager to this target.', ':': 'This colon introduces the block using the managed resource.', ',': 'This comma separates context managers entered in order.'}
        elif isinstance(node, ast.Try):
            kind, label = 'try_statement', 'Handle possible errors'
            explanation = 'try runs its body. If an exception occurs, Python looks for a matching except handler. else runs only if the try body finishes normally; finally runs as control leaves the statement, whether it succeeded or failed.'
            children = [statement(child, depth + 1) for child in node.body]
            children.extend(statement(handler, depth + 1) for handler in node.handlers)
            for block_name, body in [('else', node.orelse), ('finally', node.finalbody)]:
                if not body:
                    continue
                first_start = offset(bounds(body[0])[0])
                keyword = next(t for t in reversed(within(node)) if t.string == block_name and offset(t.start) < first_start)
                block_children = [statement(child, depth + 1) for child in body]
                text = 'This block runs only after the try body finishes normally, without an exception or early exit.' if block_name == 'else' else 'This cleanup block runs as control leaves the try statement, even during an exception or return. An abrupt process termination can prevent cleanup.'
                key = token_node(keyword, 'syntax', text, 'exception handling branch')
                colon = next(t for t in within(node) if t.string == ':' and offset(keyword.end) <= offset(t.start) < first_start)
                colon_node = token_node(colon, 'syntax', 'This colon introduces the indented ' + block_name + ' block.', 'block boundary')
                children.append(make('exception_branch', block_name.title() + ' block', text, 'exception handling branch', keyword.start, bounds(body[-1])[1], [key, colon_node, *block_children]))
            punctuation = {'try': 'try begins a block whose exceptions may be handled here.', ':': 'This colon introduces the try body.'}
        elif isinstance(node, ast.ExceptHandler):
            kind, label = 'except_handler', 'Catch ' + (ast.unparse(node.type) if node.type else 'any exception')
            explanation = 'This handler runs if the try body raises an exception matching its type. Matching includes subclasses. The exception object can be given a temporary name after as; Python clears that name at the end of this handler.'
            if node.type:
                children.append(build(node.type, 'exception type to catch', depth + 1))
            if node.name:
                token = next(t for t in within(node) if t.type == tokenize.NAME and t.string == node.name and offset(t.start) > (children[0].span.end if children else 0))
                name = token_node(token, 'name', 'This temporary variable refers to the caught exception object. Python clears it when this handler ends.', 'caught exception')
                bind(node.name, name)
                children.append(name)
            children.extend(statement(child, depth + 1) for child in node.body)
            punctuation = {'except': 'except introduces an exception handler.', 'as': 'Here as names the caught exception object temporarily.', ':': 'This colon introduces the handler body.'}
        elif isinstance(node, ast.Raise):
            kind, label = 'raise', 'Raise an exception'
            explanation = 'raise signals an exception and interrupts normal flow so Python can search for a handler. A bare raise re-raises the currently handled exception and fails if there is none.'
            if node.exc:
                children.append(build(node.exc, 'exception being raised', depth + 1))
            if node.cause:
                children.append(build(node.cause, 'explicit exception cause', depth + 1))
            punctuation = {'raise': 'raise signals an exception.', 'from': 'Here from specifies the cause of this exception; from None suppresses its displayed context.'}
        elif isinstance(node, ast.Pass):
            kind, label = 'pass', 'Do nothing (pass)'
            explanation = 'pass does nothing. It fills a block where Python requires a statement but no action is needed yet.'
            punctuation = {'pass': explanation}
        else:
            raise AnalysisError(f'{type(node).__name__} support comes later. This increment covers assignments, simple imports and functions, for loops, if branches, returns, and calls.')
        for token in within(node):
            if any(c.span.start <= offset(token.start) < c.span.end for c in children):
                continue
            if token.start not in used and token.string in punctuation:
                children.append(token_node(token, 'assignment_operator' if token.string == '=' else 'syntax', punctuation[token.string], 'syntax of ' + kind))
        children.sort(key=lambda child: child.span.start)
        result = make(kind, label, explanation, 'instruction in this block', start, end, children)
        if isinstance(node, ast.FunctionDef):
            parameters = ', '.join(arg.arg for arg in node.args.args)
            result.overview = [
                f'Inputs: {parameters}. These parameter names receive the values supplied by the caller.' if parameters else 'Inputs: this function has no parameters.',
                *[describe_step(child) for child in node.body],
                'When it runs: the body runs when the function is called, not when Python first reads the definition. Reaching the end without return gives None.'
            ]
        elif isinstance(node, (ast.For, ast.While, ast.If, ast.Assign, ast.Return, ast.Break, ast.Continue)):
            result.overview = [describe_step(node)]
        return result

    children = [statement(node) for node in tree.body]
    significant = [t for t in tokens if t.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.ENDMARKER, tokenize.INDENT, tokenize.DEDENT, tokenize.COMMENT)]
    if any(t.start not in used for t in significant):
        raise AnalysisError('Some syntax in this program is not supported yet. Try removing extra grouping parentheses or other additional syntax.')
    if len(children) == 1 and isinstance(tree.body[0], ast.Assign) and not any(t.type == tokenize.COMMENT for t in tokens):
        root = children[0]
    else:
        end = (len(lines), len(lines[-1].rstrip('\r\n')))
        root = make('module', 'Whole program', 'A module is a Python file. Its top-level instructions run in order. Function bodies run when called. Explore a part to see the instructions and syntax inside it.', 'complete Python source', (1, 0), end, children)
    def attach_trivia(piece):
        containers = []
        def visit(node):
            if node.span.start <= piece.span.start and piece.span.end <= node.span.end:
                containers.append(node)
                for child in node.children:
                    visit(child)
        visit(root)
        parent = min(containers, key=lambda n: n.span.end - n.span.start) if containers else root
        parent.children.append(piece)
        parent.children.sort(key=lambda child: child.span.start)
    for token in tokens:
        if token.type == tokenize.COMMENT:
            attach_trivia(make('comment', token.string, 'A comment is a note for people reading the code. Python does not execute the text after # on this line. A # inside a quoted string is text, not a comment.', 'human explanation in the source', token.start, token.end))
    continuation_lines = set()
    nesting = 0
    seen_lines = set()
    for token in tokens:
        if token.start[0] not in seen_lines:
            if nesting:
                continuation_lines.add(token.start[0])
            seen_lines.add(token.start[0])
        if token.type == tokenize.OP:
            if token.string in ('(', '[', '{'):
                nesting += 1
            elif token.string in (')', ']', '}'):
                nesting -= 1
    for number, line in enumerate(lines, 1):
        indent = len(line) - len(line.lstrip(' \t'))
        if indent and line.strip() and number not in continuation_lines:
            attach_trivia(make('indentation', 'Indentation', 'Leading spaces or tabs show which block this line belongs to. A deeper indentation begins a nested block; returning left leaves it. Use consistent indentation. Whitespace on a comment-only line does not itself create a block.', 'block membership shown by whitespace', (number, 0), (number, indent)))
    def explain_roles(node, parent=None, assignment=None):
        if node.kind == 'assignment':
            assignment = node
        if node.kind == 'string' and parent and parent.kind == 'element':
            node.overview = ['What it is: a string, meaning a text value (Python type str).', 'Its role here: ' + parent.label + '.', parent.explanation, 'Quotes are source syntax; the stored text does not include its surrounding quotes.']
            if assignment:
                node.overview.append('Connected to: ' + assignment.label + '. Follow the containing collection to see the full structure.')
        if node.kind in ('class','try_statement','with_statement','except_handler') and not node.overview:
            node.overview = [node.explanation, 'Explore inside to inspect the header, nested statements, names, and punctuation.']
        for child in node.children:
            explain_roles(child, node, assignment)
    explain_roles(root)
    connections = []
    for current_scope, name, use_id in uses:
        definitions = None
        search_scope = current_scope
        while search_scope is not None:
            definitions = bindings.get((search_scope, name))
            if definitions is not None:
                break
            search_scope = scope_parent[search_scope]
        for definition in definitions or []:
            connections.append(Connection(source_id=definition, target_id=use_id, label='Possible name binding (static; not execution order)'))
    for class_name, attribute, use_id in member_uses:
        for definition in class_members.get((class_name, attribute), []):
            connections.append(Connection(source_id=definition, target_id=use_id, label='Possible member definition (static inference; runtime may differ)'))
    def connect_loop_controls(node, loop=None):
        if node.kind in ('function', 'method'):
            loop = None
        if node.kind in ('for_loop', 'while_loop'):
            loop = node
        if node.kind in ('break', 'continue') and loop:
            connections.append(Connection(source_id=node.id, target_id=loop.id,
                label='Exits this loop' if node.kind == 'break' else 'Continues this loop'))
        for child in node.children:
            connect_loop_controls(child, loop)
    connect_loop_controls(root)
    return Anatomy(source=source, root=root, connections=connections)
