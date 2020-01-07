"""Utility functions."""

__author__ = "Tom Goetz"
__copyright__ = "Copyright Tom Goetz"
__license__ = "GPL"


def list_not_none(inlist):
    """Filter None values from a list."""
    return [item for item in inlist if item is not None]


def list_zero_for_none(inlist):
    """Replace None values in a list with zeros."""
    return [item if item is not None else 0 for item in inlist]


def list_in_list(list1, list2):
    """Test if all items in list1 are present in list2."""
    for list_item in list1:
        if list_item not in list2:
            return False
    return True


def list_intersection(list1, list2):
    """Return a list of the items present both in list1 and list2."""
    return [list_item for list_item in list1 if list_item in list2]


def list_intersection_count(list1, list2):
    """Return the count of items present in both lists."""
    return len(list_intersection(list1, list2))


def dict_filter_none_values(in_dict):
    """Given a dictionary, return a new dictionary with only the dict items with non-None values."""
    return {key : value for key, value in in_dict.items() if value is not None}


def filter_dict_by_list(in_dict, keep_list):
    """Return a dictionary with all items from the input dictionary who's keys appear in the list."""
    return {key : value for key, value in in_dict.items() if key in keep_list}
