# Python Anatomy · V0.5

A beginner-oriented, explodable 2D anatomy of Python source. The main mini-store program brings the language concepts together; smaller examples remain available.

## Run locally

Requires Python 3.10 or newer. From this project directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000. API documentation is at `/docs`. POST `/analyze` accepts `{"source": "cart = [\"Milk\"]"}`.

## Deploy on Render

The included `render.yaml` defines one free Python web service. Connect this repository in Render and create a Blueprint. Render installs the requirements, starts FastAPI on its assigned port, and checks `/health` before sending visitors to a new deployment.

After the first deployment succeeds, add `pythonanatomy.com` and `www.pythonanatomy.com` under the service's **Custom Domains** settings. Render will show the exact DNS records to enter at the company where the domain was purchased.

## Explore

Choose **Mini store · whole program** and press Analyze. The example has a top-level for loop that prints the catalog and another for loop inside `calculate_total`. It also includes a while shopping loop, break/continue, Boolean conditions, a Receipt class, instance methods, default/named arguments, files and exception handling.

Use **Jump to a part of the program** for direct access to classes, functions, methods, loops, and resource/error blocks. Select a piece and choose **Explore inside**, or double-click it. Breadcrumbs restore the surrounding program. Explode spreads the current level apart; Reassemble restores source positions. View size scales the diagram, and large diagrams scroll.

**Inspector (About this piece)** explains the selection and its context. The component tree includes comments and indentation. Indentation markers appear in syntax-level exploration rather than cluttering whole-block cards. The input function `ask_customer` is deliberately defined but not called in the sample, so running the sample does not wait for input.

## Supported source-analysis categories

| Category | Current support |
| --- | --- |
| Values | Names, assignment, strings, integers, finite floats, booleans, None |
| Collections | Lists, tuples, dictionaries, sets, nested collections, lookup |
| Operators | Arithmetic and binary bitwise operators, comparisons and identity, and/or/not, signed numeric literals, augmented assignment |
| Control flow | if/elif/else, for, while, break, continue, return, pass |
| Functions | Functions, parameters, defaults, positional and named arguments, calls, nested functions, lexical name links |
| Objects | Classes, simple inheritance syntax, instance methods, __init__, self, attribute reads/writes, class-call explanations, conservative member links |
| Modules | Current file as a module, import/from-import, aliases, dotted and relative import syntax |
| Errors/resources | try/except/else/finally, raise/from, with/as, contextual open/input/print and common file-method explanations |
| Source detail | Contextual punctuation, comments, block indentation, exact source spans |

Coverage means supported forms with explanations, not every legal Python grammar variant. Annotations, decorators, variadic/keyword-only/positional-only parameters, async, generators, comprehensions, starred unpacking, wildcard imports, slicing, extra grouping parentheses, prefixed/triple-quoted strings, adjacent strings, loop-else, global/nonlocal declarations, and unary bitwise inversion are not supported yet. Collection keys/set items require recognized hashable literal shapes. Input limits are 10,000 characters, 700 AST nodes, and 12 levels per block/expression traversal.

## Analysis versus execution

The analyzer never runs submitted code, performs imports, requests input, or opens files. Running `examples/mini_store.py` yourself **does** write `receipt.json` in the current directory; its file mode replaces any existing file with that name. Merely viewing/analyzing it does not.

Dashed links identify possible static name/member bindings and nearest-loop control targets. They are not execution order or a memory/data-flow simulation. Member inference covers simple module-level class construction and conventional instance receivers; runtime reassignment, descriptors, inheritance resolution and dynamic dispatch can differ. Exception-variable lifetime and control-flow definite assignment are not simulated.

The built-in and method explanations state their assumptions; functions such as open can be shadowed. No external module contents are loaded. Multi-file project navigation, execution stepping, live values/memory, and 3D remain future milestones.

## Python architecture

- `backend/models.py`: Pydantic request, node, span and connection types. Each node has an explanation, contextual relationship, optional overview and children. The API schema is 0.5.
- `backend/analyzer.py`: `ast.parse` recognizes meaning; `tokenize` retains punctuation. `statement` builds instructions, while `build` recursively builds expressions. Class/function scope bookkeeping connects possible definitions to uses. Token trivia is attached after meaning is analyzed.
- `backend/main.py`: validates HTTP requests, returns explanatory 422 errors, and serves the frontend. Local frontend responses disable caching so old JS/CSS does not mix with newer data.
- `frontend/app.js`: renders the model without depending on Python AST shapes. It supports block navigation, syntax explosion, links, and source highlights; user code is inserted with textContent rather than HTML.

AST columns count UTF-8 bytes. The analyzer converts them into Unicode character positions. API spans have one-based lines, zero-based columns and half-open offsets `[start, end)`. JavaScript uses code points for slicing. IDs are unique within one response, not stable across edits.

Python's `compile` checks semantic syntax such as break outside a loop. The resulting code object is discarded, never executed. Functions use distinct scope identifiers; method bare-name lookup skips the class namespace. `self` is explained as a convention, and __init__ as initialization rather than object creation.

## Checks

```sh
python -m unittest discover -s tests -v
node tests/test_ui.cjs
```

The second command needs Node.js and uses a minimal DOM stand-in, not real-browser visual QA. Set `PYTHON` to choose its Python executable. Checks cover source spans, contextual syntax, type-preserving JSON, complete-store coverage, scope, objects, loops, exceptions, resources, comments/indentation, unsupported forms, and navigating the diagram into supported blocks and back out.
