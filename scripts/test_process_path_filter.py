from .process_path_filter import Filter, SkipIf


def test_simple_match():
	filter = Filter(
		name="test",
		files=["test"],
	)
	assert filter.matches(["test.txt"])
	assert filter.matches(["test.py"])
	assert not filter.matches(["abc"])
	assert filter.matches(["abc", "test.py"])


def test_skip_files():
	filter = Filter(
		name="test",
		files=["test"],
		skip_if=SkipIf(
			all_file_match_any=["test.py"],
		),
	)
	assert filter.matches(["test.txt"])
	assert not filter.matches(["test.py"])
	assert not filter.matches(["abc"])
	assert filter.matches(["test.txt", "test.py"])
	assert filter.matches(["abc", "test.py"])