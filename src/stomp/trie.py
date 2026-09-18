'''A dict-like data structure where the keys are lists and which can
efficiently enumerate all suffixes of a given list prefix.'''

class Trie:
    def __init__(self):
        self.has_val = False
        self.children = {}

    def __contains__(self, key):
        cursor = self
        for k in key:
            if k in cursor.children:
                cursor = cursor.children[k]
            else:
                return False
        return cursor.has_val

    def get(self, key, default):
        cursor = self
        for k in key:
            if k in cursor.children:
                cursor = cursor.children[k]
            else:
                return default
        if cursor.has_val:
            return cursor.val
        else:
            return default

    def put(self, key, val):
        cursor = self
        for k in key:
            if k in cursor.children:
                cursor = cursor.children[k]
            else:
                t = Trie()
                cursor.children[k] = t
                cursor = t
        cursor.has_val = True
        cursor.val = val

    def items(self, prefix_key = []):
        cursor = self
        for k in prefix_key:
            if k in cursor.children:
                cursor = cursor.children[k]
            else:
                return []
        pairs = []
        stack = [(prefix_key, cursor)]
        while stack:
            (k, t) = stack.pop()
            if t.has_val:
                pairs.append((k, t.val))
            for (child_k, child_t) in t.children.items():
                stack.append((k+[child_k], child_t))
        return pairs
