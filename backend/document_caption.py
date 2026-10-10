"""Fast read-only document caption from Photoshop's workspace title."""
import re


def document_name(title):
    name, separator, suffix = title.rpartition(' @ ')
    if separator and name and re.match(r'\d[\d.,]*%', suffix):
        return name
    return None
