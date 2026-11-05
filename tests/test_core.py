import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ggbh.core import Document, DataError, PREFIX, KEY, decode, encode, find_roles


class CoreTests(unittest.TestCase):
    def test_cache_compatible_with_independent_legacy_formula(self):
        value = {"角色": {"q": {"q": ["张", "三"], "1": 12}}}
        raw = json.dumps(value, ensure_ascii=False).encode()
        compressed = gzip.compress(raw)
        legacy = PREFIX + bytes((byte + KEY[i % len(KEY)]) & 255 for i, byte in enumerate(compressed))
        self.assertEqual(decode(legacy), (value, "legacy-cache"))
        exported = encode(value, "legacy-cache")
        extracted = bytes((byte - KEY[i % len(KEY)]) & 255 for i, byte in enumerate(exported[len(PREFIX):]))
        self.assertEqual(json.loads(gzip.decompress(extracted)), value)

    def test_invalid_inputs(self):
        for data in (b'{"x":1,"x":2}', b'{"x":NaN}', b'[]trailing', PREFIX + b'bad', b'null'):
            with self.subTest(data=data), self.assertRaises(DataError):
                decode(data)

    def test_decompression_limit(self):
        with patch("ggbh.core.MAX_BYTES", 1024):
            compressed = gzip.compress(b" " * 4096)
            payload = PREFIX + bytes((b + KEY[i % len(KEY)]) & 255 for i, b in enumerate(compressed))
            with self.assertRaises(DataError):
                decode(payload)

    def test_transaction_and_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "原始'数据.json"
            original = b'{"x":1,"y":true,"name":"a","unknown":{"future":3}}'
            source.write_bytes(original)
            doc = Document(source)
            with self.assertRaises(DataError):
                doc.set_many([(("x",), "4"), (("y",), "bad")])
            self.assertEqual(doc.data["x"], 1)
            doc.set_many([(("x",), "42")])
            with self.assertRaises(DataError):
                doc.export(source)
            target = root / "副本.json"
            backup = doc.export(target)
            self.assertEqual(backup.read_bytes(), original)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(json.loads(target.read_bytes())["x"], 42)
            self.assertEqual(json.loads(target.read_bytes())["unknown"], {"future": 3})
            with self.assertRaises(FileExistsError):
                doc.export(target)
            source.write_bytes(b'{"x":2}')
            with self.assertRaises(DataError):
                doc.export(root / "stale.json")
            self.assertFalse((root / "stale.json").exists())
            self.assertFalse(list(root.glob(".ggbh-*")))
            doc.reset()
            self.assertEqual(doc.data["x"], 1)
            self.assertFalse(doc.changes)

    def test_roles_and_empty_arrays(self):
        data = {"units": [{"q": {"q": ["李", "四"], "1": 3}}, {"q": {"q": []}}]}
        self.assertEqual(list(find_roles(data)), [(("units", 0), "李四")])

    def test_integer_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.json"
            path.write_text('{"x":1}')
            doc = Document(path)
            with self.assertRaises(DataError):
                doc.set_many([(("x",), str(2**40))])
            self.assertEqual(doc.data["x"], 1)


if __name__ == "__main__":
    unittest.main()
