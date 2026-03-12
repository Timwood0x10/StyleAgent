"""
Tests for LLM utilities - parse_json_response and normalize_to_string_list
"""

import pytest
from src.utils.llm import parse_json_response, normalize_to_string_list


class TestNormalizeToStringList:
    """Tests for normalize_to_string_list function"""

    def test_plain_string_list(self):
        """Test with plain string list"""
        result = normalize_to_string_list(["item1", "item2", "item3"])
        assert result == ["item1", "item2", "item3"]

    def test_object_list_with_name_key(self):
        """Test with list of objects containing 'name' key"""
        data = [{"name": "item1"}, {"name": "item2"}]
        result = normalize_to_string_list(data, key="name")
        assert result == ["item1", "item2"]

    def test_object_list_with_other_keys(self):
        """Test with list of objects containing different keys"""
        data = [{"color": "red"}, {"color": "blue"}]
        result = normalize_to_string_list(data, key="color")
        assert result == ["red", "blue"]

    def test_object_list_with_reason_key(self):
        """Test with list of objects containing 'reason' key"""
        data = [{"reason": "looks good"}, {"reason": "matches well"}]
        result = normalize_to_string_list(data, key="reason")
        assert result == ["looks good", "matches well"]

    def test_empty_list(self):
        """Test with empty list"""
        result = normalize_to_string_list([])
        assert result == []

    def test_none_input(self):
        """Test with None input"""
        result = normalize_to_string_list(None)
        assert result == []

    def test_empty_dict_in_list(self):
        """Test with empty dict in list"""
        result = normalize_to_string_list([{}], key="name")
        assert result == []

    def test_dict_without_key(self):
        """Test with dict that doesn't have the specified key - falls back to first value"""
        data = [{"color": "red"}]
        result = normalize_to_string_list(data, key="name")
        # Falls back to first value when key not found
        assert result == ["red"]

    def test_comma_separated_string(self):
        """Test with comma-separated string"""
        result = normalize_to_string_list("item1, item2, item3")
        assert result == ["item1", "item2", "item3"]

    def test_single_string(self):
        """Test with single string (not in list)"""
        result = normalize_to_string_list("single_item")
        assert result == ["single_item"]

    def test_mixed_list(self):
        """Test with list containing only dicts (common case)"""
        data = [{"name": "item1"}, {"name": "item2"}]
        result = normalize_to_string_list(data, key="name")
        assert result == ["item1", "item2"]


class TestParseJsonResponse:
    """Tests for parse_json_response function"""

    def test_simple_json_dict(self):
        """Test parsing simple JSON dict"""
        response = '{"name": "test", "value": 123}'
        result = parse_json_response(response)
        assert result == {"name": "test", "value": 123}

    def test_json_in_markdown_code_block(self):
        """Test parsing JSON in markdown code block"""
        response = '```json\n{"name": "test"}\n```'
        result = parse_json_response(response)
        assert result == {"name": "test"}

    def test_json_in_plain_markdown_block(self):
        """Test parsing JSON in plain markdown code block"""
        response = '```\n{"name": "test"}\n```'
        result = parse_json_response(response)
        assert result == {"name": "test"}

    def test_json_list(self):
        """Test parsing JSON list"""
        response = '["item1", "item2", "item3"]'
        result = parse_json_response(response, expect_list=True)
        assert result == ["item1", "item2", "item3"]

    def test_json_list_with_dicts(self):
        """Test parsing JSON list containing dicts"""
        response = '[{"name": "item1"}, {"name": "item2"}]'
        result = parse_json_response(response, expect_list=True)
        assert result == [{"name": "item1"}, {"name": "item2"}]

    def test_empty_response(self):
        """Test with empty response"""
        result = parse_json_response("")
        assert result is None

    def test_none_response(self):
        """Test with None response"""
        result = parse_json_response(None)
        assert result is None

    def test_invalid_json(self):
        """Test with invalid JSON"""
        result = parse_json_response("not valid json at all")
        assert result is None

    def test_json_with_extra_text(self):
        """Test JSON with extra text before and after"""
        response = 'some text before {"name": "test"} and some text after'
        result = parse_json_response(response)
        assert result == {"name": "test"}

    def test_json_array_with_extra_text(self):
        """Test JSON array with extra text"""
        response = 'text before ["a", "b", "c"] text after'
        result = parse_json_response(response, expect_list=True)
        assert result == ["a", "b", "c"]
