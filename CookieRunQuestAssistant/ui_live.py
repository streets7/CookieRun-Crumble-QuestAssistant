"""Read saved UI literals without reloading or executing the running engine."""
import ast
import hashlib
import threading


class LiveHTML:
    def __init__(self, path, fallback):
        self.path = path
        self.html = fallback
        self.signature = None
        self.lock = threading.Lock()

    def read(self):
        with self.lock:
            try:
                stat = self.path.stat()
                signature = (stat.st_mtime_ns, stat.st_size)
                if signature != self.signature:
                    tree = ast.parse(self.path.read_text(encoding='utf-8'))
                    for node in tree.body:
                        if isinstance(node, ast.Assign) and any(
                            isinstance(target, ast.Name) and target.id == 'HTML'
                            for target in node.targets
                        ):
                            value = ast.literal_eval(node.value)
                            if isinstance(value, str) and value.strip():
                                self.html = value
                    self.signature = signature
            except (OSError, SyntaxError, ValueError, TypeError, UnicodeError):
                pass  # An incomplete save must not replace the working page.
            return self.html, hashlib.sha256(self.html.encode()).hexdigest()[:16]
