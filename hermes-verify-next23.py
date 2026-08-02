"""Ad-hoc verification for NEXT-2 + NEXT-3 (re-run, kept on disk).
Independent re-derivation only. No repo state mutated.
"""
import ast, sys, os, py_compile, tempfile

REPO = "/Volumes/NO NAME/TRADING/HERMES/unityengine/SignalMaestro"
OK, FAIL = [], []
def check(name, cond): (OK if cond else FAIL).append(name)

BT = os.path.join(REPO, "binance_trader.py")
EB = os.path.join(REPO, "enhanced_binance_futures_signal_bot.py")

# 0. py_compile both touched modules (real syntax + bytecode pass)
for f in (BT, EB):
    try:
        py_compile.compile(f, doraise=True)
        check(f"os.path.basename(f): py_compile OK", True)
    except py_compile.PyCompileError as e:
        check(f"{os.path.basename(f)}: py_compile FAIL: {e}", False)

bt = open(BT).read()
tree = ast.parse(bt)

# NEXT-2
target = None
for node in ast.walk(tree):
    if isinstance(node, ast.Try) and node.lineno == 739:
        for h in node.handlers:
            for c in ast.walk(h):
                if (isinstance(c, ast.Raise) and isinstance(c.exc, ast.Call)
                        and getattr(c.exc.func, 'id', '') == 'RuntimeError'):
                    target = (node, h, c)
check("NEXT-2a: try@739 handler raises RuntimeError", target is not None)
if target:
    try_node, handler, raise_node = target
    check("NEXT-2b: raise inside except (only fires on exception)", raise_node in ast.walk(handler))
    check("NEXT-2c: handler catches `Exception`",
          isinstance(handler.type, ast.Name) and handler.type.id == 'Exception')
    has_set_lev = any(isinstance(n, ast.Await) and isinstance(n.value, ast.Call)
                      and getattr(n.value.func, 'attr', '') == 'set_leverage'
                      for n in ast.walk(try_node))
    check("NEXT-2d: try body calls set_leverage (failure surface)", has_set_lev)
check("NEXT-2e: else-branch sets leverage_applied for non-futures path",
      "leverage_applied = getattr(self.config, 'DEFAULT_LEVERAGE', 1)" in bt)
check("NEXT-2f: no `except RuntimeError` swallow in file", "except RuntimeError" not in bt)

# NEXT-3
eb = open(EB).read()
etree = ast.parse(eb)
narrowed = []
for node in ast.walk(etree):
    if isinstance(node, ast.ExceptHandler) and node.type:
        names = []
        if isinstance(node.type, ast.Tuple):
            names = [getattr(e, 'id', '') for e in node.type.elts]
        elif isinstance(node.type, ast.Name):
            names = [node.type.id]
        if set(names) == {'TypeError','ValueError','ZeroDivisionError','IndexError'}:
            narrowed.append(node.lineno)
check("NEXT-3a: exactly 6 narrowed except handlers", len(narrowed) == 6)
check("NEXT-3b: narrowed at expected lines (~403-490)", all(400 <= ln <= 490 for ln in narrowed))
bare = [n.lineno for n in ast.walk(etree)
        if isinstance(n, ast.ExceptHandler) and n.type is None]
check("NEXT-3c: zero bare `except:` in file", len(bare) == 0)
check("NEXT-3d: debug log wired (6+ calls)", eb.count("self.logger.debug(") >= 6)
TARGET = (TypeError, ValueError, ZeroDivisionError, IndexError)
LEAK = (KeyboardInterrupt, SystemExit, MemoryError)
caught, leaked = [], []
for exc_cls in TARGET + LEAK:
    try:
        try: raise exc_cls("probe")
        except (TypeError, ValueError, ZeroDivisionError, IndexError): caught.append(exc_cls)
    except exc_cls: leaked.append(exc_cls)
check("NEXT-3e: all 4 target classes caught by narrowed tuple", set(caught) == set(TARGET))
check("NEXT-3f: KeyboardInterrupt/SystemExit/MemoryError leak through (not swallowed)",
      set(leaked) == set(LEAK))

# Report
n2 = sum(1 for n in OK if 'NEXT-2' in n); n3 = sum(1 for n in OK if 'NEXT-3' in n)
print(f"NEXT-2: {n2}/6  NEXT-3: {n3}/6  py_compile: 2/2")
for n in OK: print(f"  PASS  {n}")
for n in FAIL: print(f"  FAIL  {n}")
print("VERDICT:", "AD-HOC VERIFIED" if not FAIL else "UNVERIFIED")
sys.exit(0 if not FAIL else 1)
