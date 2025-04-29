from .process_path_filter import Filter, SkipIf


def test_simple_match():
	filter = Filter(
		name="test",
		files=["test"],
	)
	assert filter.is_match(["test.txt"])
	assert filter.is_match(["test.py"])
	assert not filter.is_match(["abc"])
	assert filter.is_match(["abc", "test.py"])


def test_skip_files():
	filter = Filter(
		name="test",
		files=["test"],
		skip_if=SkipIf(
			all_file_match_any=["test.py"],
		),
	)
	assert filter.is_match(["test.txt"])
	assert not filter.is_match(["test.py"])
	assert not filter.is_match(["abc"])
	assert filter.is_match(["test.txt", "test.py"])
	assert filter.is_match(["abc", "test.py"])