"""Tests for XSD schema discovery."""

from tap_workday_raas.discovery import generate_schema_for_report

XSD = """<?xml version="1.0" encoding="UTF-8"?>
<xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:wd="urn:com.workday.report/Stitch_Testing_2" xmlns:nyw="urn:com.netyourwork/aod" elementFormDefault="qualified" attributeFormDefault="qualified" targetNamespace="urn:com.workday.report/Stitch_Testing_2">
    <xsd:element name="Report_Data" type="wd:Report_DataType"/>
    <xsd:simpleType name="RichText">
        <xsd:restriction base="xsd:string"/>
    </xsd:simpleType>
    <xsd:complexType name="Candidate_Details_groupType">
        <xsd:sequence>
            <xsd:element name="Employee" type="xsd:string" minOccurs="0"/>
            <xsd:element name="Willing_To_Travel" type="xsd:string" minOccurs="0"/>
            <xsd:element name="Potential" type="xsd:string" minOccurs="0"/>
        </xsd:sequence>
    </xsd:complexType>
    <xsd:complexType name="Report_EntryType">
        <xsd:sequence>
            <xsd:element name="Default_Job_Title" type="xsd:string" minOccurs="0"/>
            <xsd:element name="Average_Pay_-_Amount" type="xsd:decimal" minOccurs="0"/>
            <xsd:element name="Hire_Date" type="xsd:date" minOccurs="0"/>
            <xsd:element name="Last_Updated" type="xsd:dateTime" minOccurs="0"/>
            <xsd:element name="job_profile_id" type="xsd:string" minOccurs="0"/>
            <xsd:element name="Languages" type="xsd:string" minOccurs="0"/>
            <xsd:element name="Default_Assessment_Tests" type="xsd:string" minOccurs="0"/>
            <xsd:element name="Business_Unit_or_Business_Unit_Hierarchy_Container" type="xsd:string" minOccurs="0"/>
            <xsd:element name="Candidate_Details_group" type="wd:Candidate_Details_groupType" minOccurs="0" maxOccurs="unbounded"/>
        </xsd:sequence>
    </xsd:complexType>
    <xsd:complexType name="Report_DataType">
        <xsd:sequence>
            <xsd:element name="Report_Entry" type="wd:Report_EntryType" minOccurs="0" maxOccurs="unbounded"/>
        </xsd:sequence>
    </xsd:complexType>
</xsd:schema>
"""


def test_generate_schema_for_report() -> None:
    expected = {
        "properties": {
            "Average_Pay_-_Amount": {
                "type": ["string", "null"],
                "format": "singer.decimal",
            },
            "Business_Unit_or_Business_Unit_Hierarchy_Container": {"type": ["string", "null"]},
            "Candidate_Details_group": {
                "items": {
                    "properties": {
                        "Employee": {"type": ["string", "null"]},
                        "Potential": {"type": ["string", "null"]},
                        "Willing_To_Travel": {"type": ["string", "null"]},
                    },
                    "type": "object",
                },
                "type": "array",
            },
            "Default_Assessment_Tests": {"type": ["string", "null"]},
            "Default_Job_Title": {"type": ["string", "null"]},
            "Hire_Date": {"type": ["string", "null"], "format": "date"},
            "Languages": {"type": ["string", "null"]},
            "Last_Updated": {"type": ["string", "null"], "format": "date-time"},
            "job_profile_id": {"type": ["string", "null"]},
        },
        "type": "object",
    }

    assert generate_schema_for_report(XSD) == expected
