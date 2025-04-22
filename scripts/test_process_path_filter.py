from .process_path_filter import Filter, SkipIf


def test_simple_match():
	filter = Filter(
		name="test",
		files=["test"],
	)
	assert filter.calculate_match_and_fingerprint(["test.txt"])[0]
	assert filter.calculate_match_and_fingerprint(["test.py"])[0]
	assert not filter.calculate_match_and_fingerprint(["abc"])[0]
	assert filter.calculate_match_and_fingerprint(["abc", "test.py"])[0]


def test_skip_files():
	filter = Filter(
		name="test",
		files=["test"],
		skip_if=SkipIf(
			all_file_match_any=["test.py"],
		),
	)
	assert filter.calculate_match_and_fingerprint(["test.txt"])[0]
	assert not filter.calculate_match_and_fingerprint(["test.py"])[0]
	assert not filter.calculate_match_and_fingerprint(["abc"])[0]
	assert filter.calculate_match_and_fingerprint(["test.txt", "test.py"])[0]
	assert filter.calculate_match_and_fingerprint(["abc", "test.py"])[0]