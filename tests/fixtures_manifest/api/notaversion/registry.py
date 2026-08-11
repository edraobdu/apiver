"""Named to prove `_load_versions()` rejects a resolved object that isn't a
Version instance, even when the dotted path itself resolves fine."""

notaversion = "not a Version instance"
