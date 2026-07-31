# Copyright (c) 2026 Opteon Solutions
# Based on tap-workday-raas — Copyright (c) Stitch
#   https://github.com/singer-io/tap-workday-raas
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""XSD schema discovery for Workday RaaS reports."""

from __future__ import annotations

from typing import TYPE_CHECKING
from xml.etree import ElementTree

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element


def _element_to_schema(element: Element) -> dict:
    elem_type = element.attrib["type"].split(":")[1]
    is_nullable = element.attrib.get("minOccurs") == "0"

    max_occurs = element.attrib.get("maxOccurs")
    if max_occurs not in (None, "unbounded"):
        msg = f"Found unexpected value for maxOccurs attribute: '{max_occurs}'"
        raise ValueError(msg)

    is_list = max_occurs == "unbounded"

    if elem_type == "date":
        schema: dict = {"type": ["string"], "format": "date"}
    elif elem_type == "dateTime":
        schema = {"type": ["string"], "format": "date-time"}
    elif elem_type == "decimal":
        schema = {"type": ["string"], "format": "singer.decimal"}
    else:
        schema = {"type": [elem_type]}

    if is_nullable:
        schema["type"].append("null")

    if is_list:
        schema = {"type": "array", "items": schema}

    return schema


def parse_complex_type(
    complex_type_selectors: list[str],
    xsd_schema_et: Element,
    ns: dict[str, str],
) -> dict[str, dict]:
    complex_type_mapping: dict[str, dict] = {}
    for selector in complex_type_selectors:
        complex_type = xsd_schema_et.find(selector, ns)
        if complex_type is None:
            continue
        name = complex_type.attrib["name"]
        complex_type_mapping[name] = {"type": "object", "properties": {}}
        for child in complex_type.findall(".//xsd:element", ns):
            elem_name = child.attrib["name"]
            schema_type = _element_to_schema(child)
            complex_type_mapping[name]["properties"][elem_name] = {**schema_type}

    return complex_type_mapping


def generate_schema_for_report(xsd: str) -> dict:
    """Convert a Workday report XSD document to a JSON Schema."""
    xsd_schema_et = ElementTree.fromstring(xsd)
    ns = {"xsd": "http://www.w3.org/2001/XMLSchema"}

    schema: dict = {"type": "object", "properties": {}}

    # The report structure is defined by two complexType elements
    report_structure_elem_names = {"Report_EntryType", "Report_DataType"}
    all_complex_type_names = {
        elem.attrib["name"] for elem in xsd_schema_et.findall("./xsd:complexType", ns)
    }

    # The set difference yields complexType elements used in Report_EntryType
    # to define nested objects
    complex_types = all_complex_type_names - report_structure_elem_names

    # Compute JSON Schemas for other complexType elements (nested objects)
    complex_type_mapping = parse_complex_type(
        [f"./xsd:complexType[@name='{name}']" for name in complex_types],
        xsd_schema_et,
        ns,
    )

    # Iterate element definitions under Report_EntryType's sequence
    entry_path = "./xsd:complexType[@name='Report_EntryType']/xsd:sequence/xsd:element"
    for elem in xsd_schema_et.findall(entry_path, ns):
        elem_type = elem.attrib["type"].split(":")[1]
        elem_name = elem.attrib["name"]

        # elem's type references a complexType — a nested object
        if elem_type in complex_type_mapping:
            max_occurs = elem.attrib.get("maxOccurs")
            if max_occurs not in (None, "unbounded"):
                msg = f"Found unexpected value for maxOccurs attribute: '{max_occurs}'"
                raise ValueError(msg)

            is_list = max_occurs == "unbounded"

            if is_list:
                elem_schema = {"type": "array", "items": complex_type_mapping[elem_type]}
            else:
                elem_schema = complex_type_mapping[elem_type]
            schema["properties"][elem_name] = elem_schema
        else:
            schema_type = _element_to_schema(elem)
            schema["properties"][elem_name] = {**schema_type}

    return schema
