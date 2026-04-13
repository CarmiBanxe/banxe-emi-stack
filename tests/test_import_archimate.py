"""
tests/test_import_archimate.py — ArchiMate Import Pipeline tests
S13-00 | banxe-architecture | banxe-emi-stack

Tests for scripts/import-archimate.py parser, generators, and validators.
No external calls — uses in-memory XML/CSV strings via tmp_path.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

# ── Locate the import-archimate module ───────────────────────────────────────
import sys
import textwrap

import pytest

_ARCH_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "banxe-architecture" / "scripts"
if str(_ARCH_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_ARCH_SCRIPTS))

try:
    import import_archimate as ia  # type: ignore[import]

    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _AVAILABLE, reason="banxe-architecture/scripts/import-archimate.py not found"
)

# ── Sample Open Exchange XML ──────────────────────────────────────────────────

_SAMPLE_XML = textwrap.dedent(
    """\
    <?xml version="1.0" encoding="UTF-8"?>
    <model xmlns="http://www.opengroup.org/xsd/archimate/3.0/"
           xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
           identifier="id-test-model" version="3.0">
      <name xml:lang="en">Test Model</name>
      <elements>
        <element identifier="elem-1" xsi:type="ApplicationComponent">
          <name xml:lang="en">Payment Service</name>
          <documentation xml:lang="en">Handles FPS and SEPA payments.</documentation>
          <properties>
            <property propertyDefinitionRef="prop-domain">
              <value xml:lang="en">payment</value>
            </property>
            <property propertyDefinitionRef="prop-status">
              <value xml:lang="en">ACTIVE</value>
            </property>
          </properties>
        </element>
        <element identifier="elem-2" xsi:type="BusinessProcess">
          <name xml:lang="en">Daily Reconciliation</name>
          <documentation xml:lang="en">CASS 7.15.17R daily recon.</documentation>
        </element>
        <element identifier="elem-3" xsi:type="TechnologyService">
          <name xml:lang="en">Midaz CBS</name>
          <documentation xml:lang="en">Core Banking System :8095.</documentation>
          <properties>
            <property propertyDefinitionRef="prop-host">
              <value xml:lang="en">localhost:8095</value>
            </property>
          </properties>
        </element>
        <element identifier="elem-4" xsi:type="DataObject">
          <name xml:lang="en">TransactionRecord</name>
          <documentation xml:lang="en">Immutable tx record. Decimal amounts (I-05).</documentation>
        </element>
      </elements>
      <relationships>
        <relationship identifier="rel-1" xsi:type="Serving"
          source="elem-1" target="elem-3">
          <name xml:lang="en">calls</name>
        </relationship>
        <relationship identifier="rel-2" xsi:type="Composition"
          source="elem-2" target="elem-1">
          <name xml:lang="en">includes</name>
        </relationship>
        <relationship identifier="rel-3" xsi:type="Flow"
          source="elem-1" target="elem-4">
          <name xml:lang="en">produces</name>
        </relationship>
      </relationships>
      <views>
        <diagrams>
          <view identifier="view-1" xsi:type="ModelViewpoint">
            <name xml:lang="en">Payment Architecture</name>
            <node elementRef="elem-1" identifier="node-1" type="Element" x="100" y="50" w="200" h="60"/>
            <node elementRef="elem-3" identifier="node-2" type="Element" x="100" y="200" w="200" h="60"/>
            <connection relationshipRef="rel-1" identifier="conn-1" source="node-1" target="node-2"/>
          </view>
        </diagrams>
      </views>
      <propertyDefinitions>
        <propertyDefinition identifier="prop-domain" type="string">
          <name xml:lang="en">banxe-domain</name>
        </propertyDefinition>
        <propertyDefinition identifier="prop-status" type="string">
          <name xml:lang="en">banxe-status</name>
        </propertyDefinition>
        <propertyDefinition identifier="prop-host" type="string">
          <name xml:lang="en">banxe-host</name>
        </propertyDefinition>
      </propertyDefinitions>
    </model>
    """
)

_EMPTY_XML = textwrap.dedent(
    """\
    <?xml version="1.0" encoding="UTF-8"?>
    <model xmlns="http://www.opengroup.org/xsd/archimate/3.0/"
           xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
           identifier="id-empty" version="3.0">
      <name xml:lang="en">Empty Model</name>
      <elements/>
      <relationships/>
    </model>
    """
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _write_xml(tmp_path: Path, content: str, name: str = "model.xml") -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _write_csv_dir(tmp_path: Path) -> Path:
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()

    # elements.csv
    with (csv_dir / "elements.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ID", "Type", "Name", "Documentation"])
        w.writerow(["csv-elem-1", "ApplicationComponent", "CSV Service", "From CSV"])
        w.writerow(["csv-elem-2", "TechnologyService", "CSV Infra", "Tech layer"])

    # relations.csv
    with (csv_dir / "relations.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ID", "Type", "Source", "Target", "Name"])
        w.writerow(["csv-rel-1", "Serving", "csv-elem-1", "csv-elem-2", "uses"])

    # properties.csv
    with (csv_dir / "properties.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ID", "Key", "Value"])
        w.writerow(["csv-elem-1", "banxe-domain", "services"])
        w.writerow(["csv-elem-1", "banxe-status", "ACTIVE"])

    return csv_dir


# ── XML Parser tests ──────────────────────────────────────────────────────────


class TestParseXml:
    def test_parse_elements_count(self, tmp_path):
        xml = _write_xml(tmp_path, _SAMPLE_XML)
        model = ia.parse_xml(xml)
        assert len(model["elements"]) == 4

    def test_parse_element_type(self, tmp_path):
        xml = _write_xml(tmp_path, _SAMPLE_XML)
        model = ia.parse_xml(xml)
        types = {e["type"] for e in model["elements"]}
        assert "ApplicationComponent" in types
        assert "BusinessProcess" in types
        assert "TechnologyService" in types
        assert "DataObject" in types

    def test_parse_element_name(self, tmp_path):
        xml = _write_xml(tmp_path, _SAMPLE_XML)
        model = ia.parse_xml(xml)
        names = {e["name"] for e in model["elements"]}
        assert "Payment Service" in names
        assert "Midaz CBS" in names

    def test_parse_element_documentation(self, tmp_path):
        xml = _write_xml(tmp_path, _SAMPLE_XML)
        model = ia.parse_xml(xml)
        payment = next(e for e in model["elements"] if e["name"] == "Payment Service")
        assert "FPS" in payment["documentation"]

    def test_parse_element_banxe_domain(self, tmp_path):
        xml = _write_xml(tmp_path, _SAMPLE_XML)
        model = ia.parse_xml(xml)
        payment = next(e for e in model["elements"] if e["name"] == "Payment Service")
        assert payment["banxe_domain"] == "services"

    def test_parse_element_properties(self, tmp_path):
        xml = _write_xml(tmp_path, _SAMPLE_XML)
        model = ia.parse_xml(xml)
        payment = next(e for e in model["elements"] if e["name"] == "Payment Service")
        assert payment["properties"].get("banxe-status") == "ACTIVE"

    def test_parse_relationships_count(self, tmp_path):
        xml = _write_xml(tmp_path, _SAMPLE_XML)
        model = ia.parse_xml(xml)
        assert len(model["relationships"]) == 3

    def test_parse_relationship_type(self, tmp_path):
        xml = _write_xml(tmp_path, _SAMPLE_XML)
        model = ia.parse_xml(xml)
        types = {r["type"] for r in model["relationships"]}
        assert "Serving" in types
        assert "Composition" in types
        assert "Flow" in types

    def test_parse_relationship_source_target(self, tmp_path):
        xml = _write_xml(tmp_path, _SAMPLE_XML)
        model = ia.parse_xml(xml)
        serving = next(r for r in model["relationships"] if r["type"] == "Serving")
        assert serving["source"] == "elem-1"
        assert serving["target"] == "elem-3"

    def test_parse_views_count(self, tmp_path):
        xml = _write_xml(tmp_path, _SAMPLE_XML)
        model = ia.parse_xml(xml)
        assert len(model["views"]) == 1

    def test_parse_view_name(self, tmp_path):
        xml = _write_xml(tmp_path, _SAMPLE_XML)
        model = ia.parse_xml(xml)
        assert model["views"][0]["name"] == "Payment Architecture"

    def test_parse_view_nodes(self, tmp_path):
        xml = _write_xml(tmp_path, _SAMPLE_XML)
        model = ia.parse_xml(xml)
        view = model["views"][0]
        assert view["node_count"] == 2

    def test_empty_model_returns_empty_lists(self, tmp_path):
        xml = _write_xml(tmp_path, _EMPTY_XML)
        model = ia.parse_xml(xml)
        assert model["elements"] == []
        assert model["relationships"] == []

    def test_missing_file_returns_empty_model(self, tmp_path):
        model = ia.parse_xml(tmp_path / "nonexistent.xml")
        assert model["elements"] == []
        assert model["relationships"] == []
        assert model["views"] == []


# ── CSV Parser tests ──────────────────────────────────────────────────────────


class TestParseCsv:
    def test_parse_elements_from_csv(self, tmp_path):
        csv_dir = _write_csv_dir(tmp_path)
        model = ia.parse_csv(csv_dir)
        assert len(model["elements"]) == 2

    def test_csv_element_name(self, tmp_path):
        csv_dir = _write_csv_dir(tmp_path)
        model = ia.parse_csv(csv_dir)
        names = {e["name"] for e in model["elements"]}
        assert "CSV Service" in names

    def test_csv_element_banxe_domain(self, tmp_path):
        csv_dir = _write_csv_dir(tmp_path)
        model = ia.parse_csv(csv_dir)
        svc = next(e for e in model["elements"] if e["name"] == "CSV Service")
        assert svc["banxe_domain"] == "services"

    def test_csv_properties_merged(self, tmp_path):
        csv_dir = _write_csv_dir(tmp_path)
        model = ia.parse_csv(csv_dir)
        svc = next(e for e in model["elements"] if e["name"] == "CSV Service")
        assert svc["properties"].get("banxe-status") == "ACTIVE"

    def test_csv_relations_count(self, tmp_path):
        csv_dir = _write_csv_dir(tmp_path)
        model = ia.parse_csv(csv_dir)
        assert len(model["relationships"]) == 1

    def test_csv_empty_dir_returns_empty(self, tmp_path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        model = ia.parse_csv(empty_dir)
        assert model["elements"] == []


# ── ArchiMate type → domain mapping tests ────────────────────────────────────


class TestTypeToDomain:
    def test_application_component_maps_to_services(self):
        assert ia.ARCHIMATE_TYPE_TO_DOMAIN["ApplicationComponent"] == "services"

    def test_business_process_maps_to_workflows(self):
        assert ia.ARCHIMATE_TYPE_TO_DOMAIN["BusinessProcess"] == "workflows"

    def test_technology_service_maps_to_infrastructure(self):
        assert ia.ARCHIMATE_TYPE_TO_DOMAIN["TechnologyService"] == "infrastructure"

    def test_data_object_maps_to_models(self):
        assert ia.ARCHIMATE_TYPE_TO_DOMAIN["DataObject"] == "models"

    def test_application_service_maps_to_api(self):
        assert ia.ARCHIMATE_TYPE_TO_DOMAIN["ApplicationService"] == "api"


# ── JSON output tests ─────────────────────────────────────────────────────────


class TestWriteJsonOutputs:
    def test_creates_elements_json(self, tmp_path):
        xml = _write_xml(tmp_path, _SAMPLE_XML)
        model = ia.parse_xml(xml)
        out_dir = tmp_path / "out"
        ia.write_json_outputs(model, out_dir)
        assert (out_dir / "elements.json").exists()

    def test_creates_relations_json(self, tmp_path):
        xml = _write_xml(tmp_path, _SAMPLE_XML)
        model = ia.parse_xml(xml)
        out_dir = tmp_path / "out"
        ia.write_json_outputs(model, out_dir)
        assert (out_dir / "relations.json").exists()

    def test_creates_views_json(self, tmp_path):
        xml = _write_xml(tmp_path, _SAMPLE_XML)
        model = ia.parse_xml(xml)
        out_dir = tmp_path / "out"
        ia.write_json_outputs(model, out_dir)
        assert (out_dir / "views.json").exists()

    def test_elements_json_parseable(self, tmp_path):
        xml = _write_xml(tmp_path, _SAMPLE_XML)
        model = ia.parse_xml(xml)
        out_dir = tmp_path / "out"
        ia.write_json_outputs(model, out_dir)
        data = json.loads((out_dir / "elements.json").read_text())
        assert len(data) == 4


# ── Service map generator tests ───────────────────────────────────────────────


class TestGenerateServiceMap:
    def test_creates_md_file(self, tmp_path):
        xml = _write_xml(tmp_path, _SAMPLE_XML)
        model = ia.parse_xml(xml)
        out_dir = tmp_path / "out"
        ia.generate_service_map(model, out_dir)
        assert (out_dir / "SERVICE-MAP-GENERATED.md").exists()

    def test_md_contains_element_names(self, tmp_path):
        xml = _write_xml(tmp_path, _SAMPLE_XML)
        model = ia.parse_xml(xml)
        out_dir = tmp_path / "out"
        ia.generate_service_map(model, out_dir)
        content = (out_dir / "SERVICE-MAP-GENERATED.md").read_text()
        assert "Payment Service" in content
        assert "Midaz CBS" in content

    def test_md_auto_generated_header(self, tmp_path):
        xml = _write_xml(tmp_path, _SAMPLE_XML)
        model = ia.parse_xml(xml)
        out_dir = tmp_path / "out"
        ia.generate_service_map(model, out_dir)
        content = (out_dir / "SERVICE-MAP-GENERATED.md").read_text()
        assert "AUTO-GENERATED" in content
