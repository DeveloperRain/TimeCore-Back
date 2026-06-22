from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


def column_name(index: int) -> str:
    name = ""

    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name

    return name


def text_cell(reference: str, value: Any, style: int | None = None) -> str:
    style_attr = f' s="{style}"' if style is not None else ""
    value = "" if value is None else str(value)

    return (
        f'<c r="{reference}" t="inlineStr"{style_attr}>'
        f"<is><t>{escape(value)}</t></is>"
        "</c>"
    )


def parse_datetime(value: Any) -> tuple[str, str]:
    if not value:
        return "", ""

    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y"), value.strftime("%H:%M:%S")

    raw_value = str(value).strip()

    formats = (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S.%f",
    )

    for date_format in formats:
        try:
            parsed = datetime.strptime(raw_value, date_format)
            return parsed.strftime("%d/%m/%Y"), parsed.strftime("%H:%M:%S")
        except ValueError:
            continue

    if "T" in raw_value:
        date_part, time_part = raw_value.split("T", 1)
        return date_part, time_part[:8]

    if " " in raw_value:
        date_part, time_part = raw_value.split(" ", 1)
        return date_part, time_part[:8]

    return raw_value, ""


def normalize_status(value: Any) -> str:
    status = "" if value is None else str(value).strip().lower()

    translations = {
        "check_in": "Entrada",
        "check out": "Salida",
        "check_out": "Salida",
        "entrada": "Entrada",
        "salida": "Salida",
        "a tiempo": "A tiempo",
        "retardo": "Retardo",
        "late": "Retardo",
        "on_time": "A tiempo",
    }

    return translations.get(status, "Registro")


def get_value(record: Dict[str, Any], *keys: str, default: str = "") -> Any:
    for key in keys:
        value = record.get(key)

        if value is not None and str(value).strip() != "":
            return value

    return default


def build_sheet(rows: List[List[Any]]) -> str:
    sheet_rows = []

    for row_index, row in enumerate(rows, start=1):
        cells = []

        for column_index, value in enumerate(row, start=1):
            reference = f"{column_name(column_index)}{row_index}"
            cells.append(text_cell(reference, value, style=1 if row_index == 1 else None))

        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <cols>
    <col min="1" max="1" width="18" customWidth="1"/>
    <col min="2" max="2" width="14" customWidth="1"/>
    <col min="3" max="3" width="32" customWidth="1"/>
    <col min="4" max="4" width="14" customWidth="1"/>
    <col min="5" max="5" width="14" customWidth="1"/>
    <col min="6" max="6" width="18" customWidth="1"/>
    <col min="7" max="7" width="22" customWidth="1"/>
    <col min="8" max="8" width="16" customWidth="1"/>
  </cols>
  <sheetData>
    {''.join(sheet_rows)}
  </sheetData>
</worksheet>"""


def build_attendance_excel(records: List[Dict[str, Any]]) -> bytes:
    rows = [[
        "Sucursal",
        "Código",
        "Empleado",
        "Fecha",
        "Hora",
        "Tipo de Registro",
        "Reloj",
        "IP del Reloj",
    ]]

    for record in records:
        timestamp = get_value(record, "timestamp", "punch_time", "time", "fecha_hora")
        fecha, hora = parse_datetime(timestamp)

        rows.append([
            get_value(record, "sucursal", "branch", "branch_name", default="Matriz"),
            get_value(record, "user_id", "uid", "codigo", default="Sin código"),
            get_value(record, "name", "user_name", "empleado", default="Sin nombre"),
            fecha,
            hora,
            normalize_status(get_value(record, "status", "punch", "tipo", default="Registro")),
            get_value(record, "device_name", "reloj", "clock_name", default="Reloj Principal"),
            get_value(record, "device_ip", "ip_reloj", "clock_ip", default="192.168.1.50"),
        ])

    files = {
        "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>""",
        "_rels/.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        "xl/workbook.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Asistencias" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>""",
        "xl/_rels/workbook.xml.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>""",
        "xl/styles.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2">
    <font><sz val="11"/><name val="Calibri"/></font>
    <font><b/><sz val="11"/><name val="Calibri"/></font>
  </fonts>
  <fills count="1"><fill><patternFill patternType="none"/></fill></fills>
  <borders count="1"><border/></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="2">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
  </cellXfs>
</styleSheet>""",
        "xl/worksheets/sheet1.xml": build_sheet(rows),
    }

    output = BytesIO()

    with ZipFile(output, "w", ZIP_DEFLATED) as workbook:
        for path, content in files.items():
            workbook.writestr(path, content)

    return output.getvalue()